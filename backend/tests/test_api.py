import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import require_business_permission
from app.core.config import Settings, get_settings
from app.core.security import verify_password
from app.db.session import Base, get_db
from app.main import app
from app.models.business import Business, BusinessMember, BusinessRole
from app.models.receptionist_configuration import ReceptionistConfiguration
from app.models.user import User
from app.models.vapi_call import VapiCall, VapiCallEvent
from app.models.vapi_configuration import VapiConfiguration
from app.services.business_authorization import (
    BusinessPermission,
    enforce_business_permission,
    has_business_permission,
    roles_with_permission,
)
from app.services.vapi_call_events import (
    _record_failed_attempt,
    process_pending_vapi_call_events,
    recover_pending_vapi_call_events,
)
from app.services.vapi_webhook_auth import verify_vapi_webhook_authorization


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


def test_settings_reject_empty_webhook_secret_and_unsafe_cors_origin() -> None:
    required = {"_env_file": None, "DB_PASSWORD": "db-test", "SECRET_KEY": "s" * 32}
    with pytest.raises(ValidationError):
        Settings(**required, VAPI_WEBHOOK_SECRET=" ")
    with pytest.raises(ValidationError):
        Settings(**required, FRONTEND_ORIGIN="*")
    with pytest.raises(ValidationError):
        Settings(
            **required,
            APP_ENV="production",
            DEBUG=True,
            FRONTEND_ORIGIN="https://frontend.example.test",
        )


def test_validation_errors_do_not_echo_submitted_values(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test Person",
            "email": "not-an-email",
            "password": "do-not-echo-this-password",
        },
        headers={"X-Request-ID": "validation-request-123"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "request_id": "validation-request-123",
    }
    assert "do-not-echo-this-password" not in response.text
    assert response.headers["X-Request-ID"] == "validation-request-123"


def test_unhandled_errors_return_generic_response_and_request_id(
    client: TestClient,
) -> None:
    def raise_internal_error() -> None:
        raise RuntimeError("internal database connection details")

    app.add_api_route("/_test/internal-error", raise_internal_error, methods=["GET"])
    try:
        with TestClient(app, raise_server_exceptions=False) as error_client:
            response = error_client.get(
                "/_test/internal-error",
                headers={"X-Request-ID": "internal-request-456"},
            )
    finally:
        app.router.routes[:] = [
            route
            for route in app.router.routes
            if getattr(route, "path", None) != "/_test/internal-error"
        ]

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "request_id": "internal-request-456",
    }
    assert "database connection details" not in response.text
    assert response.headers["X-Request-ID"] == "internal-request-456"


def test_development_cors_allows_only_explicit_localhost_aliases() -> None:
    required = {"_env_file": None, "DB_PASSWORD": "db-test", "SECRET_KEY": "s" * 32}
    settings = Settings(
        **required,
        APP_ENV="development",
        FRONTEND_ORIGIN="http://localhost:5173",
    )
    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    production_settings = Settings(
        **required,
        APP_ENV="production",
        FRONTEND_ORIGIN="https://frontend.example.test",
    )
    assert production_settings.cors_allowed_origins == [
        "https://frontend.example.test"
    ]


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


def test_user_can_update_profile_and_change_password(client: TestClient) -> None:
    register(client)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    updated = client.patch(
        "/api/v1/auth/me",
        json={"full_name": "Updated Person", "email": "updated@example.com"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Updated Person"
    assert updated.json()["email"] == "updated@example.com"
    assert "password_hash" not in updated.json()

    assert client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "wrong-password",
            "new_password": "another-long-password",
        },
        headers=headers,
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "long-password",
            "new_password": "long-password",
        },
        headers=headers,
    ).status_code == 422
    changed = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "long-password",
            "new_password": "another-long-password",
        },
        headers=headers,
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "updated@example.com", "password": "long-password"},
    ).status_code == 401
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "updated@example.com", "password": "another-long-password"},
    )
    assert new_login.status_code == 200
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_login.json()['access_token']}"},
    ).status_code == 200


def test_user_profile_rejects_duplicate_email_and_empty_updates(
    client: TestClient,
) -> None:
    register(client)
    register(client, "other@example.com")
    headers = {"Authorization": f"Bearer {login(client)}"}
    duplicate = client.patch(
        "/api/v1/auth/me",
        json={"email": "other@example.com"},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert client.patch("/api/v1/auth/me", json={}, headers=headers).status_code == 422
    assert (
        client.patch(
            "/api/v1/auth/me",
            json={"full_name": "   "},
            headers=headers,
        ).status_code
        == 422
    )


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


def test_business_update_and_member_management_enforce_roles(
    client: TestClient,
) -> None:
    register(client, "manager-owner@example.com")
    owner_token = login(client, "manager-owner@example.com")
    created = client.post(
        "/api/v1/businesses",
        json={"name": "Before Update"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201
    business_id = created.json()["id"]
    business_url = f"/api/v1/businesses/{business_id}"
    members_url = f"{business_url}/members"

    updated = client.patch(
        business_url,
        json={"name": "After Update"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "After Update"

    register(client, "manager-admin@example.com")
    register(client, "managed-member@example.com")
    added_admin = client.post(
        members_url,
        json={"email": "manager-admin@example.com", "role": "admin"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert added_admin.status_code == 201
    added_member = client.post(
        members_url,
        json={"email": "managed-member@example.com", "role": "member"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert added_member.status_code == 201
    assert len(client.get(members_url, headers={"Authorization": f"Bearer {owner_token}"}).json()) == 3

    admin_headers = {"Authorization": f"Bearer {login(client, 'manager-admin@example.com')}"}
    member_id = added_member.json()["user_id"]
    assert client.patch(
        f"{members_url}/{member_id}",
        json={"role": "admin"},
        headers=admin_headers,
    ).status_code == 403
    assert client.delete(
        f"{members_url}/{added_admin.json()['user_id']}",
        headers=admin_headers,
    ).status_code == 403
    assert client.patch(
        f"{members_url}/{added_admin.json()['user_id']}",
        json={"role": "member"},
        headers={"Authorization": f"Bearer {owner_token}"},
    ).status_code == 200
    assert client.delete(
        f"{members_url}/{member_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    ).status_code == 204
    assert client.delete(
        f"{members_url}/{created.json()['owner_user_id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    ).status_code == 409


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
        BusinessPermission.READ_CALLS,
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
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": "http://localhost:5173",
            },
        )
    finally:
        event.remove(BusinessMember, "before_insert", fail_membership_insert)

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
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
    timestamp: str | None = None,
    call_type: str | None = None,
) -> dict[str, object]:
    call: dict[str, object] = {"id": call_id}
    if assistant_id is not None:
        call["assistantId"] = assistant_id
    if phone_number_id is not None:
        call["phoneNumberId"] = phone_number_id
    if call_type is not None:
        call["type"] = call_type
    message: dict[str, object] = {
        "type": "status-update",
        "call": call,
        "status": call_status,
    }
    if timestamp is not None:
        message["timestamp"] = timestamp
    return {"message": message}


def configure_vapi_business(
    client: TestClient,
    email: str,
    business_name: str,
    assistant_id: str,
    phone_number_id: str | None = None,
) -> tuple[dict[str, object], dict[str, str]]:
    register(client, email)
    business = create_business(client, email, business_name)
    headers = {"Authorization": f"Bearer {login(client, email)}"}
    payload: dict[str, object] = {"assistant_id": assistant_id}
    if phone_number_id is not None:
        payload["phone_number_id"] = phone_number_id
    configured = client.post(
        f"/api/v1/businesses/{business['id']}/vapi-configuration",
        json=payload,
        headers=headers,
    )
    assert configured.status_code == 201
    return business, headers


def test_vapi_webhook_requires_configured_bearer_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, None)
    url = "/api/v1/integrations/vapi/webhook"
    payload = vapi_status_payload()
    assert client.post(url, json=payload).status_code == 503

    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    caplog.set_level(30, logger="app.services.vapi_webhook_auth")
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
    assert client.post(
        url,
        json=payload,
        headers={"Authorization": "Bearer "},
    ).status_code == 401
    verify_vapi_webhook_authorization("Bearer   test-webhook-token")

    failure = next(
        record
        for record in reversed(caplog.records)
        if record.name == "app.services.vapi_webhook_auth"
    )
    assert failure.authorization_present is True
    assert failure.bearer_scheme_received is True
    assert failure.credential_matches_expected is False
    assert "test-webhook-token" not in caplog.text


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
    assert webhook_response.json() == {"status": "processed"}

    with session_factory() as session:
        assert session.scalar(select(VapiConfiguration).where(
            VapiConfiguration.business_id == UUID(business["id"])
        )) is not None
        assert session.scalar(select(BusinessMember.id)) is not None
        assert session.scalar(select(VapiConfiguration.id).where(
            VapiConfiguration.assistant_id == "assistant-webhook"
        )) is not None
        call = session.scalar(select(VapiCall).where(VapiCall.vapi_call_id == "call-test-1"))
        assert call is not None
        assert call.business_id == UUID(business["id"])
        assert call.status == "ended"
        event_record = session.scalar(
            select(VapiCallEvent).where(
                VapiCallEvent.call_record_id == call.id,
                VapiCallEvent.event_status == "ended",
            )
        )
        assert event_record is not None
        assert event_record.outcome == "applied"


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
    session_factory: sessionmaker[Session],
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
        json={"message": {"type": "assistant-request", "call": {}}},
        headers=headers,
    )
    assert unsupported.status_code == 202
    assert unsupported.json() == {"status": "ignored"}
    with session_factory() as session:
        assert session.scalar(select(VapiCall.id)) is None
        assert session.scalar(select(VapiCallEvent.id)) is None
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


def test_vapi_webhook_deduplicates_stages_and_keeps_terminal_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    business, _ = configure_vapi_business(
        client,
        "call-state-owner@example.com",
        "Call State",
        "state-assistant",
        "state-phone",
    )
    url = "/api/v1/integrations/vapi/webhook"
    headers = {"Authorization": "Bearer test-webhook-token"}

    start = vapi_status_payload(
        call_id="stateful-call",
        assistant_id="state-assistant",
        phone_number_id="state-phone",
        call_status="in-progress",
        timestamp="2026-10-21T10:00:00Z",
    )
    assert client.post(url, json=start, headers=headers).json() == {
        "status": "processed"
    }
    duplicate = client.post(
        url,
        json={
            **vapi_status_payload(
                call_id="stateful-call",
                assistant_id="state-assistant",
                phone_number_id="state-phone",
                call_status="in-progress",
                timestamp="2026-10-21T10:00:01Z",
                call_type="inboundPhoneCall",
            ),
        },
        headers=headers,
    )
    assert duplicate.status_code == 202
    assert duplicate.json() == {"status": "duplicate"}

    ended = vapi_status_payload(
        call_id="stateful-call",
        assistant_id="state-assistant",
        phone_number_id="state-phone",
        call_status="ended",
        timestamp="2026-10-21T10:02:00Z",
    )
    assert client.post(url, json=ended, headers=headers).json() == {
        "status": "processed"
    }
    stale = vapi_status_payload(
        call_id="stateful-call",
        assistant_id="state-assistant",
        phone_number_id="state-phone",
        call_status="ringing",
        timestamp="2026-10-21T10:01:00Z",
    )
    assert client.post(url, json=stale, headers=headers).json() == {"status": "stale"}

    with session_factory() as session:
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == "stateful-call")
        )
        assert call is not None
        assert call.business_id == UUID(business["id"])
        assert call.status == "ended"
        assert call.direction == "inbound"
        events = session.scalars(
            select(VapiCallEvent).where(VapiCallEvent.vapi_call_id == "stateful-call")
        ).all()
        assert len(events) == 3
        assert {record.outcome for record in events} == {"applied", "stale"}
        session.add(
            VapiCallEvent(
                business_id=call.business_id,
                call_record_id=call.id,
                vapi_call_id=call.vapi_call_id,
                assistant_id=call.assistant_id,
                phone_number_id=call.phone_number_id,
                event_type="status-update",
                event_status="ended",
                processing_status="processed",
                processing_attempt_count=1,
                outcome="applied",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_vapi_webhook_rejects_naive_provider_timestamp(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    payload = vapi_status_payload(
        timestamp="2026-10-21T10:00:00",
    )
    response = client.post(
        "/api/v1/integrations/vapi/webhook",
        json=payload,
        headers={"Authorization": "Bearer test-webhook-token"},
    )
    assert response.status_code == 422
    invalid_call_type = vapi_status_payload(call_type="not-a-vapi-call-type")
    assert client.post(
        "/api/v1/integrations/vapi/webhook",
        json=invalid_call_type,
        headers={"Authorization": "Bearer test-webhook-token"},
    ).status_code == 422


def test_vapi_end_of_call_report_persists_call_details_idempotently(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    business, headers = configure_vapi_business(
        client,
        "report-owner@example.com",
        "Call Report",
        "report-assistant",
        "report-phone",
    )
    payload = {
        "message": {
            "type": "end-of-call-report",
            "timestamp": "2026-10-21T10:02:00Z",
            "endedReason": "customer-ended-call",
            "call": {
                "id": "reported-call",
                "assistantId": "report-assistant",
                "phoneNumberId": "report-phone",
                "type": "inboundPhoneCall",
                "customer": {"number": "+15551234567"},
                "phoneNumber": {"number": "+15557654321"},
                "startedAt": "2026-10-21T10:00:00Z",
                "endedAt": "2026-10-21T10:02:00Z",
                "duration": 120,
            },
            "artifact": {
                "transcript": "Caller: hello\\nAssistant: how can I help?",
                "recording": {
                    "mono": {
                        "combinedUrl": "https://recordings.example.test/call.wav"
                    }
                },
            },
        }
    }
    url = "/api/v1/integrations/vapi/webhook"
    response = client.post(url, json=payload, headers={"Authorization": "Bearer test-webhook-token"})
    assert response.status_code == 202
    assert response.json() == {"status": "processed"}
    duplicate = client.post(
        url,
        json=payload,
        headers={"Authorization": "Bearer test-webhook-token"},
    )
    assert duplicate.status_code == 202
    assert duplicate.json() == {"status": "duplicate"}

    with session_factory() as session:
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == "reported-call")
        )
        assert call is not None
        assert call.business_id == UUID(business["id"])
        assert call.status == "ended"
        assert call.direction == "inbound"
        assert call.caller_number == "+15551234567"
        assert call.recipient_number == "+15557654321"
        assert call.duration_seconds == 120
        assert call.transcript == "Caller: hello\\nAssistant: how can I help?"
        assert call.recording_url == "https://recordings.example.test/call.wav"
        assert call.ended_reason == "customer-ended-call"
        event_record = session.scalar(
            select(VapiCallEvent).where(
                VapiCallEvent.vapi_call_id == "reported-call",
                VapiCallEvent.event_type == "end-of-call-report",
            )
        )
        assert event_record is not None
        assert event_record.provider_timestamp == datetime(2026, 10, 21, 10, 2)

    calls = client.get(
        f"/api/v1/businesses/{business['id']}/calls?caller=1555123",
        headers=headers,
    )
    assert calls.status_code == 200
    assert calls.json()["total"] == 1
    detail = client.get(
        f"/api/v1/businesses/{business['id']}/calls/{calls.json()['items'][0]['id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["transcript"] == (
        "Caller: hello\\nAssistant: how can I help?"
    )
    assert detail.json()["recording_url"] == "https://recordings.example.test/call.wav"


def test_vapi_end_of_call_report_rejects_invalid_duration(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    response = client.post(
        "/api/v1/integrations/vapi/webhook",
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {
                    "id": "invalid-duration-call",
                    "assistantId": "assistant-webhook",
                    "duration": -1,
                },
            }
        },
        headers={"Authorization": "Bearer test-webhook-token"},
    )
    assert response.status_code == 422


def test_failed_end_of_call_report_recovers_saved_metadata(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    business, owner_headers = configure_vapi_business(
        client,
        "report-recovery-owner@example.com",
        "Report Recovery",
        "report-recovery-assistant",
        "report-recovery-phone",
    )
    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "recoverable-report",
                "assistantId": "report-recovery-assistant",
                "phoneNumberId": "report-recovery-phone",
                "type": "inboundPhoneCall",
            },
            "artifact": {"transcript": "Persist this before processing."},
        }
    }
    original_commit = Session.commit
    commit_count = 0

    def fail_processing_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise SQLAlchemyError("simulated report processing failure")
        original_commit(session)

    with monkeypatch.context() as context:
        context.setattr(Session, "commit", fail_processing_commit)
        failed = client.post(
            "/api/v1/integrations/vapi/webhook",
            json=payload,
            headers={"Authorization": "Bearer test-webhook-token"},
        )
    assert failed.status_code == 503

    with session_factory() as session:
        receipt = session.scalar(
            select(VapiCallEvent).where(
                VapiCallEvent.vapi_call_id == "recoverable-report",
                VapiCallEvent.event_type == "end-of-call-report",
            )
        )
        assert receipt is not None
        assert receipt.processing_status == "pending"
        assert receipt.transcript == "Persist this before processing."
        receipt.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        assert recover_pending_vapi_call_events(session) == 1
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == "recoverable-report")
        )
        assert call is not None
        assert call.business_id == UUID(business["id"])
        assert call.transcript == "Persist this before processing."

    duplicate = client.post(
        "/api/v1/integrations/vapi/webhook",
        json=payload,
        headers={"Authorization": "Bearer test-webhook-token"},
    )
    assert duplicate.status_code == 202
    assert duplicate.json() == {"status": "duplicate"}
    details = client.get(
        f"/api/v1/businesses/{business['id']}/calls/{call.id}",
        headers=owner_headers,
    )
    assert details.status_code == 200
    assert details.json()["transcript"] == "Persist this before processing."


def test_vapi_webhook_maps_phone_only_and_rejects_disabled_or_cross_business_call(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    first_business, _ = configure_vapi_business(
        client,
        "phone-only-owner@example.com",
        "Phone Only",
        "phone-only-assistant",
        "phone-only-id",
    )
    url = "/api/v1/integrations/vapi/webhook"
    headers = {"Authorization": "Bearer test-webhook-token"}
    phone_event = vapi_status_payload(
        call_id="phone-only-call",
        assistant_id=None,
        phone_number_id="phone-only-id",
        call_status="queued",
    )
    assert client.post(url, json=phone_event, headers=headers).json() == {
        "status": "processed"
    }
    with session_factory() as session:
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == "phone-only-call")
        )
        assert call is not None
        assert call.business_id == UUID(first_business["id"])
        assert call.assistant_id == "phone-only-assistant"

        configuration = session.scalar(
            select(VapiConfiguration).where(
                VapiConfiguration.business_id == UUID(first_business["id"])
            )
        )
        assert configuration is not None
        configuration.is_enabled = False
        session.commit()

    disabled = client.post(
        url,
        json=vapi_status_payload(
            call_id="disabled-call",
            assistant_id="phone-only-assistant",
            phone_number_id="phone-only-id",
        ),
        headers=headers,
    )
    assert disabled.status_code == 404

    second_business, _ = configure_vapi_business(
        client,
        "different-vapi-owner@example.com",
        "Different Vapi",
        "different-assistant",
        "different-phone",
    )
    cross_business = client.post(
        url,
        json=vapi_status_payload(
            call_id="phone-only-call",
            assistant_id="different-assistant",
            phone_number_id="different-phone",
        ),
        headers=headers,
    )
    assert cross_business.status_code == 404
    assert second_business["id"] != first_business["id"]
    with session_factory() as session:
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == "phone-only-call")
        )
        assert call is not None
        assert call.business_id == UUID(first_business["id"])
        conflicting_event = session.scalar(
            select(VapiCallEvent).where(
                VapiCallEvent.business_id == UUID(second_business["id"]),
                VapiCallEvent.vapi_call_id == "phone-only-call",
            )
        )
        assert conflicting_event is not None
        assert conflicting_event.processing_status == "failed"
        assert conflicting_event.safe_error_code == "call_business_conflict"
        assert conflicting_event.call_record_id is None


def test_vapi_webhook_database_failure_is_not_acknowledged_and_can_be_retried(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    configure_vapi_business(
        client,
        "retry-owner@example.com",
        "Retry Business",
        "retry-assistant",
        "retry-phone",
    )
    payload = vapi_status_payload(
        call_id="retry-call",
        assistant_id="retry-assistant",
        phone_number_id="retry-phone",
        call_status="queued",
    )
    headers = {"Authorization": "Bearer test-webhook-token"}
    original_commit = Session.commit
    commit_count = 0

    def fail_processing_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise SQLAlchemyError("simulated database failure")
        original_commit(session)

    with monkeypatch.context() as context:
        context.setattr(Session, "commit", fail_processing_commit)
        failed = client.post(
            "/api/v1/integrations/vapi/webhook",
            json=payload,
            headers=headers,
        )
        assert failed.status_code == 503
        assert failed.json()["detail"] == "Webhook processing temporarily unavailable"

    with session_factory() as session:
        assert session.scalar(
            select(VapiCall.id).where(VapiCall.vapi_call_id == "retry-call")
        ) is None
        pending_event = session.scalar(
            select(VapiCallEvent).where(VapiCallEvent.vapi_call_id == "retry-call")
        )
        assert pending_event is not None
        assert pending_event.processing_status == "pending"
        assert pending_event.processing_attempt_count == 1
        assert pending_event.next_attempt_at is not None
        assert recover_pending_vapi_call_events(session) == 0
        pending_event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    retried = client.post(
        "/api/v1/integrations/vapi/webhook",
        json=payload,
        headers=headers,
    )
    assert retried.status_code == 202
    assert retried.json() == {"status": "processed"}
    with session_factory() as session:
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == "retry-call")
        )
        event_record = session.scalar(
            select(VapiCallEvent).where(VapiCallEvent.vapi_call_id == "retry-call")
        )
        assert call is not None and call.status == "queued"
        assert event_record is not None
        assert event_record.processing_status == "processed"
        assert event_record.processing_attempt_count == 2


def test_recovery_marks_receipt_terminal_after_max_attempts(
    session_factory: sessionmaker[Session],
) -> None:
    user_id = uuid4()
    business_id = uuid4()
    with session_factory() as session:
        session.add(
            User(
                id=user_id,
                full_name="Retry Owner",
                email="terminal-retry-owner@example.com",
                password_hash="test-hash",
            )
        )
        session.flush()
        session.add(Business(id=business_id, name="Retry Business", owner_user_id=user_id))
        session.flush()
        event = VapiCallEvent(
            business_id=business_id,
            vapi_call_id="terminal-retry-call",
            assistant_id="retry-assistant",
            event_type="status-update",
            event_status="queued",
            processing_status="pending",
        )
        session.add(event)
        session.commit()
        event_id = event.id

        _record_failed_attempt(
            event_id,
            session,
            event_type="status-update",
            settings=Settings(
                DB_PASSWORD="test-database-password",
                SECRET_KEY="test-secret-key-that-is-at-least-thirty-two-characters",
                VAPI_RECOVERY_MAX_ATTEMPTS=1,
            ),
        )

        failed_event = session.get(VapiCallEvent, event_id)
        assert failed_event is not None
        assert failed_event.processing_status == "failed"
        assert failed_event.processing_attempt_count == 1
        assert failed_event.next_attempt_at is None
        assert failed_event.safe_error_code == "max_attempts_exceeded"
        batch = process_pending_vapi_call_events(session)
        assert batch.recovered_count == 0
        assert batch.batch_size == 0


def test_pending_call_event_is_not_recovered_by_application_startup(
    session_factory: sessionmaker[Session],
) -> None:
    user_id = uuid4()
    business_id = uuid4()
    with session_factory() as session:
        session.add(
            User(
                id=user_id,
                full_name="Recovery Owner",
                email="recovery-owner@example.com",
                password_hash="test-hash",
            )
        )
        session.add(
            Business(
                id=business_id,
                name="Recovery Business",
                owner_user_id=user_id,
            )
        )
        session.flush()
        session.add(
            BusinessMember(
                business_id=business_id,
                user_id=user_id,
                role=BusinessRole.OWNER,
            )
        )
        session.add(
            VapiConfiguration(
                business_id=business_id,
                assistant_id="recovery-assistant",
                phone_number_id="recovery-phone",
            )
        )
        pending = VapiCallEvent(
            business_id=business_id,
            vapi_call_id="recovery-call",
            assistant_id="recovery-assistant",
            phone_number_id="recovery-phone",
            event_type="status-update",
            event_status="queued",
            processing_status="pending",
            processing_attempt_count=0,
        )
        session.add(pending)
        session.commit()
        pending_id = pending.id

    with TestClient(app):
        pass

    with session_factory() as session:
        recovered = session.get(VapiCallEvent, pending_id)
        call = session.scalar(
            select(VapiCall).where(VapiCall.vapi_call_id == "recovery-call")
        )
        assert recovered is not None
        assert recovered.processing_status == "pending"
        assert recovered.processing_attempt_count == 0
        assert call is None


def test_recovery_continues_after_one_receipt_fails(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    business_id = uuid4()
    with session_factory() as session:
        session.add(
            User(
                id=user_id,
                full_name="Recovery Owner",
                email="recovery-batch-owner@example.com",
                password_hash="test-hash",
            )
        )
        session.add(
            Business(
                id=business_id,
                name="Recovery Batch Business",
                owner_user_id=user_id,
            )
        )
        session.flush()
        failed_event = VapiCallEvent(
            business_id=business_id,
            vapi_call_id="recovery-failure-call",
            assistant_id="recovery-assistant",
            event_status="queued",
            received_at=datetime(2026, 1, 1, tzinfo=UTC),
            processing_status="pending",
        )
        later_event = VapiCallEvent(
            business_id=business_id,
            vapi_call_id="recovery-later-call",
            assistant_id="recovery-assistant",
            event_status="queued",
            received_at=datetime(2026, 1, 2, tzinfo=UTC),
            processing_status="pending",
        )
        session.add_all([failed_event, later_event])
        session.commit()
        failed_event_id = failed_event.id
        later_event_id = later_event.id

    original_commit = Session.commit
    failure_injected = False

    def fail_one_receipt(session: Session) -> None:
        nonlocal failure_injected
        if not failure_injected and any(
            isinstance(record, VapiCallEvent)
            and record.vapi_call_id == "recovery-failure-call"
            and record.processing_status == "processed"
            for record in session.dirty
        ):
            failure_injected = True
            raise SQLAlchemyError("simulated receipt processing failure")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_one_receipt)
    with session_factory() as session:
        assert recover_pending_vapi_call_events(session, limit=2) == 1

    with session_factory() as session:
        failed_event = session.get(VapiCallEvent, failed_event_id)
        later_event = session.get(VapiCallEvent, later_event_id)
        assert failed_event is not None
        assert failed_event.processing_status == "pending"
        assert failed_event.processing_attempt_count == 1
        assert later_event is not None
        assert later_event.processing_status == "processed"
        assert later_event.processing_attempt_count == 1
        assert session.scalar(
            select(VapiCall.id).where(
                VapiCall.vapi_call_id == "recovery-later-call"
            )
        ) is not None


def test_webhook_does_not_run_pending_event_recovery(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    business, _ = configure_vapi_business(
        client,
        "no-sync-recovery@example.com",
        "No Synchronous Recovery",
        "no-sync-assistant",
    )
    with session_factory() as session:
        pending = VapiCallEvent(
            business_id=UUID(business["id"]),
            vapi_call_id="older-pending-call",
            assistant_id="no-sync-assistant",
            event_status="queued",
            processing_status="pending",
        )
        session.add(pending)
        session.commit()
        pending_id = pending.id

    response = client.post(
        "/api/v1/integrations/vapi/webhook",
        json=vapi_status_payload(
            call_id="new-webhook-call",
            assistant_id="no-sync-assistant",
            phone_number_id=None,
            call_status="queued",
        ),
        headers={"Authorization": "Bearer test-webhook-token"},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "processed"}
    with session_factory() as session:
        pending = session.get(VapiCallEvent, pending_id)
        assert pending is not None
        assert pending.processing_status == "pending"
        assert session.scalar(
            select(VapiCall.id).where(
                VapiCall.vapi_call_id == "new-webhook-call"
            )
        ) is not None


def test_call_history_is_authorized_paginated_filtered_and_private(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_vapi_webhook_auth(monkeypatch, "test-webhook-token")
    business, owner_headers = configure_vapi_business(
        client,
        "history-owner@example.com",
        "History Business",
        "history-assistant",
        "history-phone",
    )
    other_business, _ = configure_vapi_business(
        client,
        "history-other-owner@example.com",
        "Other History Business",
        "other-history-assistant",
        "other-history-phone",
    )
    webhook_url = "/api/v1/integrations/vapi/webhook"
    webhook_headers = {"Authorization": "Bearer test-webhook-token"}
    for call_id, call_status in (
        ("history-call-1", "queued"),
        ("history-call-2", "ended"),
    ):
        response = client.post(
            webhook_url,
            json=vapi_status_payload(
                call_id=call_id,
                assistant_id="history-assistant",
                phone_number_id="history-phone",
                call_status=call_status,
            ),
            headers=webhook_headers,
        )
        assert response.status_code == 202

    foreign_response = client.post(
        webhook_url,
        json=vapi_status_payload(
            call_id="foreign-history-call",
            assistant_id="other-history-assistant",
            phone_number_id="other-history-phone",
        ),
        headers=webhook_headers,
    )
    assert foreign_response.status_code == 202

    url = f"/api/v1/businesses/{business['id']}/calls"
    listed = client.get(url, headers=owner_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert listed.json()["limit"] == 50
    assert {
        item["vapi_call_id"] for item in listed.json()["items"]
    } == {"history-call-1", "history-call-2"}
    assert not {
        "transcript",
        "recording_url",
        "authorization",
        "webhook_secret",
        "processing_error",
    }.intersection(listed.json()["items"][0])

    filtered = client.get(
        f"{url}?status=queued&limit=1&sort_by=created_at&sort_order=asc",
        headers=owner_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["vapi_call_id"] == "history-call-1"

    call_id = listed.json()["items"][0]["id"]
    own_call = client.get(f"{url}/{call_id}", headers=owner_headers)
    assert own_call.status_code == 200
    register(client, "history-member@example.com")
    add_business_member(
        session_factory,
        UUID(business["id"]),
        "history-member@example.com",
        BusinessRole.MEMBER,
    )
    member_headers = {
        "Authorization": f"Bearer {login(client, 'history-member@example.com')}"
    }
    assert client.get(url, headers=member_headers).status_code == 403
    assert client.get(f"{url}/{call_id}", headers=member_headers).status_code == 403
    foreign_call = client.get(
        f"/api/v1/businesses/{other_business['id']}/calls/{call_id}",
        headers=owner_headers,
    )
    assert foreign_call.status_code == 404
    assert client.get(url).status_code == 401
    assert client.get(f"{url}?limit=101", headers=owner_headers).status_code == 422
    assert client.get(f"{url}?status=unknown", headers=owner_headers).status_code == 422
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    future_filter = client.get(
        url,
        params={"created_after": future},
        headers=owner_headers,
    )
    assert future_filter.status_code == 200
    assert future_filter.json()["total"] == 0


def test_call_history_validates_date_ranges_and_user_membership(
    client: TestClient,
) -> None:
    register(client, "date-range-owner@example.com")
    business = create_business(
        client,
        "date-range-owner@example.com",
        "Date Range Business",
    )
    headers = {
        "Authorization": f"Bearer {login(client, 'date-range-owner@example.com')}"
    }
    url = f"/api/v1/businesses/{business['id']}/calls"
    start = datetime(2026, 10, 21, tzinfo=UTC)
    later = start + timedelta(hours=1)
    reversed_range = client.get(
        url,
        params={
            "created_after": later.isoformat(),
            "created_before": start.isoformat(),
        },
        headers=headers,
    )
    assert reversed_range.status_code == 422
    naive_date = client.get(
        url,
        params={"created_after": "2026-10-21T00:00:00"},
        headers=headers,
    )
    assert naive_date.status_code == 422


def test_existing_health_endpoints(client: TestClient) -> None:
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code in (200, 503)
    assert ready.json()["status"] in ("ready", "not_ready")
