from enum import Enum

from fastapi import HTTPException, status

from app.models.business import BusinessRole


class BusinessPermission(str, Enum):
    READ = "read"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_OPERATIONAL_RESOURCES = "manage_operational_resources"
    MANAGE_MEMBERS = "manage_members"
    TRANSFER_OWNERSHIP = "transfer_ownership"
    REMOVE_OWNER = "remove_owner"


_ROLE_PERMISSIONS: dict[BusinessRole, frozenset[BusinessPermission]] = {
    BusinessRole.OWNER: frozenset(BusinessPermission),
    BusinessRole.ADMIN: frozenset(
        {
            BusinessPermission.READ,
            BusinessPermission.MANAGE_SETTINGS,
            BusinessPermission.MANAGE_OPERATIONAL_RESOURCES,
            BusinessPermission.MANAGE_MEMBERS,
        }
    ),
    BusinessRole.MEMBER: frozenset({BusinessPermission.READ}),
}


def roles_with_permission(permission: BusinessPermission) -> tuple[BusinessRole, ...]:
    return tuple(
        role
        for role, permissions in _ROLE_PERMISSIONS.items()
        if permission in permissions
    )


def has_business_permission(
    role: BusinessRole,
    permission: BusinessPermission,
) -> bool:
    return permission in _ROLE_PERMISSIONS[role]


def enforce_business_permission(
    role: BusinessRole,
    permission: BusinessPermission,
) -> None:
    if not has_business_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient business permissions",
        )
