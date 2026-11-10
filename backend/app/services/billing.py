import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.billing import (
    SUBSCRIPTION_STATUSES,
    BillingAuditLog,
    BillingInvoice,
    BillingMinuteGrant,
    BillingPayment,
    BillingPlan,
    BillingProviderEvent,
    BillingSubscription,
    BillingSubscriptionPeriod,
    BillingUsage,
)
from app.models.receptionist_provisioning import ReceptionistProvisioning
from app.models.vapi_call import VapiCall

logger = logging.getLogger(__name__)
_ACTIVE_STATUSES = ("active", "trialing")
_PROVIDER_EVENT_TOLERANCE_SECONDS = 300


class InvalidBillingProviderEvent(ValueError):
    pass


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _calendar_period(timestamp: datetime) -> tuple[datetime, datetime]:
    timestamp = _aware(timestamp).astimezone(UTC)
    start = datetime(timestamp.year, timestamp.month, 1, tzinfo=UTC)
    if timestamp.month == 12:
        end = datetime(timestamp.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(timestamp.year, timestamp.month + 1, 1, tzinfo=UTC)
    return start, end


def _period_from_unix(data: dict[str, Any], name: str) -> datetime | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidBillingProviderEvent(f"{name} must be a Unix timestamp")
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise InvalidBillingProviderEvent(f"{name} is invalid") from error


def verify_provider_signature(
    payload: bytes,
    signature: str | None,
    webhook_secret: str | None,
    *,
    now: int | None = None,
) -> None:
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment webhook is not configured",
        )
    if signature is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment webhook signature",
        )
    fields = dict(
        pair.split("=", 1)
        for pair in signature.split(",")
        if "=" in pair
    )
    timestamp_text = fields.get("t")
    supplied_digest = fields.get("v1")
    if (
        timestamp_text is None
        or supplied_digest is None
        or not timestamp_text.isascii()
        or not timestamp_text.isdecimal()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment webhook signature",
        )
    timestamp = int(timestamp_text)
    current_time = int(time.time()) if now is None else now
    if abs(current_time - timestamp) > _PROVIDER_EVENT_TOLERANCE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment webhook signature has expired",
        )
    signed_content = str(timestamp).encode() + b"." + payload
    expected = hmac.new(
        webhook_secret.encode(),
        signed_content,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied_digest):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment webhook signature",
        )


def current_subscription(
    db: Session,
    business_id: UUID,
    *,
    lock: bool = False,
) -> BillingSubscription | None:
    statement = (
        select(BillingSubscription)
        .where(
            BillingSubscription.business_id == business_id,
            BillingSubscription.status.in_(_ACTIVE_STATUSES),
        )
        .order_by(BillingSubscription.created_at.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def latest_subscription(db: Session, business_id: UUID) -> BillingSubscription | None:
    return db.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.business_id == business_id)
        .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id)
        .limit(1)
    )


def _record_subscription_period(
    db: Session,
    subscription: BillingSubscription,
    plan: BillingPlan,
    start: datetime,
    end: datetime,
) -> BillingSubscriptionPeriod:
    start = _aware(start)
    end = _aware(end)
    period = db.scalar(
        select(BillingSubscriptionPeriod).where(
            BillingSubscriptionPeriod.subscription_id == subscription.id,
            BillingSubscriptionPeriod.period_start == start,
            BillingSubscriptionPeriod.period_end == end,
        )
    )
    if period is not None:
        return period
    period = BillingSubscriptionPeriod(
        business_id=subscription.business_id,
        subscription_id=subscription.id,
        period_start=start,
        period_end=end,
        monthly_price_snapshot=plan.monthly_price,
        currency_snapshot=plan.currency,
        included_minutes_snapshot=plan.included_minutes,
        max_phone_numbers_snapshot=plan.max_phone_numbers,
    )
    db.add(period)
    db.flush()
    return period


def record_finalized_call_usage(db: Session, call: VapiCall) -> BillingUsage | None:
    if call.status != "ended" or call.duration_seconds is None or call.duration_seconds <= 0:
        return None

    existing = db.scalar(
        select(BillingUsage).where(
            BillingUsage.call_id == call.id,
            BillingUsage.usage_type == "call_seconds",
        )
    )
    if existing is not None:
        return existing

    call_ended_at = _aware(call.ended_at or datetime.now(UTC))
    period_result = db.execute(
        select(BillingSubscriptionPeriod, BillingSubscription)
        .join(
            BillingSubscription,
            BillingSubscription.id == BillingSubscriptionPeriod.subscription_id,
        )
        .where(
            BillingSubscriptionPeriod.business_id == call.business_id,
            BillingSubscriptionPeriod.period_start <= call_ended_at,
            BillingSubscriptionPeriod.period_end > call_ended_at,
        )
        .order_by(BillingSubscriptionPeriod.period_start.desc())
        .limit(1)
        .with_for_update(of=BillingSubscription)
    ).one_or_none()

    subscription: BillingSubscription | None = None
    period: BillingSubscriptionPeriod | None = None
    if period_result is not None:
        period, subscription = period_result
    else:
        subscription = current_subscription(db, call.business_id, lock=True)
        if (
            subscription is not None
            and subscription.current_period_start is not None
            and subscription.current_period_end is not None
            and _aware(subscription.current_period_start)
            <= call_ended_at
            < _aware(subscription.current_period_end)
        ):
            plan = db.get(BillingPlan, subscription.plan_id)
            if plan is not None:
                period = _record_subscription_period(
                    db,
                    subscription,
                    plan,
                    subscription.current_period_start,
                    subscription.current_period_end,
                )

    if period is not None:
        period_start = period.period_start
        period_end = period.period_end
        subscription_id = subscription.id if subscription is not None else None
        period_id = period.id
    else:
        period_start, period_end = _calendar_period(call_ended_at)
        subscription_id = None
        period_id = None

    usage = BillingUsage(
        business_id=call.business_id,
        subscription_id=subscription_id,
        billing_period_id=period_id,
        call_id=call.id,
        usage_type="call_seconds",
        billable_seconds=call.duration_seconds,
        quantity=Decimal(call.duration_seconds),
        billing_period_start=period_start,
        billing_period_end=period_end,
    )
    db.add(usage)
    db.flush()
    return usage


def _used_seconds(
    db: Session,
    business_id: UUID,
    start: datetime,
    end: datetime,
) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(BillingUsage.billable_seconds), 0)).where(
                BillingUsage.business_id == business_id,
                BillingUsage.billing_period_start == start,
                BillingUsage.billing_period_end == end,
            )
        )
        or 0
    )


def usage_summary(db: Session, business_id: UUID) -> dict[str, Any]:
    subscription = latest_subscription(db, business_id)
    plan = db.get(BillingPlan, subscription.plan_id) if subscription else None
    if (
        subscription is not None
        and subscription.current_period_start is not None
        and subscription.current_period_end is not None
    ):
        period_start = _aware(subscription.current_period_start)
        period_end = _aware(subscription.current_period_end)
        included_minutes = (
            plan.included_minutes if plan is not None else 0
        )
        current_period_id = db.scalar(
            select(BillingSubscriptionPeriod.id).where(
                BillingSubscriptionPeriod.subscription_id == subscription.id,
                BillingSubscriptionPeriod.period_start == period_start,
                BillingSubscriptionPeriod.period_end == period_end,
            )
        )
        additional_minutes = (
            int(
                db.scalar(
                    select(func.coalesce(func.sum(BillingMinuteGrant.minutes), 0)).where(
                        BillingMinuteGrant.billing_period_id == current_period_id
                    )
                )
                or 0
            )
            if current_period_id is not None
            else 0
        )
        included_minutes += additional_minutes
    else:
        period_start, period_end = _calendar_period(datetime.now(UTC))
        included_minutes = 0
        additional_minutes = 0
        subscription = None
        plan = None

    used_seconds = _used_seconds(db, business_id, period_start, period_end)
    used_minutes = (used_seconds + 59) // 60
    remaining = max(0, included_minutes - used_minutes)
    usage_percent = (
        min(100.0, used_minutes / included_minutes * 100)
        if included_minutes > 0
        else 0.0
    )
    return {
        "business_id": business_id,
        "subscription_id": subscription.id if subscription else None,
        "plan": plan,
        "status": subscription.status if subscription else None,
        "monthly_price": plan.monthly_price if plan else None,
        "currency": plan.currency if plan else None,
        "included_minutes": included_minutes,
        "used_seconds": used_seconds,
        "used_minutes": used_minutes,
        "remaining_minutes": remaining,
        "usage_percent": usage_percent,
        "billing_period_start": period_start if subscription else None,
        "billing_period_end": period_end if subscription else None,
        "next_billing_date": (
            subscription.current_period_end if subscription else None
        ),
        "additional_minutes": additional_minutes,
    }


def enforce_call_entitlement(db: Session, business_id: UUID) -> BillingSubscription:
    subscription = current_subscription(db, business_id, lock=True)
    if (
        subscription is None
        or subscription.current_period_start is None
        or subscription.current_period_end is None
        or not (
            _aware(subscription.current_period_start)
            <= datetime.now(UTC)
            < _aware(subscription.current_period_end)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="An active subscription is required",
        )

    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="The current subscription plan is unavailable",
        )
    summary = usage_summary(db, business_id)
    if summary["used_minutes"] >= summary["included_minutes"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="The included call-minute allowance has been exhausted",
        )
    return subscription


def enforce_provisioning_entitlements(db: Session, business_id: UUID) -> None:
    subscription = enforce_call_entitlement(db, business_id)
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="The current subscription plan is unavailable",
        )
    already_has_phone = db.scalar(
        select(ReceptionistProvisioning.id)
        .where(
            ReceptionistProvisioning.business_id == business_id,
            ReceptionistProvisioning.phone_number.is_not(None),
        )
        .limit(1)
    )
    if already_has_phone is None:
        provisioned_count = db.scalar(
            select(func.count(ReceptionistProvisioning.id)).where(
                ReceptionistProvisioning.business_id == business_id,
                ReceptionistProvisioning.phone_number.is_not(None),
                ReceptionistProvisioning.status != "failed",
            )
        ) or 0
        if provisioned_count >= plan.max_phone_numbers:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="The plan's phone-number limit has been reached",
            )


def _required_string(data: dict[str, Any], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise InvalidBillingProviderEvent(f"{name} is required")
    return value.strip()


def _optional_string(data: dict[str, Any], name: str, limit: int = 255) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise InvalidBillingProviderEvent(f"{name} is invalid")
    return value


def _safe_hosted_invoice_url(data: dict[str, Any]) -> str | None:
    value = _optional_string(data, "hosted_invoice_url", 2048)
    if value is None:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise InvalidBillingProviderEvent("hosted_invoice_url is invalid") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise InvalidBillingProviderEvent("hosted_invoice_url is invalid")
    return value


def _apply_subscription_event(
    db: Session,
    provider: str,
    event_type: str,
    data: dict[str, Any],
    created_at: datetime | None,
) -> None:
    provider_subscription_id = _required_string(data, "subscription_id")
    status_value = data.get("status")
    if status_value is not None and (
        status_value not in SUBSCRIPTION_STATUSES or status_value == "suspended"
    ):
        raise InvalidBillingProviderEvent("subscription status is invalid")
    subscription = db.scalar(
        select(BillingSubscription)
        .where(
            BillingSubscription.provider == provider,
            BillingSubscription.provider_subscription_id == provider_subscription_id,
        )
        .with_for_update()
    )
    if subscription is None and event_type == "subscription.created":
        try:
            business_id = UUID(_required_string(data, "business_id"))
            plan_id = UUID(_required_string(data, "plan_id"))
        except ValueError as error:
            raise InvalidBillingProviderEvent("business_id or plan_id is invalid") from error
        plan = db.get(BillingPlan, plan_id)
        if plan is None:
            raise InvalidBillingProviderEvent("plan_id does not exist")
        subscription = BillingSubscription(
            business_id=business_id,
            plan_id=plan_id,
            provider=provider,
            provider_customer_id=_optional_string(data, "customer_id"),
            provider_subscription_id=provider_subscription_id,
            status="incomplete",
        )
        db.add(subscription)
        db.flush()
    elif subscription is None:
        return

    if (
        created_at is not None
        and subscription.last_provider_event_created_at is not None
        and _aware(created_at) <= _aware(subscription.last_provider_event_created_at)
    ):
        return

    if status_value is not None:
        subscription.provider_status = status_value
        subscription.status = (
            "suspended" if subscription.suspended_by_admin else status_value
        )

    plan_id_value = data.get("plan_id")
    if plan_id_value is not None:
        try:
            plan_id = UUID(str(plan_id_value))
        except ValueError as error:
            raise InvalidBillingProviderEvent("plan_id is invalid") from error
        plan = db.get(BillingPlan, plan_id)
        if plan is None:
            raise InvalidBillingProviderEvent("plan_id does not exist")
        subscription.plan_id = plan.id
    else:
        plan = db.get(BillingPlan, subscription.plan_id)
    assert plan is not None

    for field in ("current_period_start", "current_period_end", "trial_end"):
        parsed = _period_from_unix(data, field)
        if parsed is not None:
            setattr(subscription, field, parsed)
    cancel_at_period_end = data.get("cancel_at_period_end")
    if cancel_at_period_end is not None:
        if not isinstance(cancel_at_period_end, bool):
            raise InvalidBillingProviderEvent("cancel_at_period_end must be boolean")
        subscription.cancel_at_period_end = cancel_at_period_end

    start = subscription.current_period_start
    end = subscription.current_period_end
    if start is not None and end is not None:
        if _aware(start) >= _aware(end):
            raise InvalidBillingProviderEvent("subscription period is invalid")
        _record_subscription_period(db, subscription, plan, start, end)
    if created_at is not None:
        subscription.last_provider_event_created_at = _aware(created_at)


def _apply_invoice_event(
    db: Session,
    provider: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    provider_subscription_id = _required_string(data, "subscription_id")
    subscription = db.scalar(
        select(BillingSubscription)
        .where(
            BillingSubscription.provider == provider,
            BillingSubscription.provider_subscription_id == provider_subscription_id,
        )
        .with_for_update()
    )
    if subscription is None:
        return
    provider_invoice_id = _required_string(data, "invoice_id")
    invoice = db.scalar(
        select(BillingInvoice)
        .where(
            BillingInvoice.provider == provider,
            BillingInvoice.provider_invoice_id == provider_invoice_id,
        )
        .with_for_update()
    )
    if invoice is None:
        amount = data.get("amount")
        currency = data.get("currency")
        if isinstance(amount, bool) or not isinstance(amount, (int, float, Decimal)):
            raise InvalidBillingProviderEvent("invoice amount is invalid")
        if not isinstance(currency, str) or len(currency) != 3:
            raise InvalidBillingProviderEvent("invoice currency is invalid")
        invoice = BillingInvoice(
            business_id=subscription.business_id,
            subscription_id=subscription.id,
            provider=provider,
            provider_invoice_id=provider_invoice_id,
            amount=Decimal(str(amount)),
            currency=currency.upper(),
            status="open",
        )
        db.add(invoice)
    state = {
        "invoice.created": "open",
        "invoice.updated": "open",
        "invoice.paid": "paid",
        "invoice.failed": "uncollectible",
        "invoice.voided": "void",
    }.get(event_type)
    if state is None:
        return
    invoice.status = state
    invoice.payment_reference = _optional_string(data, "payment_reference")
    invoice.failure_details = (
        "Payment failed. Please update the payment method."
        if event_type == "invoice.failed"
        else None
    )
    invoice.hosted_invoice_url = _safe_hosted_invoice_url(data)
    invoice.paid_at = _period_from_unix(data, "paid_at")
    invoice.due_date = None
    due_date = data.get("due_date")
    if due_date is not None:
        if not isinstance(due_date, str):
            raise InvalidBillingProviderEvent("due_date is invalid")
        try:
            invoice.due_date = datetime.fromisoformat(due_date).date()
        except ValueError as error:
            raise InvalidBillingProviderEvent("due_date is invalid") from error
    if state == "uncollectible":
        subscription.provider_status = "past_due"
        subscription.status = (
            "suspended" if subscription.suspended_by_admin else "past_due"
        )
    elif state == "paid" and subscription.provider_status == "past_due":
        subscription.provider_status = "active"
        subscription.status = (
            "suspended" if subscription.suspended_by_admin else "active"
        )


def _apply_payment_event(
    db: Session,
    provider: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    provider_subscription_id = _required_string(data, "subscription_id")
    subscription = db.scalar(
        select(BillingSubscription)
        .where(
            BillingSubscription.provider == provider,
            BillingSubscription.provider_subscription_id == provider_subscription_id,
        )
        .with_for_update()
    )
    if subscription is None:
        return
    payment_id = _required_string(data, "payment_id")
    payment = db.scalar(
        select(BillingPayment)
        .where(
            BillingPayment.provider == provider,
            BillingPayment.provider_payment_id == payment_id,
        )
        .with_for_update()
    )
    if payment is None:
        amount = data.get("amount")
        currency = data.get("currency")
        if isinstance(amount, bool) or not isinstance(amount, (int, float, Decimal)):
            raise InvalidBillingProviderEvent("payment amount is invalid")
        if not isinstance(currency, str) or len(currency) != 3:
            raise InvalidBillingProviderEvent("payment currency is invalid")
        invoice_provider_id = _optional_string(data, "invoice_id")
        invoice_id = None
        if invoice_provider_id is not None:
            invoice_id = db.scalar(
                select(BillingInvoice.id).where(
                    BillingInvoice.provider == provider,
                    BillingInvoice.provider_invoice_id == invoice_provider_id,
                    BillingInvoice.business_id == subscription.business_id,
                )
            )
        payment = BillingPayment(
            business_id=subscription.business_id,
            subscription_id=subscription.id,
            invoice_id=invoice_id,
            provider=provider,
            provider_payment_id=payment_id,
            amount=Decimal(str(amount)),
            currency=currency.upper(),
            status="pending",
        )
        db.add(payment)
    if event_type == "payment.succeeded":
        payment.status = "succeeded"
        payment.failure_details = None
        if subscription.provider_status == "past_due":
            subscription.provider_status = "active"
            subscription.status = (
                "suspended" if subscription.suspended_by_admin else "active"
            )
    elif event_type == "payment.failed":
        payment.status = "failed"
        payment.failure_details = "Payment failed. Please update the payment method."
        subscription.provider_status = "past_due"
        subscription.status = (
            "suspended" if subscription.suspended_by_admin else "past_due"
        )
    elif event_type == "payment.refunded":
        payment.status = "refunded"


def process_provider_event(
    db: Session,
    provider: str,
    event_id: str,
    event_type: str,
    event_created_at: datetime | None,
    data: dict[str, Any],
) -> bool:
    if not provider or len(provider) > 32:
        raise InvalidBillingProviderEvent("provider is invalid")
    event = BillingProviderEvent(
        provider=provider,
        provider_event_id=event_id,
        event_type=event_type,
        provider_created_at=event_created_at,
        processing_status="ignored",
    )
    db.add(event)
    try:
        db.flush()
        subscription: BillingSubscription | None = None
        provider_subscription_id = data.get("subscription_id")
        if (
            event_type
            in {
                "subscription.updated",
                "invoice.created",
                "invoice.updated",
                "invoice.paid",
                "invoice.failed",
                "invoice.voided",
                "payment.succeeded",
                "payment.failed",
                "payment.refunded",
            }
            and isinstance(provider_subscription_id, str)
        ):
            subscription = db.scalar(
                select(BillingSubscription)
                .where(
                    BillingSubscription.provider == provider,
                    BillingSubscription.provider_subscription_id
                    == provider_subscription_id,
                )
                .with_for_update()
            )
        stale = (
            subscription is not None
            and event_created_at is not None
            and subscription.last_provider_event_created_at is not None
            and _aware(event_created_at)
            <= _aware(subscription.last_provider_event_created_at)
        )
        if stale:
            event.processing_status = "ignored"
        elif event_type in {"subscription.created", "subscription.updated"}:
            _apply_subscription_event(
                db, provider, event_type, data, event_created_at
            )
            event.processing_status = "processed"
        elif event_type in {
            "invoice.created",
            "invoice.updated",
            "invoice.paid",
            "invoice.failed",
            "invoice.voided",
        }:
            _apply_invoice_event(db, provider, event_type, data)
            event.processing_status = "processed"
        elif event_type in {
            "payment.succeeded",
            "payment.failed",
            "payment.refunded",
        }:
            _apply_payment_event(db, provider, event_type, data)
            event.processing_status = "processed"
        if (
            subscription is not None
            and event_created_at is not None
            and not stale
        ):
            subscription.last_provider_event_created_at = _aware(event_created_at)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        if db.scalar(
            select(BillingProviderEvent.id).where(
                BillingProviderEvent.provider == provider,
                BillingProviderEvent.provider_event_id == event_id,
            )
        ) is not None:
            db.rollback()
            return False
        raise
    except (InvalidBillingProviderEvent, SQLAlchemyError):
        db.rollback()
        raise


def add_admin_audit(
    db: Session,
    *,
    admin_user_id: UUID,
    action: str,
    business_id: UUID | None = None,
    subscription_id: UUID | None = None,
    details: str | None = None,
) -> None:
    db.add(
        BillingAuditLog(
            admin_user_id=admin_user_id,
            business_id=business_id,
            subscription_id=subscription_id,
            action=action,
            details=details,
        )
    )


def grant_period_minutes(
    db: Session,
    *,
    subscription: BillingSubscription,
    admin_user_id: UUID,
    minutes: int,
    reason: str,
) -> BillingMinuteGrant:
    if (
        subscription.current_period_start is None
        or subscription.current_period_end is None
        or not (
            _aware(subscription.current_period_start)
            <= datetime.now(UTC)
            < _aware(subscription.current_period_end)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription has no current billing period",
        )
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription plan no longer exists",
        )
    period = _record_subscription_period(
        db,
        subscription,
        plan,
        subscription.current_period_start,
        subscription.current_period_end,
    )
    grant = BillingMinuteGrant(
        business_id=subscription.business_id,
        subscription_id=subscription.id,
        billing_period_id=period.id,
        admin_user_id=admin_user_id,
        minutes=minutes,
        reason=reason,
    )
    db.add(grant)
    add_admin_audit(
        db,
        admin_user_id=admin_user_id,
        action="subscription.minutes_granted",
        business_id=subscription.business_id,
        subscription_id=subscription.id,
        details=f"{minutes} minutes; {reason}",
    )
    return grant
