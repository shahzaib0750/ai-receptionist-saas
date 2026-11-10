import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.vapi_call import VapiCall, VapiCallEvent
from app.models.vapi_configuration import VapiConfiguration
from app.schemas.vapi_webhook import (
    VapiEndOfCallReportMessage,
    VapiStatusUpdateMessage,
)
from app.services.billing import record_finalized_call_usage

logger = logging.getLogger(__name__)

_MAX_RECOVERY_BATCH_SIZE = 1000

# Webhooks lock configuration, then receipt, then call. Recovery starts at the
# receipt and follows the same order for the remaining rows.
_STATUS_ORDER = {
    "scheduled": 0,
    "queued": 1,
    "ringing": 2,
    "in-progress": 3,
    "forwarding": 4,
    "ended": 5,
}


class VapiCallEventResult(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    STALE = "stale"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RecoveryBatchResult:
    batch_size: int
    recovered_count: int
    failed_attempt_count: int
    terminal_failure_count: int
    skipped_count: int
    pending_count: int
    oldest_pending_age_seconds: float | None
    duration_seconds: float


def _database_error(
    db: Session,
    error: SQLAlchemyError,
    *,
    event_type: str = "status-update",
) -> HTTPException:
    db.rollback()
    logger.error(
        "Vapi call-event transaction failed",
        extra={"event_type": event_type, "error_type": type(error).__name__},
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Webhook processing temporarily unavailable",
    )


def _resolve_vapi_configuration(
    event: VapiStatusUpdateMessage | VapiEndOfCallReportMessage,
    db: Session,
) -> VapiConfiguration:
    identifiers = []
    if event.call.assistantId is not None:
        identifiers.append(VapiConfiguration.assistant_id == event.call.assistantId)
    if event.call.phoneNumberId is not None:
        identifiers.append(
            VapiConfiguration.phone_number_id == event.call.phoneNumberId
        )
    if not identifiers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Call event is missing configured Vapi identifiers",
        )

    configurations = db.scalars(
        select(VapiConfiguration)
        .where(
            VapiConfiguration.is_enabled.is_(True),
            or_(*identifiers),
        )
        .limit(2)
        .with_for_update()
    ).all()
    if len(configurations) != 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vapi configuration not found",
        )

    configuration = configurations[0]
    if (
        event.call.assistantId is not None
        and configuration.assistant_id != event.call.assistantId
    ) or (
        event.call.phoneNumberId is not None
        and configuration.phone_number_id != event.call.phoneNumberId
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vapi configuration not found",
        )
    return configuration


def _find_event(
    db: Session,
    business_id: UUID,
    vapi_call_id: str,
    event_status: str,
    *,
    event_type: str = "status-update",
    lock: bool = False,
) -> VapiCallEvent | None:
    statement = select(VapiCallEvent).where(
        VapiCallEvent.business_id == business_id,
        VapiCallEvent.vapi_call_id == vapi_call_id,
        VapiCallEvent.event_type == event_type,
        VapiCallEvent.event_status == event_status,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _direction_for_event(
    event: VapiStatusUpdateMessage | VapiEndOfCallReportMessage,
) -> str | None:
    if event.call.call_type == "inboundPhoneCall":
        return "inbound"
    if event.call.call_type == "outboundPhoneCall":
        return "outbound"
    return None


def _recording_url(event: VapiEndOfCallReportMessage) -> str | None:
    candidates: list[str] = []
    artifact = event.artifact
    if artifact is None:
        return None
    if artifact.recordingUrl is not None:
        candidates.append(artifact.recordingUrl)

    def collect_urls(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if isinstance(key, str) and "url" in key.casefold():
                    if isinstance(nested, str):
                        candidates.append(nested)
                    else:
                        collect_urls(nested)
                else:
                    collect_urls(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_urls(nested)

    if artifact.recording is not None:
        collect_urls(artifact.recording)

    for candidate in candidates:
        if len(candidate) > 2048:
            continue
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            continue
        if (
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        ):
            return candidate
    return None


def _report_values(
    event: VapiEndOfCallReportMessage,
) -> dict[str, object | None]:
    artifact = event.artifact
    duration = event.call.duration
    return {
        "caller_number": (
            event.call.customer.number if event.call.customer is not None else None
        ),
        "recipient_number": (
            event.call.phoneNumber.number
            if event.call.phoneNumber is not None
            else None
        ),
        "started_at": event.call.startedAt,
        "ended_at": event.call.endedAt,
        "duration_seconds": round(duration) if duration is not None else None,
        "transcript": artifact.transcript if artifact is not None else None,
        "recording_url": _recording_url(event),
        "ended_reason": event.endedReason,
    }


def _is_global_call_id_conflict(error: IntegrityError) -> bool:
    diagnostic = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    return diagnostic == "uq_vapi_calls_vapi_call_id"


def _record_failed_attempt(
    event_id: UUID,
    db: Session,
    *,
    event_type: str,
    settings: Settings,
) -> None:
    try:
        event = db.scalar(
            select(VapiCallEvent)
            .where(
                VapiCallEvent.id == event_id,
                VapiCallEvent.processing_status == "pending",
            )
            .with_for_update()
        )
        if event is None:
            db.rollback()
            return

        event.processing_attempt_count += 1
        if event.processing_attempt_count >= settings.VAPI_RECOVERY_MAX_ATTEMPTS:
            event.processing_status = "failed"
            event.next_attempt_at = None
            event.safe_error_code = "max_attempts_exceeded"
        else:
            delay = min(
                settings.VAPI_RECOVERY_POLL_INTERVAL_SECONDS
                * (2 ** min(event.processing_attempt_count - 1, 30)),
                settings.VAPI_RECOVERY_MAX_BACKOFF_SECONDS,
            )
            event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            event.safe_error_code = "processing_error"
        db.commit()
    except SQLAlchemyError as error:
        raise _database_error(db, error, event_type=event_type) from None


def _process_pending_event(
    event_id: UUID,
    db: Session,
    *,
    skip_locked: bool = False,
    retry_global_call_id_conflict: bool = True,
    settings: Settings | None = None,
) -> VapiCallEventResult:
    settings = settings or get_settings()
    event_type = "status-update"
    try:
        event = db.scalar(
            select(VapiCallEvent)
            .where(VapiCallEvent.id == event_id)
            .with_for_update(skip_locked=skip_locked)
        )
        if event is None:
            db.rollback()
            return (
                VapiCallEventResult.SKIPPED
                if skip_locked
                else VapiCallEventResult.FAILED
            )
        event_type = event.event_type
        if event.processing_status == "failed":
            db.rollback()
            return VapiCallEventResult.FAILED
        if event.processing_status == "processed":
            db.rollback()
            return VapiCallEventResult.DUPLICATE
        if event.next_attempt_at is not None:
            retry_at = event.next_attempt_at
            now = datetime.now(UTC)
            if retry_at.tzinfo is None:
                now = now.replace(tzinfo=None)
            if retry_at > now:
                db.rollback()
                return VapiCallEventResult.DUPLICATE

        event.processing_attempt_count += 1
        call = db.scalar(
            select(VapiCall)
            .where(VapiCall.vapi_call_id == event.vapi_call_id)
            .with_for_update()
        )
        if call is not None and call.business_id != event.business_id:
            event.processing_status = "failed"
            event.next_attempt_at = None
            event.safe_error_code = "call_business_conflict"
            db.commit()
            return VapiCallEventResult.FAILED

        if call is None:
            call = VapiCall(
                business_id=event.business_id,
                vapi_call_id=event.vapi_call_id,
                assistant_id=event.assistant_id,
                phone_number_id=event.phone_number_id,
                direction=event.direction,
                status=event.event_status,
            )
            db.add(call)
            db.flush()
            outcome = "applied"
            result = VapiCallEventResult.PROCESSED
        elif _STATUS_ORDER[event.event_status] > _STATUS_ORDER[call.status]:
            call.status = event.event_status
            outcome = "applied"
            result = VapiCallEventResult.PROCESSED
        else:
            outcome = "stale"
            result = VapiCallEventResult.STALE

        if event.event_type == "end-of-call-report":
            if _STATUS_ORDER[event.event_status] > _STATUS_ORDER[call.status]:
                call.status = event.event_status
            for field in (
                "caller_number",
                "recipient_number",
                "started_at",
                "ended_at",
                "duration_seconds",
                "transcript",
                "recording_url",
                "ended_reason",
            ):
                value = getattr(event, field)
                if value is not None:
                    setattr(call, field, value)
            outcome = "applied"
            result = VapiCallEventResult.PROCESSED
            record_finalized_call_usage(db, call)

        if call.direction is None and event.direction is not None:
            call.direction = event.direction
        event.call_record_id = call.id
        event.processing_status = "processed"
        event.next_attempt_at = None
        event.outcome = outcome
        event.safe_error_code = None
        db.commit()
        return result
    except IntegrityError as error:
        db.rollback()
        if retry_global_call_id_conflict and _is_global_call_id_conflict(error):
            return _process_pending_event(
                event_id,
                db,
                skip_locked=skip_locked,
                retry_global_call_id_conflict=False,
                settings=settings,
            )
        _record_failed_attempt(
            event_id,
            db,
            event_type=event_type,
            settings=settings,
        )
        raise _database_error(db, error, event_type=event_type) from None
    except SQLAlchemyError as error:
        db.rollback()
        _record_failed_attempt(
            event_id,
            db,
            event_type=event_type,
            settings=settings,
        )
        raise _database_error(db, error, event_type=event_type) from None


def process_vapi_status_update(
    event: VapiStatusUpdateMessage,
    db: Session,
) -> VapiCallEventResult:
    configuration: VapiConfiguration | None = None
    try:
        configuration = _resolve_vapi_configuration(event, db)
        existing = _find_event(
            db,
            configuration.business_id,
            event.call.id,
            event.status,
            lock=True,
        )
        if existing is not None:
            event_id = existing.id
            direction = _direction_for_event(event)
            if direction is not None and existing.direction is None:
                existing.direction = direction
                call = db.scalar(
                    select(VapiCall)
                    .where(VapiCall.vapi_call_id == event.call.id)
                    .with_for_update()
                )
                if call is not None:
                    if call.business_id != configuration.business_id:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Vapi call not found",
                        )
                    if call.direction is None:
                        call.direction = direction
            db.commit()
            if existing.processing_status == "pending":
                return _process_pending_event(event_id, db)
            if existing.processing_status == "failed":
                return VapiCallEventResult.FAILED
            return VapiCallEventResult.DUPLICATE

        receipt = VapiCallEvent(
            business_id=configuration.business_id,
            vapi_call_id=event.call.id,
            assistant_id=configuration.assistant_id,
            phone_number_id=configuration.phone_number_id,
            direction=_direction_for_event(event),
            event_type=event.type,
            event_status=event.status,
            provider_timestamp=event.timestamp,
            processing_status="pending",
            processing_attempt_count=0,
        )
        db.add(receipt)
        db.commit()
        return _process_pending_event(receipt.id, db)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        try:
            if configuration is None:
                raise _database_error(db, error)
            existing = _find_event(
                db,
                configuration.business_id,
                event.call.id,
                event.status,
                lock=True,
            )
        except SQLAlchemyError as lookup_error:
            raise _database_error(db, lookup_error) from None
        if existing is not None:
            event_id = existing.id
            processing_status = existing.processing_status
            db.commit()
            if processing_status == "pending":
                return _process_pending_event(event_id, db)
            if processing_status == "processed":
                return VapiCallEventResult.DUPLICATE
            return VapiCallEventResult.FAILED
        raise _database_error(db, error) from None
    except SQLAlchemyError as error:
        raise _database_error(db, error) from None


def process_vapi_end_of_call_report(
    event: VapiEndOfCallReportMessage,
    db: Session,
) -> VapiCallEventResult:
    configuration: VapiConfiguration | None = None
    event_type = "end-of-call-report"
    event_status = "ended"
    try:
        configuration = _resolve_vapi_configuration(event, db)
        existing = _find_event(
            db,
            configuration.business_id,
            event.call.id,
            event_status,
            event_type=event_type,
            lock=True,
        )
        if existing is not None:
            event_id = existing.id
            db.commit()
            if existing.processing_status == "pending":
                return _process_pending_event(event_id, db)
            if existing.processing_status == "failed":
                return VapiCallEventResult.FAILED
            return VapiCallEventResult.DUPLICATE

        receipt = VapiCallEvent(
            business_id=configuration.business_id,
            vapi_call_id=event.call.id,
            assistant_id=configuration.assistant_id,
            phone_number_id=configuration.phone_number_id,
            direction=_direction_for_event(event),
            event_type=event_type,
            event_status=event_status,
            provider_timestamp=event.timestamp,
            processing_status="pending",
            processing_attempt_count=0,
            **_report_values(event),
        )
        db.add(receipt)
        db.commit()
        return _process_pending_event(receipt.id, db)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        try:
            if configuration is None:
                raise _database_error(db, error, event_type=event_type)
            existing = _find_event(
                db,
                configuration.business_id,
                event.call.id,
                event_status,
                event_type=event_type,
                lock=True,
            )
        except SQLAlchemyError as lookup_error:
            raise _database_error(
                db,
                lookup_error,
                event_type=event_type,
            ) from None
        if existing is not None:
            event_id = existing.id
            processing_status = existing.processing_status
            db.commit()
            if processing_status == "pending":
                return _process_pending_event(event_id, db)
            if processing_status == "processed":
                return VapiCallEventResult.DUPLICATE
            return VapiCallEventResult.FAILED
        raise _database_error(db, error, event_type=event_type) from None
    except SQLAlchemyError as error:
        raise _database_error(db, error, event_type=event_type) from None


def process_pending_vapi_call_events(
    db: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
) -> RecoveryBatchResult:
    settings = settings or get_settings()
    batch_limit = min(
        settings.VAPI_RECOVERY_BATCH_SIZE if limit is None else limit,
        _MAX_RECOVERY_BATCH_SIZE,
    )
    if batch_limit < 1:
        raise ValueError("Recovery batch limit must be at least one")

    started_at = time.monotonic()

    try:
        pending_ids = db.scalars(
            select(VapiCallEvent.id)
            .where(
                VapiCallEvent.processing_status == "pending",
                or_(
                    VapiCallEvent.next_attempt_at.is_(None),
                    VapiCallEvent.next_attempt_at <= func.now(),
                ),
            )
            .order_by(VapiCallEvent.received_at, VapiCallEvent.id)
            .limit(batch_limit)
        ).all()
    except SQLAlchemyError as error:
        raise _database_error(db, error) from None

    db.rollback()
    recovered = 0
    failed = 0
    skipped = 0
    for event_id in pending_ids:
        try:
            result = _process_pending_event(
                event_id,
                db,
                skip_locked=True,
                settings=settings,
            )
        except HTTPException as error:
            failed += 1
            logger.warning(
                "Pending Vapi call-event recovery failed",
                extra={
                    "event_id": str(event_id),
                    "status_code": error.status_code,
                },
            )
            continue
        if result in {
            VapiCallEventResult.PROCESSED,
            VapiCallEventResult.STALE,
        }:
            recovered += 1
        elif result is VapiCallEventResult.FAILED:
            failed += 1
        elif result is VapiCallEventResult.SKIPPED:
            skipped += 1

    try:
        pending_count, oldest_pending_at = db.execute(
            select(
                func.count(VapiCallEvent.id),
                func.min(VapiCallEvent.received_at),
            ).where(VapiCallEvent.processing_status == "pending")
        ).one()
        terminal_count = 0
        if pending_ids:
            terminal_count = db.scalar(
                select(func.count(VapiCallEvent.id)).where(
                    VapiCallEvent.id.in_(pending_ids),
                    VapiCallEvent.processing_status == "failed",
                )
            ) or 0
        db.rollback()
    except SQLAlchemyError as error:
        raise _database_error(db, error) from None

    oldest_age = None
    if oldest_pending_at is not None:
        if oldest_pending_at.tzinfo is None:
            oldest_pending_at = oldest_pending_at.replace(tzinfo=UTC)
        oldest_age = max(
            0.0,
            (datetime.now(UTC) - oldest_pending_at).total_seconds(),
        )

    return RecoveryBatchResult(
        batch_size=len(pending_ids),
        recovered_count=recovered,
        failed_attempt_count=failed,
        terminal_failure_count=terminal_count,
        skipped_count=skipped,
        pending_count=pending_count,
        oldest_pending_age_seconds=oldest_age,
        duration_seconds=time.monotonic() - started_at,
    )


def recover_pending_vapi_call_events(
    db: Session,
    *,
    limit: int = 50,
) -> int:
    return process_pending_vapi_call_events(db, limit=limit).recovered_count
