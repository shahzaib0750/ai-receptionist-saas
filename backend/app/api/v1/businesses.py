from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_business_permission
from app.db.session import get_db
from app.models.business import Business, BusinessMember, BusinessRole
from app.models.user import User
from app.schemas.business import BusinessCreate, BusinessRead
from app.services.business_authorization import (
    BusinessPermission,
    roles_with_permission,
)

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
