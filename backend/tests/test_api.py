from collections.abc import Iterator
from uuid import UUID, uuid4

import jwt
import pytest
from app.api.dependencies import require_business_permission
from app.core.config import get_settings
from app.core.security import verify_password
from app.db.session import Base, get_db
from app.main import app
from app.models.business import Business, BusinessMember, BusinessRole
from app.models.user import User
from app.services.business_authorization import (
    BusinessPermission,
    enforce_business_permission,
    has_business_permission,
    roles_with_permission,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
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


def test_existing_health_endpoints(client: TestClient) -> None:
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code in (200, 503)
    assert ready.json()["status"] in ("ready", "not_ready")
