from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import app.models  # noqa: F401
import pytest
from app.db.session import Base
from app.models.billing import (
    BillingAuditLog,
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
from app.models.vapi_call import VapiCall
from app.services.billing import (
    InvalidBillingProviderEvent,
    enforce_call_entitlement,
    grant_period_minutes,
    process_provider_event,
    record_finalized_call_usage,
    usage_summary,
    verify_provider_signature,
)
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _billing_fixture(
    session: Session,
    *,
    included_minutes: int = 100,
) -> tuple[Business, User, BillingPlan, BillingSubscription, BillingSubscriptionPeriod]:
    user = User(
        full_name="Billing owner",
        email=f"{uuid4()}@example.test",
        password_hash="not-a-real-password-hash",
    )
    session.add(user)
    session.flush()
    business = Business(name="Billing business", owner_user_id=user.id)
    session.add(business)
    session.flush()
    plan = BillingPlan(
        name=f"Billing plan {uuid4()}",
        monthly_price=Decimal("29.90"),
        currency="USD",
        included_minutes=included_minutes,
        max_phone_numbers=2,
    )
    session.add(plan)
    session.flush()
    now = datetime.now(UTC)
    start = now - timedelta(days=1)
    end = now + timedelta(days=29)
    subscription = BillingSubscription(
        business_id=business.id,
        plan_id=plan.id,
        provider="test",
        provider_subscription_id=f"sub_{uuid4()}",
        status="active",
        provider_status="active",
        current_period_start=start,
        current_period_end=end,
    )
    session.add(subscription)
    session.flush()
    period = BillingSubscriptionPeriod(
        business_id=business.id,
        subscription_id=subscription.id,
        period_start=start,
        period_end=end,
        monthly_price_snapshot=plan.monthly_price,
        currency_snapshot=plan.currency,
        included_minutes_snapshot=plan.included_minutes,
        max_phone_numbers_snapshot=plan.max_phone_numbers,
    )
    session.add(period)
    session.flush()
    return business, user, plan, subscription, period


def _call(
    session: Session,
    business: Business,
    *,
    duration_seconds: int | None,
    ended_at: datetime | None = None,
) -> VapiCall:
    call = VapiCall(
        business_id=business.id,
        vapi_call_id=f"call_{uuid4()}",
        assistant_id="assistant-test",
        status="ended",
        duration_seconds=duration_seconds,
        ended_at=ended_at or datetime.now(UTC),
    )
    session.add(call)
    session.flush()
    return call


def test_usage_is_idempotent_and_minutes_are_rounded_after_aggregation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        business, _user, _plan, _subscription, _period = _billing_fixture(
            session, included_minutes=1
        )
        first_call = _call(session, business, duration_seconds=30)
        second_call = _call(session, business, duration_seconds=30)

        record_finalized_call_usage(session, first_call)
        record_finalized_call_usage(session, first_call)
        record_finalized_call_usage(session, second_call)
        session.commit()

        assert session.scalar(select(func.count(BillingUsage.id))) == 2
        summary = usage_summary(session, business.id)
        assert summary["used_seconds"] == 60
        assert summary["used_minutes"] == 1
        assert summary["remaining_minutes"] == 0


def test_short_calls_are_not_rounded_up_individually(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        business, _user, _plan, _subscription, _period = _billing_fixture(
            session, included_minutes=1
        )
        for _ in range(3):
            record_finalized_call_usage(
                session,
                _call(session, business, duration_seconds=20),
            )
        session.commit()

        summary = usage_summary(session, business.id)
        assert summary["used_seconds"] == 60
        assert summary["used_minutes"] == 1


def test_usage_is_assigned_by_call_end_across_period_boundary(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        business, _user, plan, subscription, current_period = _billing_fixture(session)
        previous_start = current_period.period_start - timedelta(days=30)
        previous_end = current_period.period_start
        previous_period = BillingSubscriptionPeriod(
            business_id=business.id,
            subscription_id=subscription.id,
            period_start=previous_start,
            period_end=previous_end,
            monthly_price_snapshot=plan.monthly_price,
            currency_snapshot=plan.currency,
            included_minutes_snapshot=plan.included_minutes,
            max_phone_numbers_snapshot=plan.max_phone_numbers,
        )
        session.add(previous_period)
        session.flush()
        before_boundary = _call(
            session,
            business,
            duration_seconds=15,
            ended_at=previous_end - timedelta(microseconds=1),
        )
        at_boundary = _call(
            session,
            business,
            duration_seconds=20,
            ended_at=current_period.period_start,
        )

        before_usage = record_finalized_call_usage(session, before_boundary)
        current_usage = record_finalized_call_usage(session, at_boundary)
        session.commit()

        assert before_usage is not None
        assert current_usage is not None
        assert before_usage.billing_period_id == previous_period.id
        assert current_usage.billing_period_id == current_period.id


def test_missing_or_zero_duration_does_not_create_usage(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        business, _user, _plan, _subscription, _period = _billing_fixture(session)
        no_duration = _call(session, business, duration_seconds=None)
        zero_duration = _call(session, business, duration_seconds=0)

        assert record_finalized_call_usage(session, no_duration) is None
        assert record_finalized_call_usage(session, zero_duration) is None
        assert session.scalar(select(func.count(BillingUsage.id))) == 0


def test_exhausted_allowance_blocks_new_call_entitlement_and_admin_grant_restores_it(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        business, admin, _plan, subscription, _period = _billing_fixture(
            session, included_minutes=1
        )
        record_finalized_call_usage(
            session,
            _call(session, business, duration_seconds=60),
        )
        session.commit()

        with pytest.raises(HTTPException) as exhausted:
            enforce_call_entitlement(session, business.id)
        assert exhausted.value.status_code == 402

        grant = grant_period_minutes(
            session,
            subscription=subscription,
            admin_user_id=admin.id,
            minutes=5,
            reason="Customer support adjustment",
        )
        session.commit()
        assert grant.minutes == 5
        assert session.scalar(select(func.count(BillingMinuteGrant.id))) == 1
        assert session.scalar(select(func.count(BillingAuditLog.id))) == 1
        assert usage_summary(session, business.id)["remaining_minutes"] == 5
        assert enforce_call_entitlement(session, business.id).id == subscription.id


def test_provider_signature_validates_digest_and_timestamp() -> None:
    import hashlib
    import hmac

    secret = "unit-test-webhook-secret"
    payload = b'{"id":"evt_1"}'
    timestamp = 2_000_000_000
    digest = hmac.new(
        secret.encode(),
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()

    verify_provider_signature(
        payload,
        f"t={timestamp},v1={digest}",
        secret,
        now=timestamp,
    )
    with pytest.raises(HTTPException):
        verify_provider_signature(
            payload,
            f"t={timestamp},v1={digest}",
            secret,
            now=timestamp + 301,
        )
    with pytest.raises(HTTPException):
        verify_provider_signature(
            payload,
            f"t={timestamp},v1={'0' * 64}",
            secret,
            now=timestamp,
        )


def test_provider_event_delivery_is_idempotent_and_stale_events_are_ignored(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _business, _user, _plan, subscription, _period = _billing_fixture(session)
        latest_created = datetime.now(UTC)
        subscription.last_provider_event_created_at = latest_created
        session.commit()
        event_data = {
            "subscription_id": subscription.provider_subscription_id,
            "status": "past_due",
        }

        processed = process_provider_event(
            session,
            "test",
            "event-new",
            "subscription.updated",
            latest_created - timedelta(days=1),
            event_data,
        )
        duplicate = process_provider_event(
            session,
            "test",
            "event-new",
            "subscription.updated",
            latest_created - timedelta(days=1),
            event_data,
        )

        assert processed is True
        assert duplicate is False
        assert session.get(BillingSubscription, subscription.id).status == "active"
        assert session.scalar(select(func.count(BillingProviderEvent.id))) == 1
        assert session.scalar(
            select(BillingProviderEvent.processing_status)
        ) == "ignored"


def test_invalid_provider_event_rolls_back_receipt(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        with pytest.raises(InvalidBillingProviderEvent):
            process_provider_event(
                session,
                "test",
                "event-invalid",
                "subscription.updated",
                datetime.now(UTC),
                {"subscription_id": "missing-sub", "status": "not-a-status"},
            )
        assert session.scalar(select(func.count(BillingProviderEvent.id))) == 0


def test_payment_failure_and_recovery_update_subscription_status(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _business, _user, _plan, subscription, _period = _billing_fixture(session)
        provider_subscription_id = subscription.provider_subscription_id

        assert process_provider_event(
            session,
            "test",
            "payment-failed",
            "payment.failed",
            datetime.now(UTC),
            {
                "subscription_id": provider_subscription_id,
                "payment_id": "payment-1",
                "amount": Decimal("29.90"),
                "currency": "USD",
            },
        )
        failed = session.get(BillingSubscription, subscription.id)
        assert failed is not None
        assert failed.status == "past_due"
        assert session.scalar(select(BillingPayment.status)) == "failed"

        assert process_provider_event(
            session,
            "test",
            "payment-succeeded",
            "payment.succeeded",
            datetime.now(UTC) + timedelta(seconds=1),
            {
                "subscription_id": provider_subscription_id,
                "payment_id": "payment-1",
                "amount": Decimal("29.90"),
                "currency": "USD",
            },
        )
        recovered = session.get(BillingSubscription, subscription.id)
        assert recovered is not None
        assert recovered.status == "active"
        assert session.scalar(select(BillingPayment.status)) == "succeeded"
