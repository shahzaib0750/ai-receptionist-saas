from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.db.session import get_db
from app.models.business import Business, BusinessMember
from app.models.user import User
from app.services.business_authorization import (
    BusinessPermission,
    enforce_business_permission,
)

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        decoded_token = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user = db.get(User, decoded_token.user_id)
    if (
        user is None
        or not user.is_active
        or user.token_version != decoded_token.token_version
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_business_permission(
    permission: BusinessPermission,
) -> Callable[..., Business]:
    def dependency(
        business_id: UUID,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> Business:
        result = db.execute(
            select(Business, BusinessMember.role)
            .join(BusinessMember, BusinessMember.business_id == Business.id)
            .where(
                Business.id == business_id,
                BusinessMember.user_id == current_user.id,
            )
        ).one_or_none()
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found",
            )
        business, role = result
        enforce_business_permission(role, permission)
        return business

    return dependency


def require_platform_billing_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    try:
        allowed_user_ids = {
            UUID(value.strip())
            for value in get_settings().BILLING_ADMIN_USER_IDS.split(",")
            if value.strip()
        }
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform administrator configuration is invalid",
        ) from error
    if current_user.id not in allowed_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required",
        )
    return current_user
