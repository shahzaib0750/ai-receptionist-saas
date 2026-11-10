import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models.billing import (
    BillingPlan,
    BillingProviderEvent,
    BillingSubscription,
)


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


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, email: str) -> tuple[str, UUID]:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Billing Test User",
            "email": email,
            "password": "long-password",
        },
    )
    assert registered.status_code == 201
    user_id = UUID(registered.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "long-password"},
    )
    assert login.status_code == 200
    return login.json()["access_token"], user_id


def create_business(client: TestClient, token: str, name: str) -> UUID:
    response = client.post(
        "/api/v1/businesses",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


def test_published_billing_plans_are_public_and_hide_provider_identifiers(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            BillingPlan(
                name="Public plan",
                description="Published plan details",
                monthly_price=Decimal("39.00"),
                currency="USD",
                provider_price_id="private-provider-price",
                included_minutes=500,
                max_phone_numbers=1,
                is_active=True,
            )
        )
        session.commit()

    response = client.get("/api/v1/billing/plans")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": response.json()[0]["id"],
            "name": "Public plan",
            "description": "Published plan details",
            "monthly_price": "39.00",
            "currency": "USD",
            "included_minutes": 500,
            "max_phone_numbers": 1,
        }
    ]


def test_seed_billing_plans_is_idempotent_and_preserves_customized_values(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    from app.scripts.seed_billing_plans import seed_missing_billing_plans

    with session_factory() as session:
        inserted = seed_missing_billing_plans(session)
        session.commit()

    assert set(inserted) == {"Starter", "Growth", "Business"}

    with session_factory() as session:
        starter = session.scalar(
            select(BillingPlan).where(BillingPlan.name == "Starter")
        )
        assert starter is not None
        starter.monthly_price = Decimal("34.00")
        starter.description = "Customized starter plan."
        session.commit()

    with session_factory() as session:
        assert seed_missing_billing_plans(session) == []
        session.commit()

        plans = session.scalars(select(BillingPlan).order_by(BillingPlan.name)).all()
        assert len(plans) == 3
        starter = next(plan for plan in plans if plan.name == "Starter")
        assert starter.monthly_price == Decimal("34.00")
        assert starter.description == "Customized starter plan."
        assert starter.provider_price_id is None
        assert all(plan.currency == "USD" and plan.is_active for plan in plans)
        assert {
            plan.name: (
                plan.monthly_price,
                plan.included_minutes,
                plan.max_phone_numbers,
            )
            for plan in plans
        } == {
            "Starter": (Decimal("34.00"), 300, 1),
            "Growth": (Decimal("79.00"), 1000, 3),
            "Business": (Decimal("149.00"), 2500, 10),
        }

    response = client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    assert {plan["name"] for plan in response.json()} == {
        "Starter",
        "Growth",
        "Business",
    }


def test_business_billing_data_is_tenant_scoped(client: TestClient) -> None:
    token_a, _user_a = register_and_login(client, "billing-a@example.com")
    token_b, _user_b = register_and_login(client, "billing-b@example.com")
    business_b = create_business(client, token_b, "Business B")

    response = client.get(
        f"/api/v1/businesses/{business_b}/billing/usage",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 404


def test_platform_billing_admin_uses_user_uuid_allowlist(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, user_id = register_and_login(client, "billing-admin@example.com")
    settings = SimpleNamespace(BILLING_ADMIN_USER_IDS="")
    monkeypatch.setattr("app.api.dependencies.get_settings", lambda: settings)
    headers = {"Authorization": f"Bearer {token}"}

    denied = client.get("/api/v1/admin/billing/plans", headers=headers)
    settings.BILLING_ADMIN_USER_IDS = str(user_id)
    allowed = client.get("/api/v1/admin/billing/plans", headers=headers)

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == []


def test_payment_actions_fail_explicitly_without_a_provider_adapter(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    token, _user_id = register_and_login(client, "billing-owner@example.com")
    business_id = create_business(client, token, "Billing Business")
    settings = Settings(
        _env_file=None,
        DB_PASSWORD="local-test-password",
        SECRET_KEY="s" * 32,
        PAYMENT_PROVIDER="test",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    with session_factory() as session:
        plan = BillingPlan(
            name="Configured plan",
            monthly_price=Decimal("29.90"),
            currency="USD",
            provider_price_id="price_test",
            included_minutes=100,
            max_phone_numbers=1,
        )
        session.add(plan)
        session.flush()
        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC) + timedelta(days=29)
        subscription = BillingSubscription(
            business_id=business_id,
            plan_id=plan.id,
            provider="test",
            provider_subscription_id="sub_test",
            status="active",
            provider_status="active",
            current_period_start=start,
            current_period_end=end,
        )
        session.add(subscription)
        session.commit()
        plan_id = plan.id
        subscription_id = subscription.id

    headers = {"Authorization": f"Bearer {token}"}
    cancel = client.post(
        f"/api/v1/businesses/{business_id}/billing/cancel",
        headers=headers,
    )
    change_plan = client.post(
        f"/api/v1/businesses/{business_id}/billing/change-plan",
        json={"plan_id": str(plan_id)},
        headers=headers,
    )

    assert cancel.status_code == 503
    assert change_plan.status_code == 503
    with session_factory() as session:
        subscription = session.get(BillingSubscription, subscription_id)
        assert subscription is not None
        assert subscription.status == "active"
        assert subscription.cancel_at_period_end is False


def test_signed_payment_webhook_is_idempotent_and_rejects_bad_signatures(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    secret = "local-test-payment-webhook-secret"
    settings = Settings(
        _env_file=None,
        DB_PASSWORD="local-test-password",
        SECRET_KEY="s" * 32,
        PAYMENT_PROVIDER="test",
        PAYMENT_WEBHOOK_SECRET=secret,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    timestamp = int(time.time())
    payload = json.dumps(
        {"id": "evt_duplicate", "type": "unsupported.event", "data": {}},
        separators=(",", ":"),
    ).encode()
    digest = hmac.new(
        secret.encode(),
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    signature = f"t={timestamp},v1={digest}"
    headers = {"Provider-Signature": signature}

    rejected = client.post(
        "/api/v1/billing/webhooks/test",
        content=payload,
        headers={"Provider-Signature": f"t={timestamp},v1={'0' * 64}"},
    )
    assert rejected.status_code == 400

    first = client.post(
        "/api/v1/billing/webhooks/test",
        content=payload,
        headers=headers,
    )
    duplicate = client.post(
        "/api/v1/billing/webhooks/test",
        content=payload,
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json() == {"status": "processed"}
    assert duplicate.status_code == 200
    assert duplicate.json() == {"status": "duplicate"}
    with session_factory() as session:
        assert session.scalar(select(func.count(BillingProviderEvent.id))) == 1
