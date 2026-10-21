import json
from collections.abc import Iterator
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from app.api.dependencies import require_business_permission
from app.core.config import get_settings
from app.core.security import verify_password
from app.db.session import Base, get_db
from app.main import app
from app.models.business import Business, BusinessMember, BusinessRole
from app.models.receptionist_configuration import ReceptionistConfiguration
from app.models.user import User
from app.models.vapi_configuration import VapiConfiguration
from app.services.business_authorization import (
    BusinessPermission,
    enforce_business_permission,
    has_business_permission,
    roles_with_permission,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    yield TestingSessionLocal
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


def register(client: TestClient, email: str = "person@example.com") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test Person", "email": email, "password": "long-password"},
    )
    assert response.status_code == 201
    return response.json()


def login(client: TestClient, email: str = "person@example.com") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "long-password"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def create_business(client: TestClient, email: str, name: str) -> dict[str, object]:
    token = login(client, email)
    response = client.post(
        "/api/v1/businesses",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()


def add_business_member(
    session_factory: sessionmaker[Session],
    business_id: UUID,
    email: str,
    role: BusinessRole,
) -> None:
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.add(
            BusinessMember(
                business_id=business_id,
                user_id=user.id,
                role=role,
            )
        )
        session.commit()


def assert_response_has_no_internal_fields(data: dict[str, object]) -> None:
    assert not {
        "password_hash",
        "SECRET_KEY",
        "DB_PASSWORD",
        "VAPI_API_KEY",
        "PAYMENT_SECRET_KEY",
    }.intersection(data)


def test_register_normalizes_email_and_never_returns_password_hash(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": " Test Person ",
            "email": " Person@Example.COM ",
            "password": "long-password",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "person@example.com"
    assert "password_hash" not in response.json()
    assert "password" not in response.json()
    assert "access_token" not in response.json()
    assert_response_has_no_internal_fields(response.json())


def test_duplicate_email_rejected_after_normalization(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Another Person", "email": "PERSON@example.com", "password": "long-password"},
    )
    assert response.status_code == 409


def test_password_is_hashed_with_argon2id(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client)
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == "person@example.com"))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password("long-password", user.password_hash)
        assert not verify_password("wrong-password", user.password_hash)


def test_login_success_and_failure(client: TestClient) -> None:
    register(client)
    successful = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "long-password"},
    )
    assert successful.status_code == 200
    assert set(successful.json()) == {"access_token", "token_type"}
    assert_response_has_no_internal_fields(successful.json())
    failed = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "wrong-password"},
    )
    assert failed.status_code == 401


def test_access_token_validation(client: TestClient) -> None:
    user = register(client)
    token = login(client)
    current_user = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert current_user.status_code == 200
    assert_response_has_no_internal_fields(current_user.json())
    assert "access_token" not in current_user.json()

    invalid_algorithm_token = jwt.encode(
        {"sub": user["id"], "type": "access"},
        get_settings().SECRET_KEY.get_secret_value(),
        algorithm="HS512",
    )
    expired_token = jwt.encode(
        {"sub": user["id"], "type": "access", "iat": 0, "exp": 0},
        get_settings().SECRET_KEY.get_secret_value(),
        algorithm="HS256",
    )
    for invalid_token in ("not-a-jwt", invalid_algorithm_token, expired_token):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {invalid_token}"},
        )
        assert response.status_code == 401


def test_authentication_required(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_business_endpoints_reject_invalid_tokens(client: TestClient) -> None:
    headers = {"Authorization": "Bearer not-a-valid-token"}
    assert client.get("/api/v1/businesses", headers=headers).status_code == 401
    assert client.post("/api/v1/businesses", json={"name": "Acme"}, headers=headers).status_code == 401
    assert client.get(f"/api/v1/businesses/{uuid4()}", headers=headers).status_code == 401


def test_business_creation_listing_and_membership(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/businesses", json={"name": "Acme"}, headers=headers)
    assert created.status_code == 201
    business = created.json()
    assert business["name"] == "Acme"

    listed = client.get("/api/v1/businesses", headers=headers)
    assert [item["id"] for item in listed.json()] == [business["id"]]
    retrieved = client.get(f"/api/v1/businesses/{business['id']}", headers=headers)
    assert retrieved.status_code == 200
    assert_response_has_no_internal_fields(business)
    assert_response_has_no_internal_fields(retrieved.json())
    assert "access_token" not in business
    assert "access_token" not in retrieved.json()
    assert "access_token" not in listed.text

    with session_factory() as session:
        membership = session.scalar(
            select(BusinessMember).where(
                BusinessMember.business_id == UUID(business["id"])
            )
        )
        assert membership is not None
        assert membership.role is BusinessRole.OWNER
        assert membership.user_id == UUID(business["owner_user_id"])


def test_business_endpoints_reject_unauthenticated_requests(client: TestClient) -> None:
    assert client.get("/api/v1/businesses").status_code == 401
    assert client.post("/api/v1/businesses", json={"name": "Acme"}).status_code == 401
    assert client.get(f"/api/v1/businesses/{uuid4()}").status_code == 401


def test_business_access_is_isolated_between_two_users_and_businesses(
    client: TestClient,
) -> None:
    register(client, "first@example.com")
    first_token = login(client, "first@example.com")
    first_headers = {"Authorization": f"Bearer {first_token}"}
    first_business_response = client.post(
        "/api/v1/businesses",
        json={"name": "First Private"},
        headers=first_headers,
    )
    assert first_business_response.status_code == 201
    first_business = first_business_response.json()

    register(client, "second@example.com")
    second_token = login(client, "second@example.com")
    second_headers = {"Authorization": f"Bearer {second_token}"}
    second_business_response = client.post(
        "/api/v1/businesses",
        json={"name": "Second Private"},
        headers=second_headers,
    )
    assert second_business_response.status_code == 201
    second_business = second_business_response.json()

    first_list = client.get("/api/v1/businesses", headers=first_headers)
    second_list = client.get("/api/v1/businesses", headers=second_headers)
    assert [item["id"] for item in first_list.json()] == [first_business["id"]]
    assert [item["id"] for item in second_list.json()] == [second_business["id"]]

    assert (
        client.get(f"/api/v1/businesses/{first_business['id']}", headers=second_headers).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/businesses/{second_business['id']}", headers=first_headers).status_code
        == 404
    )
    assert_response_has_no_internal_fields(first_business)
    assert_response_has_no_internal_fields(second_business)
    assert "access_token" not in first_business
    assert "access_token" not in second_business
    assert_response_has_no_internal_fields(first_list.json()[0])
    assert_response_has_no_internal_fields(second_list.json()[0])


def test_owner_admin_and_member_permission_matrix() -> None:
    owner_permissions = set(BusinessPermission)
    admin_permissions = {
        BusinessPermission.READ,
        BusinessPermission.MANAGE_SETTINGS,
        BusinessPermission.MANAGE_OPERATIONAL_RESOURCES,
        BusinessPermission.MANAGE_MEMBERS,
    }
    member_permissions = {BusinessPermission.READ}

    for permission in owner_permissions:
        assert has_business_permission(BusinessRole.OWNER, permission)
    for permission in admin_permissions:
        assert has_business_permission(BusinessRole.ADMIN, permission)
    for permission in owner_permissions - admin_permissions:
        assert not has_business_permission(BusinessRole.ADMIN, permission)
    for permission in member_permissions:
        assert has_business_permission(BusinessRole.MEMBER, permission)
    for permission in owner_permissions - member_permissions:
        assert not has_business_permission(BusinessRole.MEMBER, permission)

    assert set(roles_with_permission(BusinessPermission.READ)) == set(BusinessRole)
    assert set(roles_with_permission(BusinessPermission.TRANSFER_OWNERSHIP)) == {
        BusinessRole.OWNER
    }
    assert set(roles_with_permission(BusinessPermission.REMOVE_OWNER)) == {
        BusinessRole.OWNER
    }
    with pytest.raises(HTTPException) as denied:
        enforce_business_permission(
            BusinessRole.MEMBER,
            BusinessPermission.MANAGE_SETTINGS,
        )
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as denied:
        enforce_business_permission(
            BusinessRole.ADMIN,
            BusinessPermission.TRANSFER_OWNERSHIP,
        )
    assert denied.value.status_code == 403


def test_all_business_roles_can_read_only_businesses_they_belong_to(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    created = client.post(
        "/api/v1/businesses",
        json={"name": "Shared Business"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201
    business_id = UUID(created.json()["id"])

    register(client, "admin@example.com")
    admin_token = login(client, "admin@example.com")
    register(client, "member@example.com")
    member_token = login(client, "member@example.com")

    with session_factory() as session:
        admin = session.scalar(select(User).where(User.email == "admin@example.com"))
        member = session.scalar(select(User).where(User.email == "member@example.com"))
        assert admin is not None
        assert member is not None
        session.add_all(
            [
                BusinessMember(
                    business_id=business_id,
                    user_id=admin.id,
                    role=BusinessRole.ADMIN,
                ),
                BusinessMember(
                    business_id=business_id,
                    user_id=member.id,
                    role=BusinessRole.MEMBER,
                ),
            ]
        )
        session.commit()

    for token in (owner_token, admin_token, member_token):
        headers = {"Authorization": f"Bearer {token}"}
        listed = client.get("/api/v1/businesses", headers=headers)
        assert [item["id"] for item in listed.json()] == [str(business_id)]
        retrieved = client.get(
            f"/api/v1/businesses/{business_id}",
            headers=headers,
        )
        assert retrieved.status_code == 200


def test_business_permission_dependency_blocks_forbidden_roles(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    created = client.post(
        "/api/v1/businesses",
        json={"name": "Permission Checks"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    business_id = UUID(created.json()["id"])

    register(client, "admin@example.com")
    register(client, "member@example.com")

    with session_factory() as session:
        owner = session.scalar(select(User).where(User.email == "owner@example.com"))
        admin = session.scalar(select(User).where(User.email == "admin@example.com"))
        member = session.scalar(select(User).where(User.email == "member@example.com"))
        assert owner is not None
        assert admin is not None
        assert member is not None
        session.add_all(
            [
                BusinessMember(
                    business_id=business_id,
                    user_id=admin.id,
                    role=BusinessRole.ADMIN,
                ),
                BusinessMember(
                    business_id=business_id,
                    user_id=member.id,
                    role=BusinessRole.MEMBER,
                ),
            ]
        )
        session.commit()

        manage_settings = require_business_permission(
            BusinessPermission.MANAGE_SETTINGS
        )
        manage_members = require_business_permission(
            BusinessPermission.MANAGE_MEMBERS
        )
        transfer_ownership = require_business_permission(
            BusinessPermission.TRANSFER_OWNERSHIP
        )

        assert manage_settings(business_id, admin, session).id == business_id
        assert manage_members(business_id, admin, session).id == business_id
        with pytest.raises(HTTPException) as member_denied:
            manage_settings(business_id, member, session)
        assert member_denied.value.status_code == 403
        with pytest.raises(HTTPException) as admin_denied:
            transfer_ownership(business_id, admin, session)
        assert admin_denied.value.status_code == 403
        assert transfer_ownership(business_id, owner, session).id == business_id


def test_business_create_rejects_privilege_fields(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    for privilege_fields in (
        {"role": "owner"},
        {"role": "admin"},
        {"owner_user_id": str(uuid4())},
        {"members": [{"user_id": str(uuid4()), "role": "admin"}]},
    ):
        response = client.post(
            "/api/v1/businesses",
            json={"name": "Attempted Privilege Escalation", **privilege_fields},
            headers=headers,
        )
        assert response.status_code == 422

    with session_factory() as session:
        assert session.scalar(select(User.id).where(User.email == "person@example.com")) is not None
        assert session.scalar(select(BusinessMember.id)) is None


def test_business_and_owner_membership_creation_is_atomic(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client)
    token = login(client)

    def fail_membership_insert(*args: object) -> None:
        del args
        raise RuntimeError("simulated membership insert failure")

    event.listen(BusinessMember, "before_insert", fail_membership_insert)
    try:
        response = client.post(
            "/api/v1/businesses",
            json={"name": "Atomic Creation"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        event.remove(BusinessMember, "before_insert", fail_membership_insert)

    assert response.status_code == 500
    with session_factory() as session:
        assert session.scalar(select(Business.id)) is None
        assert session.scalar(select(BusinessMember.id)) is None


def test_duplicate_business_membership_is_rejected(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client)
    token = login(client)
    business = client.post(
        "/api/v1/businesses",
        json={"name": "Unique Membership"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    with session_factory() as session:
        original = session.scalar(
            select(BusinessMember).where(
                BusinessMember.business_id == UUID(business["id"])
            )
        )
        assert original is not None
        session.add(
            BusinessMember(
                business_id=original.business_id,
                user_id=original.user_id,
                role=BusinessRole.ADMIN,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        memberships = session.scalars(
            select(BusinessMember).where(
                BusinessMember.business_id == UUID(business["id"])
            )
        ).all()
        assert len(memberships) == 1


def test_owner_can_create_retrieve_and_update_receptionist_configuration(
    client: TestClient,
) -> None:
    register(client, "receptionist-owner@example.com")
    business = create_business(client, "receptionist-owner@example.com", "Receptionist Co")
    business_id = business["id"]
    headers = {
        "Authorization": f"Bearer {login(client, 'receptionist-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business_id}/receptionist-configuration"
    payload = {
        "assistant_name": "Avery",
        "greeting_message": "Hello, how can I help?",
        "business_timezone": "America/New_York",
    }

    created = client.post(url, json=payload, headers=headers)
    assert created.status_code == 201
    configuration = created.json()
    assert configuration["business_id"] == business_id
    assert configuration["assistant_name"] == "Avery"
    assert configuration["is_enabled"] is True
    assert_response_has_no_internal_fields(configuration)

    retrieved = client.get(url, headers=headers)
    assert retrieved.status_code == 200
    assert retrieved.json() == configuration

    updated = client.patch(
        url,
        json={
            "greeting_message": "Welcome!",
            "business_timezone": "Europe/London",
            "is_enabled": False,
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == configuration["id"]
    assert updated.json()["assistant_name"] == "Avery"
    assert updated.json()["greeting_message"] == "Welcome!"
    assert updated.json()["business_timezone"] == "Europe/London"
    assert updated.json()["is_enabled"] is False
    assert_response_has_no_internal_fields(updated.json())


def test_admin_can_create_and_update_receptionist_configuration(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client, "configuration-owner@example.com")
    business = create_business(
        client,
        "configuration-owner@example.com",
        "Admin Managed Business",
    )
    register(client, "configuration-admin@example.com")
    add_business_member(
        session_factory,
        UUID(business["id"]),
        "configuration-admin@example.com",
        BusinessRole.ADMIN,
    )
    headers = {
        "Authorization": f"Bearer {login(client, 'configuration-admin@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/receptionist-configuration"
    payload = {
        "assistant_name": "Jordan",
        "greeting_message": "How may I help?",
        "business_timezone": "UTC",
    }

    created = client.post(url, json=payload, headers=headers)
    assert created.status_code == 201
    updated = client.patch(
        url,
        json={"assistant_name": "Jordan Admin"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["assistant_name"] == "Jordan Admin"


def test_member_can_read_but_cannot_write_receptionist_configuration(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client, "member-policy-owner@example.com")
    business = create_business(
        client,
        "member-policy-owner@example.com",
        "Member Read Business",
    )
    url = f"/api/v1/businesses/{business['id']}/receptionist-configuration"
    owner_headers = {
        "Authorization": f"Bearer {login(client, 'member-policy-owner@example.com')}"
    }
    payload = {
        "assistant_name": "Sam",
        "greeting_message": "Hello.",
        "business_timezone": "UTC",
    }
    created = client.post(url, json=payload, headers=owner_headers)
    assert created.status_code == 201

    register(client, "configuration-member@example.com")
    add_business_member(
        session_factory,
        UUID(business["id"]),
        "configuration-member@example.com",
        BusinessRole.MEMBER,
    )
    member_headers = {
        "Authorization": f"Bearer {login(client, 'configuration-member@example.com')}"
    }
    assert client.get(url, headers=member_headers).status_code == 200
    assert client.post(url, json=payload, headers=member_headers).status_code == 403
    assert (
        client.patch(url, json={"assistant_name": "Changed"}, headers=member_headers).status_code
        == 403
    )


def test_receptionist_configuration_requires_authentication(
    client: TestClient,
) -> None:
    url = f"/api/v1/businesses/{uuid4()}/receptionist-configuration"
    payload = {
        "assistant_name": "Alex",
        "greeting_message": "Hello.",
        "business_timezone": "UTC",
    }
    assert client.get(url).status_code == 401
    assert client.post(url, json=payload).status_code == 401
    assert client.patch(url, json={"is_enabled": False}).status_code == 401


def test_non_member_cannot_access_another_business_configuration(
    client: TestClient,
) -> None:
    register(client, "tenant-owner@example.com")
    business = create_business(client, "tenant-owner@example.com", "Tenant Business")
    owner_headers = {
        "Authorization": f"Bearer {login(client, 'tenant-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/receptionist-configuration"
    created = client.post(
        url,
        json={
            "assistant_name": "Casey",
            "greeting_message": "Hello.",
            "business_timezone": "UTC",
        },
        headers=owner_headers,
    )
    assert created.status_code == 201

    register(client, "outsider@example.com")
    outsider_headers = {
        "Authorization": f"Bearer {login(client, 'outsider@example.com')}"
    }
    assert client.get(url, headers=outsider_headers).status_code == 404
    assert client.patch(
        url,
        json={"assistant_name": "Intruder"},
        headers=outsider_headers,
    ).status_code == 404
    assert client.post(
        url,
        json={
            "assistant_name": "Intruder",
            "greeting_message": "Hello.",
            "business_timezone": "UTC",
        },
        headers=outsider_headers,
    ).status_code == 404


def test_receptionist_configuration_duplicate_returns_conflict(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client, "duplicate-owner@example.com")
    business = create_business(client, "duplicate-owner@example.com", "Duplicate Config")
    headers = {
        "Authorization": f"Bearer {login(client, 'duplicate-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/receptionist-configuration"
    payload = {
        "assistant_name": "Morgan",
        "greeting_message": "Hello.",
        "business_timezone": "UTC",
    }
    assert client.post(url, json=payload, headers=headers).status_code == 201
    duplicate = client.post(url, json=payload, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Receptionist configuration already exists"
    }
    with session_factory() as session:
        existing = session.scalar(
            select(ReceptionistConfiguration).where(
                ReceptionistConfiguration.business_id == UUID(business["id"])
            )
        )
        assert existing is not None
        session.add(
            ReceptionistConfiguration(
                business_id=existing.business_id,
                assistant_name="Duplicate",
                greeting_message="Duplicate",
                business_timezone="UTC",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.parametrize(
    "payload",
    [
        {"assistant_name": "", "greeting_message": "Hello.", "business_timezone": "UTC"},
        {"assistant_name": "Agent", "greeting_message": " ", "business_timezone": "UTC"},
        {
            "assistant_name": "Agent",
            "greeting_message": "Hello.",
            "business_timezone": "Not/A_Timezone",
        },
        {
            "assistant_name": "x" * 121,
            "greeting_message": "Hello.",
            "business_timezone": "UTC",
        },
        {
            "assistant_name": "Agent",
            "greeting_message": "x" * 2001,
            "business_timezone": "UTC",
        },
        {
            "assistant_name": "Agent",
            "greeting_message": "Hello.",
            "business_timezone": "UTC",
            "business_id": str(uuid4()),
        },
        {
            "assistant_name": "Agent",
            "greeting_message": "Hello.",
            "business_timezone": "UTC",
            "id": str(uuid4()),
        },
        {
            "assistant_name": "Agent",
            "greeting_message": "Hello.",
            "business_timezone": "UTC",
            "role": "owner",
        },
    ],
)
def test_receptionist_configuration_rejects_invalid_and_protected_fields(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    register(client, "validation-owner@example.com")
    business = create_business(
        client,
        "validation-owner@example.com",
        "Validation Business",
    )
    headers = {
        "Authorization": f"Bearer {login(client, 'validation-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/receptionist-configuration"
    assert client.post(url, json=payload, headers=headers).status_code == 422


def test_receptionist_configuration_update_rejects_protected_fields(
    client: TestClient,
) -> None:
    register(client, "protected-update-owner@example.com")
    business = create_business(
        client,
        "protected-update-owner@example.com",
        "Protected Update Business",
    )
    headers = {
        "Authorization": f"Bearer {login(client, 'protected-update-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/receptionist-configuration"
    created = client.post(
        url,
        json={
            "assistant_name": "Protected",
            "greeting_message": "Hello.",
            "business_timezone": "UTC",
        },
        headers=headers,
    )
    assert created.status_code == 201

    invalid_updates = (
        {"id": str(uuid4())},
        {"business_id": str(uuid4())},
        {"owner_user_id": str(uuid4())},
        {"role": "owner"},
        {"business_timezone": "Not/A_Timezone"},
        {"assistant_name": None},
        {},
    )
    for payload in invalid_updates:
        assert client.patch(url, json=payload, headers=headers).status_code == 422

    current = client.get(url, headers=headers)
    assert current.status_code == 200
    assert current.json()["assistant_name"] == "Protected"


def test_receptionist_configuration_missing_returns_not_found(
    client: TestClient,
) -> None:
    register(client, "missing-config-owner@example.com")
    business = create_business(
        client,
        "missing-config-owner@example.com",
        "Missing Configuration",
    )
    headers = {
        "Authorization": f"Bearer {login(client, 'missing-config-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/receptionist-configuration"
    assert client.get(url, headers=headers).status_code == 404
    assert (
        client.patch(url, json={"is_enabled": False}, headers=headers).status_code
        == 404
    )


def test_vapi_configuration_create_retrieve_and_update(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client, "vapi-owner@example.com")
    business = create_business(client, "vapi-owner@example.com", "Vapi Business")
    register(client, "vapi-admin@example.com")
    add_business_member(
        session_factory,
        UUID(business["id"]),
        "vapi-admin@example.com",
        BusinessRole.ADMIN,
    )

    owner_headers = {
        "Authorization": f"Bearer {login(client, 'vapi-owner@example.com')}"
    }
    admin_headers = {
        "Authorization": f"Bearer {login(client, 'vapi-admin@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/vapi-configuration"
    created = client.post(
        url,
        json={
            "assistant_id": "assistant-internal-id",
            "phone_number_id": "phone-internal-id",
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    assert created.json()["assistant_id"] == "assistant-internal-id"
    assert created.json()["phone_number_id"] == "phone-internal-id"
    assert "api_key" not in created.json()
    assert "webhook_secret" not in created.json()
    assert_response_has_no_internal_fields(created.json())

    retrieved = client.get(url, headers=admin_headers)
    assert retrieved.status_code == 200
    assert retrieved.json() == created.json()
    updated = client.patch(
        url,
        json={"assistant_id": "updated-assistant-id", "is_enabled": False},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["assistant_id"] == "updated-assistant-id"
    assert updated.json()["phone_number_id"] == "phone-internal-id"
    assert updated.json()["is_enabled"] is False
    assert "api_key" not in updated.json()
    assert "webhook_secret" not in updated.json()


def test_vapi_configuration_permissions_cross_tenant_and_duplicates(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    register(client, "vapi-tenant-owner@example.com")
    business = create_business(
        client,
        "vapi-tenant-owner@example.com",
        "Vapi Tenant",
    )
    register(client, "vapi-tenant-member@example.com")
    add_business_member(
        session_factory,
        UUID(business["id"]),
        "vapi-tenant-member@example.com",
        BusinessRole.MEMBER,
    )
    register(client, "vapi-outsider@example.com")

    url = f"/api/v1/businesses/{business['id']}/vapi-configuration"
    owner_headers = {
        "Authorization": f"Bearer {login(client, 'vapi-tenant-owner@example.com')}"
    }
    member_headers = {
        "Authorization": f"Bearer {login(client, 'vapi-tenant-member@example.com')}"
    }
    outsider_headers = {
        "Authorization": f"Bearer {login(client, 'vapi-outsider@example.com')}"
    }
    payload = {"assistant_id": "tenant-assistant"}

    created = client.post(url, json=payload, headers=owner_headers)
    assert created.status_code == 201
    assert client.get(url, headers=member_headers).status_code == 200
    assert client.post(url, json={"assistant_id": "another"}, headers=member_headers).status_code == 403
    assert client.patch(url, json={"is_enabled": False}, headers=member_headers).status_code == 403
    assert client.get(url, headers=outsider_headers).status_code == 404
    assert client.post(url, json=payload, headers=outsider_headers).status_code == 404
    assert client.patch(url, json={"is_enabled": False}, headers=outsider_headers).status_code == 404
    duplicate = client.post(url, json=payload, headers=owner_headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Vapi configuration already exists"
    assert client.get(url).status_code == 401
    assert client.post(url, json=payload).status_code == 401
    assert client.patch(url, json={"is_enabled": False}).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"assistant_id": ""},
        {"assistant_id": "   "},
        {"assistant_id": "assistant id with spaces"},
        {"assistant_id": "x" * 256},
        {"assistant_id": "assistant", "phone_number_id": ""},
        {"assistant_id": "assistant", "business_id": str(uuid4())},
        {"assistant_id": "assistant", "api_key": "do-not-accept"},
    ],
)
def test_vapi_configuration_rejects_invalid_and_protected_fields(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    register(client, "vapi-validation-owner@example.com")
    business = create_business(
        client,
        "vapi-validation-owner@example.com",
        "Vapi Validation",
    )
    headers = {
        "Authorization": f"Bearer {login(client, 'vapi-validation-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/vapi-configuration"
    assert client.post(url, json=payload, headers=headers).status_code == 422


def test_vapi_configuration_rejects_duplicate_provider_identifiers(
    client: TestClient,
) -> None:
    register(client, "vapi-first-owner@example.com")
    first_business = create_business(
        client,
        "vapi-first-owner@example.com",
        "First Vapi Business",
    )
    first_headers = {
        "Authorization": f"Bearer {login(client, 'vapi-first-owner@example.com')}"
    }
    first_url = f"/api/v1/businesses/{first_business['id']}/vapi-configuration"
    assert client.post(
        first_url,
        json={"assistant_id": "shared-assistant"},
        headers=first_headers,
    ).status_code == 201

    register(client, "vapi-second-owner@example.com")
    second_business = create_business(
        client,
        "vapi-second-owner@example.com",
        "Second Vapi Business",
    )
    second_headers = {
        "Authorization": f"Bearer {login(client, 'vapi-second-owner@example.com')}"
    }
    second_url = f"/api/v1/businesses/{second_business['id']}/vapi-configuration"
    collision = client.post(
        second_url,
        json={"assistant_id": "shared-assistant"},
        headers=second_headers,
    )
    assert collision.status_code == 409
    assert collision.json()["detail"] == "Vapi identifiers are already configured"


def configure_vapi_webhook_auth(
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
) -> None:
    secret = SecretStr(token) if token is not None else None
    monkeypatch.setattr(
        "app.services.vapi_webhook_auth.get_settings",
        lambda: SimpleNamespace(VAPI_WEBHOOK_SECRET=secret),
    )


def vapi_status_payload(
    *,
    call_id: str = "call-test-1",
    assistant_id: str | None = "assistant-webhook",
    phone_number_id: str | None = "phone-webhook",
    call_status: str = "ended",
) -> dict[str, object]:
    call: dict[str, object] = {"id": call_id}
    if assistant_id is not None:
        call["assistantId"] = assistant_id
    if phone_number_id is not None:
        call["phoneNumberId"] = phone_number_id
    return {"message": {"type": "status-update", "call": call, "status": call_status}}


def test_vapi_webhook_requires_configured_bearer_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, None)
    url = "/api/v1/integrations/vapi/webhook"
    payload = vapi_status_payload()
    assert client.post(url, json=payload).status_code == 503

    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, json=payload, headers={"Authorization": "Basic wrong"}).status_code == 401
    assert (
        client.post(
            url,
            json=payload,
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )


def test_vapi_webhook_accepts_documented_status_update_without_side_effects(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    register(client, "webhook-owner@example.com")
    business = create_business(client, "webhook-owner@example.com", "Webhook Business")
    configuration_url = (
        f"/api/v1/businesses/{business['id']}/vapi-configuration"
    )
    owner_headers = {
        "Authorization": f"Bearer {login(client, 'webhook-owner@example.com')}"
    }
    assert client.post(
        configuration_url,
        json={
            "assistant_id": "assistant-webhook",
            "phone_number_id": "phone-webhook",
        },
        headers=owner_headers,
    ).status_code == 201

    valid_payload = json.dumps(vapi_status_payload()).encode()
    webhook_response = client.post(
        "/api/v1/integrations/vapi/webhook",
        content=valid_payload,
        headers={
            "Authorization": "Bearer test-webhook-token",
            "Content-Type": "application/json",
        },
    )
    assert webhook_response.status_code == 202
    assert webhook_response.json() == {"status": "accepted"}

    with session_factory() as session:
        assert session.scalar(select(VapiConfiguration).where(
            VapiConfiguration.business_id == UUID(business["id"])
        )) is not None
        assert session.scalar(select(BusinessMember.id)) is not None
        assert session.scalar(select(VapiConfiguration.id).where(
            VapiConfiguration.assistant_id == "assistant-webhook"
        )) is not None


def test_vapi_webhook_rejects_oversized_stream_without_content_length(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    chunks = iter([b"x" * (64 * 1024 + 1)])
    response = client.post(
        "/api/v1/integrations/vapi/webhook",
        content=chunks,
        headers={"Authorization": "Bearer test-webhook-token"},
    )
    assert response.status_code == 413


def test_vapi_webhook_validates_events_and_rejects_unknown_mappings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    webhook_url = "/api/v1/integrations/vapi/webhook"
    headers = {"Authorization": "Bearer test-webhook-token"}

    assert client.post(webhook_url, content="{", headers=headers).status_code == 400
    malformed = client.post(
        webhook_url,
        json={"message": {"type": "status-update", "status": "ended", "call": {}}},
        headers=headers,
    )
    assert malformed.status_code == 422
    invalid_status = client.post(
        webhook_url,
        json=vapi_status_payload(call_status="unknown"),
        headers=headers,
    )
    assert invalid_status.status_code == 422
    unsupported = client.post(
        webhook_url,
        json={"message": {"type": "end-of-call-report", "call": {}}},
        headers=headers,
    )
    assert unsupported.status_code == 202
    assert unsupported.json() == {"status": "ignored"}
    unknown = client.post(
        webhook_url,
        json=vapi_status_payload(
            assistant_id="unknown-assistant",
            phone_number_id="unknown-phone",
        ),
        headers=headers,
    )
    assert unknown.status_code == 404


def test_vapi_webhook_rejects_mismatched_identifier_mapping(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    register(client, "mapping-owner-one@example.com")
    first_business = create_business(
        client,
        "mapping-owner-one@example.com",
        "Mapping One",
    )
    first_headers = {
        "Authorization": f"Bearer {login(client, 'mapping-owner-one@example.com')}"
    }
    assert client.post(
        f"/api/v1/businesses/{first_business['id']}/vapi-configuration",
        json={"assistant_id": "assistant-one", "phone_number_id": "phone-one"},
        headers=first_headers,
    ).status_code == 201

    register(client, "mapping-owner-two@example.com")
    second_business = create_business(
        client,
        "mapping-owner-two@example.com",
        "Mapping Two",
    )
    second_headers = {
        "Authorization": f"Bearer {login(client, 'mapping-owner-two@example.com')}"
    }
    assert client.post(
        f"/api/v1/businesses/{second_business['id']}/vapi-configuration",
        json={"assistant_id": "assistant-two", "phone_number_id": "phone-two"},
        headers=second_headers,
    ).status_code == 201

    response = client.post(
        "/api/v1/integrations/vapi/webhook",
        json=vapi_status_payload(
            assistant_id="assistant-one",
            phone_number_id="phone-two",
        ),
        headers={"Authorization": "Bearer test-webhook-token"},
    )
    assert response.status_code == 404


def test_existing_health_endpoints(client: TestClient) -> None:
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code in (200, 503)
    assert ready.json()["status"] in ("ready", "not_ready")
