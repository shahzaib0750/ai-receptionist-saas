import json
import logging
import threading

from app.core.config import Settings
from app.services.vapi_call_events import RecoveryBatchResult
from app.workers.vapi_recovery import _StructuredLogFormatter, run_recovery_worker
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        DB_PASSWORD="test-database-password",
        SECRET_KEY="test-secret-key-that-is-at-least-thirty-two-characters",
        VAPI_RECOVERY_POLL_INTERVAL_SECONDS=1,
        VAPI_RECOVERY_BATCH_SIZE=2,
    )


def test_worker_logs_structured_batch_fields() -> None:
    record = logging.LogRecord(
        name="vapi-recovery",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Vapi recovery batch completed",
        args=(),
        exc_info=None,
    )
    record.batch_size = 12

    entry = json.loads(_StructuredLogFormatter().format(record))

    assert entry["message"] == "Vapi recovery batch completed"
    assert entry["batch_size"] == 12
    assert entry["level"] == "INFO"


def test_worker_polls_until_shutdown_and_closes_each_session(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite://")
    session_factory = sessionmaker(bind=engine, class_=Session)
    stop_event = threading.Event()
    poll_count = 0

    def process_batch(session, *, settings):
        nonlocal poll_count
        assert session.is_active
        assert settings.VAPI_RECOVERY_BATCH_SIZE == 2
        poll_count += 1
        if poll_count == 3:
            stop_event.set()
        return RecoveryBatchResult(
            batch_size=0,
            recovered_count=0,
            failed_attempt_count=0,
            terminal_failure_count=0,
            skipped_count=0,
            pending_count=0,
            oldest_pending_age_seconds=None,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(
        "app.workers.vapi_recovery.process_pending_vapi_call_events",
        process_batch,
    )
    run_recovery_worker(session_factory, _settings(), stop_event)
    engine.dispose()

    assert poll_count == 3


def test_worker_continues_polling_after_database_error(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    session_factory = sessionmaker(bind=engine, class_=Session)
    stop_event = threading.Event()
    poll_count = 0

    def process_batch(_session, *, settings):
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            raise HTTPException(
                status_code=503,
                detail="Webhook processing temporarily unavailable",
            )
        stop_event.set()
        return RecoveryBatchResult(
            batch_size=0,
            recovered_count=0,
            failed_attempt_count=0,
            terminal_failure_count=0,
            skipped_count=0,
            pending_count=0,
            oldest_pending_age_seconds=None,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(
        "app.workers.vapi_recovery.process_pending_vapi_call_events",
        process_batch,
    )
    run_recovery_worker(session_factory, _settings(), stop_event)
    engine.dispose()

    assert poll_count == 2
