import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.db.session import Base
from app.models.billing import (
    BillingCustomer,
    BillingInvoice,
    BillingMinuteGrant,
    BillingPayment,
    BillingPlan,
    BillingProviderEvent,
    BillingSubscription,
    BillingSubscriptionPeriod,
    BillingUsage,
)
from app.models.business import Business
from app.models.user import User
from app.models.vapi_call import VapiCall, VapiCallEvent
from app.models.vapi_configuration import VapiConfiguration
from app.schemas.vapi_webhook import (
    VapiEndOfCallReportMessage,
    VapiStatusUpdateMessage,
)
from app.services.vapi_call_events import (
    VapiCallEventResult,
    _process_pending_event,
    process_vapi_end_of_call_report,
    process_vapi_status_update,
    recover_pending_vapi_call_events,
)
from fastapi import HTTPException
from sqlalchemy import Engine, create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

_TEST_TABLES = [
    User.__table__,
    Business.__table__,
    VapiConfiguration.__table__,
    VapiCall.__table__,
    VapiCallEvent.__table__,
    BillingPlan.__table__,
    BillingCustomer.__table__,
    BillingSubscription.__table__,
    BillingSubscriptionPeriod.__table__,
    BillingMinuteGrant.__table__,
    BillingUsage.__table__,
    BillingInvoice.__table__,
    BillingPayment.__table__,
    BillingProviderEvent.__table__,
]
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@pytest.fixture
def postgres_session_factory() -> Iterator[sessionmaker[Session]]:
    database_url = os.environ.get("VAPI_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set VAPI_TEST_DATABASE_URL to an isolated local PostgreSQL DB")

    url = make_url(database_url)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in _LOCAL_HOSTS
        or url.database is None
        or not url.database.startswith("vapi_test_")
    ):
        pytest.fail(
            "VAPI_TEST_DATABASE_URL must target a local PostgreSQL database "
            "whose name starts with 'vapi_test_'"
        )

    engine = create_engine(database_url, pool_size=8, max_overflow=0)
    schema_name = f"vapi_test_{uuid4().hex}"
    schema_created = False
    try:
        with engine.begin() as connection:
            current_database = connection.scalar(text("SELECT current_database()"))
            if current_database != url.database:
                pytest.fail("Connected database does not match test database URL")
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')
            schema_created = True

        test_engine = engine.execution_options(
            schema_translate_map={None: schema_name}
        )
        Base.metadata.create_all(test_engine, tables=_TEST_TABLES)
        yield sessionmaker(
            bind=test_engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )
    finally:
        if schema_created:
            test_engine = engine.execution_options(
                schema_translate_map={None: schema_name}
            )
            Base.metadata.drop_all(test_engine, tables=_TEST_TABLES)
            with engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema_name}"')
        engine.dispose()


def _create_business(
    session_factory: sessionmaker[Session],
) -> tuple[UUID, str, str]:
    suffix = uuid4().hex
    with session_factory() as session:
        user = User(
            full_name="PostgreSQL concurrency test",
            email=f"{suffix}@example.test",
            password_hash="not-a-real-password-hash",
        )
        session.add(user)
        session.flush()
        business = Business(name=f"PostgreSQL test {suffix}", owner_user_id=user.id)
        session.add(business)
        session.flush()
        assistant_id = f"assistant-{suffix}"
        phone_number_id = f"phone-{suffix}"
        session.add(
            VapiConfiguration(
                business_id=business.id,
                assistant_id=assistant_id,
                phone_number_id=phone_number_id,
            )
        )
        session.commit()
        return business.id, assistant_id, phone_number_id


def _status_event(
    call_id: str,
    assistant_id: str,
    phone_number_id: str,
) -> VapiStatusUpdateMessage:
    return VapiStatusUpdateMessage.model_validate(
        {
            "type": "status-update",
            "status": "queued",
            "call": {
                "id": call_id,
                "assistantId": assistant_id,
                "phoneNumberId": phone_number_id,
            },
        }
    )


def _is_locked_select(statement: str, table: str) -> bool:
    normalized = statement.casefold()
    return (
        normalized.lstrip().startswith("select")
        and (f"from {table}" in normalized or f".{table}" in normalized)
        and "for update" in normalized
    )


def _concurrent_status_update(
    session_factory: sessionmaker[Session],
    event_message: VapiStatusUpdateMessage,
    *,
    role: str,
) -> VapiCallEventResult:
    with session_factory() as session:
        session.connection().info["vapi_test_role"] = role
        return process_vapi_status_update(event_message, session)


def test_duplicate_deliveries_create_one_receipt_and_call(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    _, assistant_id, phone_number_id = _create_business(postgres_session_factory)
    call_id = f"duplicate-{uuid4().hex}"
    event_message = _status_event(call_id, assistant_id, phone_number_id)
    first_holds_receipt = threading.Event()
    second_requests_receipt = threading.Event()
    release_first = threading.Event()
    engine: Engine = postgres_session_factory.kw["bind"]

    def pause_first_processing(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if (
            connection.info.get("vapi_test_role") == "duplicate-one"
            and _is_locked_select(statement, "vapi_call_events")
        ):
            query_count = connection.info.get("receipt_lock_query_count", 0) + 1
            connection.info["receipt_lock_query_count"] = query_count
            if query_count == 2:
                first_holds_receipt.set()
                if not release_first.wait(timeout=10):
                    raise TimeoutError("Test did not release the first receipt lock")

    def observe_second_receipt_request(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if (
            connection.info.get("vapi_test_role") == "duplicate-two"
            and _is_locked_select(statement, "vapi_call_events")
        ):
            second_requests_receipt.set()

    event.listen(engine, "after_cursor_execute", pause_first_processing)
    event.listen(engine, "before_cursor_execute", observe_second_receipt_request)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                _concurrent_status_update,
                postgres_session_factory,
                event_message,
                role="duplicate-one",
            )
            assert first_holds_receipt.wait(timeout=10)
            second = executor.submit(
                _concurrent_status_update,
                postgres_session_factory,
                event_message,
                role="duplicate-two",
            )
            assert second_requests_receipt.wait(timeout=10)
            release_first.set()
            results = [
                first.result(timeout=20),
                second.result(timeout=20),
            ]
    finally:
        release_first.set()
        event.remove(engine, "after_cursor_execute", pause_first_processing)
        event.remove(engine, "before_cursor_execute", observe_second_receipt_request)

    assert results.count(VapiCallEventResult.PROCESSED) == 1
    assert results.count(VapiCallEventResult.DUPLICATE) == 1
    with postgres_session_factory() as session:
        assert session.scalar(
            select(VapiCall.id).where(VapiCall.vapi_call_id == call_id)
        )
        receipt_count = session.scalar(
            select(func.count())
            .select_from(VapiCallEvent)
            .where(VapiCallEvent.vapi_call_id == call_id)
        )
        assert receipt_count == 1


def test_concurrent_businesses_racing_for_global_call_id_are_isolated(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    first_business, first_assistant, first_phone = _create_business(
        postgres_session_factory
    )
    second_business, second_assistant, second_phone = _create_business(
        postgres_session_factory
    )
    call_id = f"cross-business-{uuid4().hex}"
    events = (
        _status_event(call_id, first_assistant, first_phone),
        _status_event(call_id, second_assistant, second_phone),
    )
    both_checked_call = threading.Barrier(2)
    engine: Engine = postgres_session_factory.kw["bind"]

    def synchronize_missing_call_lookup(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if (
            connection.info.get("vapi_test_role", "").startswith("cross-business")
            and not connection.info.get("call_barrier_waited")
            and _is_locked_select(statement, "vapi_calls")
        ):
            connection.info["call_barrier_waited"] = True
            both_checked_call.wait(timeout=10)

    event.listen(engine, "after_cursor_execute", synchronize_missing_call_lookup)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _concurrent_status_update,
                    postgres_session_factory,
                    event_message,
                    role=f"cross-business-{index}",
                )
                for index, event_message in enumerate(events)
            ]
            results = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_missing_call_lookup)

    assert sorted(result.value for result in results) == ["failed", "processed"]
    with postgres_session_factory() as session:
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == call_id)
        )
        assert call is not None
        assert call.business_id in {first_business, second_business}
        receipts = session.scalars(
            select(VapiCallEvent).where(VapiCallEvent.vapi_call_id == call_id)
        ).all()
        assert len(receipts) == 2
        successful_receipt = next(
            receipt for receipt in receipts if receipt.processing_status == "processed"
        )
        failed_receipt = next(
            receipt for receipt in receipts if receipt.processing_status == "failed"
        )
        assert successful_receipt.business_id == call.business_id
        assert successful_receipt.call_record_id == call.id
        assert failed_receipt.business_id != call.business_id
        assert failed_receipt.call_record_id is None
        assert failed_receipt.safe_error_code == "call_business_conflict"


def test_recovery_skips_a_receipt_locked_by_another_worker(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    business_id, assistant_id, phone_number_id = _create_business(
        postgres_session_factory
    )
    call_id = f"skip-locked-{uuid4().hex}"
    with postgres_session_factory() as session:
        receipt = VapiCallEvent(
            business_id=business_id,
            vapi_call_id=call_id,
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
            event_status="queued",
            processing_status="pending",
        )
        session.add(receipt)
        session.commit()
        receipt_id = receipt.id

    with postgres_session_factory() as lock_holder:
        lock_holder.scalar(
            select(VapiCallEvent)
            .where(VapiCallEvent.id == receipt_id)
            .with_for_update()
        )
        with postgres_session_factory() as competing_recovery:
            assert recover_pending_vapi_call_events(competing_recovery, limit=1) == 0
        locked_receipt = lock_holder.get(VapiCallEvent, receipt_id)
        assert locked_receipt is not None
        assert locked_receipt.processing_status == "pending"

    with postgres_session_factory() as recovery_session:
        assert recover_pending_vapi_call_events(recovery_session, limit=1) == 1
    with postgres_session_factory() as session:
        recovered = session.get(VapiCallEvent, receipt_id)
        assert recovered is not None
        assert recovered.processing_status == "processed"
        assert recovered.processing_attempt_count == 1


def test_live_webhook_waiting_on_recovery_returns_duplicate(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    business_id, assistant_id, phone_number_id = _create_business(
        postgres_session_factory
    )
    call_id = f"recovery-webhook-race-{uuid4().hex}"
    event_message = _status_event(call_id, assistant_id, phone_number_id)
    with postgres_session_factory() as session:
        receipt = VapiCallEvent(
            business_id=business_id,
            vapi_call_id=call_id,
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
            event_status="queued",
            processing_status="pending",
        )
        session.add(receipt)
        session.commit()
        receipt_id = receipt.id

    recovery_has_row_lock = threading.Event()
    live_is_waiting = threading.Event()
    release_recovery = threading.Event()
    engine: Engine = postgres_session_factory.kw["bind"]

    def pause_recovery_after_lock(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if (
            connection.info.get("vapi_test_role") == "recovery"
            and _is_locked_select(statement, "vapi_call_events")
        ):
            recovery_has_row_lock.set()
            if not release_recovery.wait(timeout=10):
                raise TimeoutError("Test did not release the recovery row lock")

    def observe_live_lock_request(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if (
            connection.info.get("vapi_test_role") == "live"
            and _is_locked_select(statement, "vapi_call_events")
        ):
            live_is_waiting.set()

    event.listen(engine, "after_cursor_execute", pause_recovery_after_lock)
    event.listen(engine, "before_cursor_execute", observe_live_lock_request)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            def recover() -> int:
                with postgres_session_factory() as session:
                    session.connection().info["vapi_test_role"] = "recovery"
                    return recover_pending_vapi_call_events(session, limit=1)

            recovery_future = executor.submit(recover)
            assert recovery_has_row_lock.wait(timeout=10)
            live_future = executor.submit(
                _concurrent_status_update,
                postgres_session_factory,
                event_message,
                role="live",
            )
            assert live_is_waiting.wait(timeout=10)
            release_recovery.set()
            assert recovery_future.result(timeout=20) == 1
            assert live_future.result(timeout=20) is VapiCallEventResult.DUPLICATE
    finally:
        release_recovery.set()
        event.remove(engine, "after_cursor_execute", pause_recovery_after_lock)
        event.remove(engine, "before_cursor_execute", observe_live_lock_request)

    with postgres_session_factory() as session:
        receipt = session.get(VapiCallEvent, receipt_id)
        assert receipt is not None
        assert receipt.processing_status == "processed"
        assert receipt.processing_attempt_count == 1
        assert session.scalar(
            select(VapiCall.id).where(VapiCall.vapi_call_id == call_id)
        )


def test_failed_processing_rolls_back_but_persists_attempt_count(
    postgres_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business_id, assistant_id, phone_number_id = _create_business(
        postgres_session_factory
    )
    call_id = f"attempt-count-{uuid4().hex}"
    with postgres_session_factory() as session:
        receipt = VapiCallEvent(
            business_id=business_id,
            vapi_call_id=call_id,
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
            event_status="queued",
            processing_status="pending",
        )
        session.add(receipt)
        session.commit()
        receipt_id = receipt.id

    with postgres_session_factory() as session:
        original_commit = session.commit
        fail_once = True

        def fail_processing_commit() -> None:
            nonlocal fail_once
            if fail_once:
                fail_once = False
                raise SQLAlchemyError("simulated processing commit failure")
            original_commit()

        monkeypatch.setattr(session, "commit", fail_processing_commit)
        with pytest.raises(HTTPException) as failure:
            _process_pending_event(receipt_id, session)
        assert failure.value.status_code == 503

    with postgres_session_factory() as session:
        failed_receipt = session.get(VapiCallEvent, receipt_id)
        assert failed_receipt is not None
        assert failed_receipt.processing_status == "pending"
        assert failed_receipt.processing_attempt_count == 1
        assert session.scalar(
            select(VapiCall.id).where(VapiCall.vapi_call_id == call_id)
        ) is None


def test_duplicate_processing_under_concurrent_load_is_idempotent(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    business_id, assistant_id, phone_number_id = _create_business(
        postgres_session_factory
    )
    call_id = f"concurrent-load-{uuid4().hex}"
    with postgres_session_factory() as session:
        receipt = VapiCallEvent(
            business_id=business_id,
            vapi_call_id=call_id,
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
            event_status="queued",
            processing_status="pending",
        )
        session.add(receipt)
        session.commit()
        receipt_id = receipt.id

    def process_once() -> VapiCallEventResult:
        with postgres_session_factory() as session:
            return _process_pending_event(receipt_id, session)

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _: process_once(), range(12)))

    assert results.count(VapiCallEventResult.PROCESSED) == 1
    assert results.count(VapiCallEventResult.DUPLICATE) == 11
    with postgres_session_factory() as session:
        receipt = session.get(VapiCallEvent, receipt_id)
        assert receipt is not None
        assert receipt.processing_status == "processed"
        assert receipt.processing_attempt_count == 1
        assert session.scalar(
            select(func.count())
            .select_from(VapiCall)
            .where(VapiCall.vapi_call_id == call_id)
        ) == 1


def test_recovery_workers_split_pending_receipts_under_load(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    business_id, assistant_id, phone_number_id = _create_business(
        postgres_session_factory
    )
    call_ids = [f"recovery-load-{uuid4().hex}" for _ in range(24)]
    with postgres_session_factory() as session:
        session.add_all(
            [
                VapiCallEvent(
                    business_id=business_id,
                    vapi_call_id=call_id,
                    assistant_id=assistant_id,
                    phone_number_id=phone_number_id,
                    event_status="queued",
                    processing_status="pending",
                )
                for call_id in call_ids
            ]
        )
        session.commit()

    both_workers_read_pending = threading.Barrier(2)
    engine: Engine = postgres_session_factory.kw["bind"]

    def synchronize_worker_batches(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        normalized = statement.casefold()
        if (
            connection.info.get("vapi_test_role", "").startswith("load-recovery")
            and not connection.info.get("pending_batch_barrier_waited")
            and normalized.lstrip().startswith("select")
            and "processing_status" in normalized
            and "for update" not in normalized
            and (".vapi_call_events" in normalized or "from vapi_call_events" in normalized)
        ):
            connection.info["pending_batch_barrier_waited"] = True
            both_workers_read_pending.wait(timeout=10)

    event.listen(engine, "after_cursor_execute", synchronize_worker_batches)
    try:
        def recover(role: str) -> int:
            with postgres_session_factory() as session:
                session.connection().info["vapi_test_role"] = role
                return recover_pending_vapi_call_events(session, limit=24)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(recover, "load-recovery-one"),
                executor.submit(recover, "load-recovery-two"),
            ]
            recovered_counts = [future.result(timeout=30) for future in futures]
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_worker_batches)

    assert sum(recovered_counts) == len(call_ids)
    with postgres_session_factory() as session:
        receipts = session.scalars(
            select(VapiCallEvent).where(VapiCallEvent.vapi_call_id.in_(call_ids))
        ).all()
        assert len(receipts) == len(call_ids)
        assert all(
            receipt.processing_status == "processed" for receipt in receipts
        ), [
            (
                receipt.vapi_call_id,
                receipt.processing_status,
                receipt.processing_attempt_count,
                receipt.safe_error_code,
            )
            for receipt in receipts
            if receipt.processing_status != "processed"
        ]
        assert all(
            receipt.processing_attempt_count == 1 for receipt in receipts
        ), [
            (receipt.vapi_call_id, receipt.processing_attempt_count)
            for receipt in receipts
            if receipt.processing_attempt_count != 1
        ]
        assert session.scalar(
            select(func.count())
            .select_from(VapiCall)
            .where(VapiCall.vapi_call_id.in_(call_ids))
        ) == len(call_ids)


def test_concurrent_final_report_delivery_creates_one_usage_record(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    business_id, assistant_id, phone_number_id = _create_business(
        postgres_session_factory
    )
    now = datetime.now(UTC)
    period_start = now - timedelta(days=1)
    period_end = now + timedelta(days=29)
    with postgres_session_factory() as session:
        plan = BillingPlan(
            name=f"Concurrency plan {uuid4()}",
            monthly_price=Decimal("25.00"),
            currency="USD",
            included_minutes=250,
            max_phone_numbers=1,
        )
        session.add(plan)
        session.flush()
        subscription = BillingSubscription(
            business_id=business_id,
            plan_id=plan.id,
            provider="test",
            provider_subscription_id=f"sub_{uuid4()}",
            status="active",
            provider_status="active",
            current_period_start=period_start,
            current_period_end=period_end,
        )
        session.add(subscription)
        session.flush()
        session.add(
            BillingSubscriptionPeriod(
                business_id=business_id,
                subscription_id=subscription.id,
                period_start=period_start,
                period_end=period_end,
                monthly_price_snapshot=plan.monthly_price,
                currency_snapshot=plan.currency,
                included_minutes_snapshot=plan.included_minutes,
                max_phone_numbers_snapshot=plan.max_phone_numbers,
            )
        )
        session.commit()

    call_id = f"billing-race-{uuid4()}"
    report = VapiEndOfCallReportMessage.model_validate(
        {
            "type": "end-of-call-report",
            "call": {
                "id": call_id,
                "assistantId": assistant_id,
                "phoneNumberId": phone_number_id,
                "type": "inboundPhoneCall",
                "startedAt": (now - timedelta(minutes=2)).isoformat(),
                "endedAt": now.isoformat(),
                "duration": 94,
            },
            "artifact": {"transcript": "Concurrent billing report"},
        }
    )
    barrier = threading.Barrier(2)

    def deliver() -> VapiCallEventResult:
        with postgres_session_factory() as session:
            barrier.wait(timeout=10)
            return process_vapi_end_of_call_report(report, session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: deliver(), range(2)))

    assert sorted(result.value for result in results) == ["duplicate", "processed"]
    with postgres_session_factory() as session:
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == call_id)
        )
        assert call is not None
        assert call.business_id == business_id
        assert session.scalar(
            select(func.count(BillingUsage.id)).where(
                BillingUsage.call_id == call.id,
                BillingUsage.business_id == business_id,
                BillingUsage.billable_seconds == 94,
            )
        ) == 1
