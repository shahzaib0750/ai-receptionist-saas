import json
import logging
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, engine
from app.services.vapi_call_events import process_pending_vapi_call_events

logger = logging.getLogger(__name__)

_STANDARD_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
}


class _StructuredLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        log_entry.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _STANDARD_LOG_RECORD_KEYS
            }
        )
        if record.exc_info is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def run_recovery_worker(
    session_factory: Callable[[], Session],
    settings: Settings,
    stop_event: threading.Event,
) -> None:
    last_successful_recovery_at: datetime | None = None
    logger.info(
        "Vapi recovery worker started",
        extra={
            "poll_interval_seconds": settings.VAPI_RECOVERY_POLL_INTERVAL_SECONDS,
            "batch_size": settings.VAPI_RECOVERY_BATCH_SIZE,
            "max_attempts": settings.VAPI_RECOVERY_MAX_ATTEMPTS,
        },
    )

    while not stop_event.is_set():
        try:
            with session_factory() as db:
                batch = process_pending_vapi_call_events(db, settings=settings)
        except HTTPException as error:
            logger.error(
                "Vapi recovery poll failed",
                extra={
                    "status_code": error.status_code,
                    "last_successful_recovery_at": last_successful_recovery_at,
                },
            )
        else:
            last_successful_recovery_at = datetime.now(UTC)
            logger.info(
                "Vapi recovery batch completed",
                extra={
                    "batch_size": batch.batch_size,
                    "recovered_count": batch.recovered_count,
                    "failed_attempt_count": batch.failed_attempt_count,
                    "terminal_failure_count": batch.terminal_failure_count,
                    "skipped_count": batch.skipped_count,
                    "pending_count": batch.pending_count,
                    "oldest_pending_age_seconds": (
                        batch.oldest_pending_age_seconds
                    ),
                    "duration_seconds": batch.duration_seconds,
                    "last_successful_recovery_at": last_successful_recovery_at,
                },
            )

        stop_event.wait(settings.VAPI_RECOVERY_POLL_INTERVAL_SECONDS)

    logger.info(
        "Vapi recovery worker stopped",
        extra={"last_successful_recovery_at": last_successful_recovery_at},
    )


def main() -> None:
    settings = get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(_StructuredLogFormatter())
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        handlers=[handler],
    )
    if not settings.VAPI_RECOVERY_ENABLED:
        logger.info("Vapi recovery worker is disabled")
        engine.dispose()
        return

    stop_event = threading.Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("Vapi recovery worker received shutdown signal", extra={"signal": signum})
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        run_recovery_worker(SessionLocal, settings, stop_event)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
