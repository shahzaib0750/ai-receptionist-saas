from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_business_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.business import Business, BusinessMember, BusinessRole
from app.models.receptionist_configuration import ReceptionistConfiguration
from app.models.receptionist_provisioning import ReceptionistProvisioning
from app.models.user import User
from app.schemas.business import (
    BusinessCreate,
    BusinessMemberCreate,
    BusinessMemberRead,
    BusinessMemberUpdate,
    BusinessRead,
    BusinessUpdate,
)
from app.services.business_authorization import (
    BusinessPermission,
    roles_with_permission,
)
from app.services.receptionist_provisioning import update_provisioned_assistant

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
def create_business(
    payload: BusinessCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Business:
    business = Business(name=payload.name, owner_user_id=current_user.id)
    db.add(business)
    db.flush()
    db.add(
        BusinessMember(
            business_id=business.id,
            user_id=current_user.id,
            role=BusinessRole.OWNER,
        )
    )
    db.commit()
    db.refresh(business)
    return business


@router.get("", response_model=list[BusinessRead])
def list_businesses(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Business]:
    statement = (
        select(Business)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(
            BusinessMember.user_id == current_user.id,
            BusinessMember.role.in_(roles_with_permission(BusinessPermission.READ)),
        )
        .order_by(Business.created_at, Business.id)
    )
    return list(db.scalars(statement).all())


@router.get("/{business_id}", response_model=BusinessRead)
def read_business(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ)),
    ],
) -> Business:
    return business


@router.patch("/{business_id}", response_model=BusinessRead)
def update_business(
    payload: BusinessUpdate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> Business:
    previous_name = business.name
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    try:
        if business.name != previous_name:
            provisioning = db.scalar(
                select(ReceptionistProvisioning).where(
                    ReceptionistProvisioning.business_id == business.id
                )
            )
            receptionist_configuration = db.scalar(
                select(ReceptionistConfiguration).where(
                    ReceptionistConfiguration.business_id == business.id
                )
            )
            if provisioning is not None and receptionist_configuration is not None:
                if receptionist_configuration.assistant_name == (
                    f"{previous_name} Receptionist"
                ):
                    receptionist_configuration.assistant_name = (
                        f"{business.name} Receptionist"
                    )
                previous_greeting = (
                    f"Thank you for calling {previous_name}. How can I help you today?"
                )
                if receptionist_configuration.greeting_message == previous_greeting:
                    receptionist_configuration.greeting_message = (
                        f"Thank you for calling {business.name}. "
                        "How can I help you today?"
                    )
                update_provisioned_assistant(
                    business,
                    receptionist_configuration,
                    provisioning,
                    get_settings(),
                )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    db.refresh(business)
    return business


@router.get("/{business_id}/members", response_model=list[BusinessMemberRead])
def list_business_members(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_MEMBERS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> list[BusinessMemberRead]:
    members = db.execute(
        select(BusinessMember, User.email, User.full_name)
        .join(User, User.id == BusinessMember.user_id)
        .where(BusinessMember.business_id == business.id)
        .order_by(BusinessMember.created_at, BusinessMember.user_id)
    ).all()
    return [
        BusinessMemberRead(
            user_id=member.user_id,
            email=email,
            full_name=full_name,
            role=member.role,
            created_at=member.created_at,
        )
        for member, email, full_name in members
    ]


@router.post(
    "/{business_id}/members",
    response_model=BusinessMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_business_member(
    payload: BusinessMemberCreate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_MEMBERS)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BusinessMemberRead:
    actor_membership = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business.id,
            BusinessMember.user_id == current_user.id,
        )
    )
    if actor_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    if (
        actor_membership.role is BusinessRole.ADMIN
        and payload.role is not BusinessRole.MEMBER
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only add members",
        )

    user = db.scalar(select(User).where(User.email == str(payload.email)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    membership = BusinessMember(
        business_id=business.id,
        user_id=user.id,
        role=payload.role,
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if (
            db.scalar(
                select(BusinessMember.id).where(
                    BusinessMember.business_id == business.id,
                    BusinessMember.user_id == user.id,
                )
            )
            is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a business member",
            ) from None
        raise
    db.refresh(membership)
    return BusinessMemberRead(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.patch(
    "/{business_id}/members/{user_id}",
    response_model=BusinessMemberRead,
)
def update_business_member(
    user_id: UUID,
    payload: BusinessMemberUpdate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_MEMBERS)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BusinessMemberRead:
    actor_membership = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business.id,
            BusinessMember.user_id == current_user.id,
        )
    )
    target = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business.id,
            BusinessMember.user_id == user_id,
        )
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business member not found",
        )
    if actor_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    if target.role is BusinessRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The business owner role cannot be changed",
        )
    if actor_membership.role is BusinessRole.ADMIN and (
        target.role is not BusinessRole.MEMBER
        or payload.role is not BusinessRole.MEMBER
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only manage members",
        )

    target.role = payload.role
    db.commit()
    user = db.get(User, target.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business member not found",
        )
    return BusinessMemberRead(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=target.role,
        created_at=target.created_at,
    )


@router.delete(
    "/{business_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_business_member(
    user_id: UUID,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_MEMBERS)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    actor_membership = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business.id,
            BusinessMember.user_id == current_user.id,
        )
    )
    target = db.scalar(
        select(BusinessMember).where(
            BusinessMember.business_id == business.id,
            BusinessMember.user_id == user_id,
        )
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business member not found",
        )
    if actor_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    if target.role is BusinessRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The business owner membership cannot be removed",
        )
    if (
        actor_membership.role is BusinessRole.ADMIN
        and target.role is not BusinessRole.MEMBER
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only manage members",
        )
    db.delete(target)
    db.commit()
