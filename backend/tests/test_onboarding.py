from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID

import pytest
from app.core.config import Settings
from app.db.session import Base, get_db
from app.main import app
from app.models.billing import (
    BillingPlan,
    BillingSubscription,
    BillingSubscriptionPeriod,
)
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Onboarding User",
            "email": email,
            "password": "long-onboarding-password",
        },
    )
    assert response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "long-onboarding-password"},
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        DB_PASSWORD=SecretStr("test-db-password"),
        SECRET_KEY=SecretStr("s" * 32),
        VAPI_API_KEY=SecretStr("test-vapi-api-key"),
        VAPI_WEBHOOK_SECRET=SecretStr("test-vapi-webhook-secret"),
        PUBLIC_API_BASE_URL="https://api.example.test",
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN=SecretStr("test-twilio-auth-token"),
    )


def create_workspace(client: TestClient, token: str) -> UUID:
    response = client.post(
        "/api/v1/businesses",
        json={"name": "Northstar Dental"},
        headers=auth(token),
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


def add_active_billing_subscription(
    session_factory: sessionmaker[Session],
    business_id: UUID,
) -> None:
    now = datetime.now(UTC)
    period_start = now - timedelta(days=1)
    period_end = now + timedelta(days=29)
    with session_factory() as session:
        plan = BillingPlan(
            name=f"Test Plan {business_id}",
            monthly_price=Decimal("10.00"),
            currency="USD",
            included_minutes=100,
            max_phone_numbers=1,
        )
        session.add(plan)
        session.flush()
        subscription = BillingSubscription(
            business_id=business_id,
            plan_id=plan.id,
            provider="test",
            provider_subscription_id=f"sub-{business_id}",
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


def onboarding_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Northstar Dental",
        "industry": "Dental clinic",
        "description": "Family dental care and preventive services.",
        "website": "https://northstar.example.test",
        "address": "12 Main Street",
        "business_hours": "Monday to Friday, 9am to 5pm",
        "contact_phone": "+15551234567",
        "contact_email": "office@northstar.example.com",
        "country_code": "US",
        "requirements_text": (
            "We miss calls after work. Answer questions about our services and "
            "hours. If unsure, explain the team will follow up."
        ),
        "fallback_instructions": "Do not guess; tell callers the team will follow up.",
        "selected_services": ["call_answering"],
        "business_timezone": "America/New_York",
    }
    payload.update(overrides)
    return payload


class FakeVapiClient:
    instances: ClassVar[list[FakeVapiClient]] = []

    def __init__(self, _api_key: str) -> None:
        self.assistants: dict[str, dict[str, Any]] = {}
        self.phones: dict[str, dict[str, Any]] = {}
        self.created_assistants = 0
        self.imported_phones = 0
        self.assignments: list[tuple[str, str]] = []
        self.__class__.instances.append(self)

    def find_assistant(self, provisioning_id: str) -> dict[str, Any] | None:
        return self.assistants.get(provisioning_id)

    def create_assistant(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_assistants += 1
        assistant = {"id": "assistant-managed", **payload}
        self.assistants[payload["metadata"]["provisioningId"]] = assistant
        return assistant

    def find_phone_number(
        self, name: str, phone_number: str
    ) -> dict[str, Any] | None:
        return self.phones.get(name) if self.phones.get(name, {}).get("number") == phone_number else None

    def import_twilio_number(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.imported_phones += 1
        phone = {"id": "phone-managed", **payload}
        self.phones[payload["name"]] = phone
        return phone

    def assign_assistant(self, phone_number_id: str, assistant_id: str) -> None:
        self.assignments.append((phone_number_id, assistant_id))

    def update_assistant(self, _assistant_id: str, _payload: dict[str, Any]) -> None:
        return None

    def close(self) -> None:
        return None


class FakeTwilioClient:
    instances: ClassVar[list[FakeTwilioClient]] = []
    fail_availability_once = False

    def __init__(self, _account_sid: str, _auth_token: str) -> None:
        self.owned: dict[str, dict[str, str]] = {}
        self.purchases = 0
        self.__class__.instances.append(self)

    def find_available_number(self, country_code: str) -> str:
        assert country_code == "US"
        if self.__class__.fail_availability_once:
            self.__class__.fail_availability_once = False
            from app.integrations.vapi.twilio_client import TwilioProviderError

            raise TwilioProviderError(no_number=True)
        return "+12125550123"

    def find_owned_number(self, phone_number: str) -> dict[str, str] | None:
        return self.owned.get(phone_number)

    def purchase_number(self, phone_number: str) -> dict[str, str]:
        self.purchases += 1
        number = {"sid": "PN-managed", "phone_number": phone_number}
        self.owned[phone_number] = number
        return number

    def close(self) -> None:
        return None


def install_fake_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeVapiClient.instances.clear()
    FakeTwilioClient.instances.clear()
    FakeTwilioClient.fail_availability_once = False
    monkeypatch.setattr(
        "app.services.receptionist_provisioning.get_settings",
        make_settings,
    )
    monkeypatch.setattr(
        "app.services.receptionist_provisioning.VapiClient",
        FakeVapiClient,
    )
    monkeypatch.setattr(
        "app.services.receptionist_provisioning.TwilioClient",
        FakeTwilioClient,
    )


def test_onboarding_saves_business_requirements_and_supported_service(
    client: TestClient,
) -> None:
    token = register_and_login(client, "onboarding@example.com")
    business_id = create_workspace(client, token)

    saved = client.put(
        f"/api/v1/businesses/{business_id}/onboarding",
        json=onboarding_payload(),
        headers=auth(token),
    )
    assert saved.status_code == 200
    result = saved.json()
    assert result["industry"] == "Dental clinic"
    assert result["requirements_text"].startswith("We miss calls")
    assert result["selected_services"] == ["call_answering"]
    assert result["status"] == "draft"

    unsupported = client.put(
        f"/api/v1/businesses/{business_id}/onboarding",
        json=onboarding_payload(selected_services=["appointment_booking"]),
        headers=auth(token),
    )
    assert unsupported.status_code == 422


def test_onboarding_and_provisioning_are_business_scoped(client: TestClient) -> None:
    owner_token = register_and_login(client, "owner-onboarding@example.com")
    other_token = register_and_login(client, "other-onboarding@example.com")
    business_id = create_workspace(client, owner_token)

    response = client.get(
        f"/api/v1/businesses/{business_id}/onboarding",
        headers=auth(other_token),
    )
    assert response.status_code == 404

    provision = client.post(
        f"/api/v1/businesses/{business_id}/receptionist/provision",
        json={"accept_phone_number_provisioning": True},
        headers=auth(other_token),
    )
    assert provision.status_code == 404


def test_business_admin_cannot_trigger_billable_phone_provisioning(
    client: TestClient,
) -> None:
    owner_token = register_and_login(client, "owner-billing@example.com")
    admin_token = register_and_login(client, "admin-billing@example.com")
    business_id = create_workspace(client, owner_token)
    member = client.post(
        f"/api/v1/businesses/{business_id}/members",
        json={"email": "admin-billing@example.com", "role": "admin"},
        headers=auth(owner_token),
    )
    assert member.status_code == 201
    saved = client.put(
        f"/api/v1/businesses/{business_id}/onboarding",
        json=onboarding_payload(),
        headers=auth(owner_token),
    )
    assert saved.status_code == 200

    response = client.post(
        f"/api/v1/businesses/{business_id}/receptionist/provision",
        json={"accept_phone_number_provisioning": True},
        headers=auth(admin_token),
    )
    assert response.status_code == 403


def test_phone_number_provisioning_requires_explicit_consent(
    client: TestClient,
) -> None:
    token = register_and_login(client, "consent-onboarding@example.com")
    business_id = create_workspace(client, token)
    saved = client.put(
        f"/api/v1/businesses/{business_id}/onboarding",
        json=onboarding_payload(),
        headers=auth(token),
    )
    assert saved.status_code == 200

    response = client.post(
        f"/api/v1/businesses/{business_id}/receptionist/provision",
        json={"accept_phone_number_provisioning": False},
        headers=auth(token),
    )
    assert response.status_code == 422
    onboarding = client.get(
        f"/api/v1/businesses/{business_id}/onboarding",
        headers=auth(token),
    )
    assert onboarding.status_code == 200
    assert onboarding.json()["phone_number_consent_given"] is False


def test_managed_provisioning_is_idempotent_and_activation_is_truthful(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_providers(monkeypatch)
    token = register_and_login(client, "managed-onboarding@example.com")
    business_id = create_workspace(client, token)
    add_active_billing_subscription(session_factory, business_id)
    saved = client.put(
        f"/api/v1/businesses/{business_id}/onboarding",
        json=onboarding_payload(),
        headers=auth(token),
    )
    assert saved.status_code == 200

    provision_url = f"/api/v1/businesses/{business_id}/receptionist/provision"
    ready = client.post(
        provision_url,
        json={"accept_phone_number_provisioning": True},
        headers=auth(token),
    )
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["phone_number"] == "+12125550123"
    assert ready.json()["phone_number_consent_given"] is True
    assert "assistant_id" not in ready.json()
    assert "phone_number_id" not in ready.json()

    retried = client.post(
        provision_url,
        json={"accept_phone_number_provisioning": True},
        headers=auth(token),
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "ready"
    fake_vapi = FakeVapiClient.instances[-1]
    fake_twilio = FakeTwilioClient.instances[0]
    assert fake_vapi.created_assistants == 1
    assert fake_vapi.imported_phones == 1
    assert fake_twilio.purchases == 1

    activated = client.post(
        f"/api/v1/businesses/{business_id}/receptionist/activate",
        headers=auth(token),
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    fake_vapi = FakeVapiClient.instances[-1]
    assert fake_vapi.assignments == [("phone-managed", "assistant-managed")]

    activation_retry = client.post(
        f"/api/v1/businesses/{business_id}/receptionist/activate",
        headers=auth(token),
    )
    assert activation_retry.status_code == 200
    assert len(fake_vapi.assignments) == 1


def test_provisioning_failure_is_persisted_and_can_be_retried(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_providers(monkeypatch)
    FakeTwilioClient.fail_availability_once = True
    token = register_and_login(client, "retry-onboarding@example.com")
    business_id = create_workspace(client, token)
    add_active_billing_subscription(session_factory, business_id)
    client.put(
        f"/api/v1/businesses/{business_id}/onboarding",
        json=onboarding_payload(),
        headers=auth(token),
    )
    provision_url = f"/api/v1/businesses/{business_id}/receptionist/provision"

    failed = client.post(
        provision_url,
        json={"accept_phone_number_provisioning": True},
        headers=auth(token),
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["safe_error_code"] == "twilio_no_number"
    assert failed.json()["error_message"]

    retried = client.post(
        provision_url,
        json={"accept_phone_number_provisioning": True},
        headers=auth(token),
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "ready"


def test_provisioning_requires_platform_credentials(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        DB_PASSWORD=SecretStr("test-db-password"),
        SECRET_KEY=SecretStr("s" * 32),
    )
    monkeypatch.setattr(
        "app.services.receptionist_provisioning.get_settings",
        lambda: settings,
    )
    token = register_and_login(client, "missing-provider@example.com")
    business_id = create_workspace(client, token)
    add_active_billing_subscription(session_factory, business_id)
    client.put(
        f"/api/v1/businesses/{business_id}/onboarding",
        json=onboarding_payload(),
        headers=auth(token),
    )

    response = client.post(
        f"/api/v1/businesses/{business_id}/receptionist/provision",
        json={"accept_phone_number_provisioning": True},
        headers=auth(token),
    )
    assert response.status_code == 503
    assert "VAPI_API_KEY" in response.json()["detail"]
