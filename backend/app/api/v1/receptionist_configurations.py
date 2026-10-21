from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_business_permission
from app.db.session import get_db
from app.models.business import Business
from app.models.receptionist_configuration import ReceptionistConfiguration
from app.schemas.receptionist_configuration import (
    ReceptionistConfigurationCreate,
    ReceptionistConfigurationRead,
    ReceptionistConfigurationUpdate,
)
from app.services.business_authorization import BusinessPermission

router = APIRouter(
    prefix="/businesses/{business_id}/receptionist-configuration",
    tags=["receptionist configuration"],
)


@router.post(
    "",
    response_model=ReceptionistConfigurationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_receptionist_configuration(
    payload: ReceptionistConfigurationCreate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> ReceptionistConfiguration:
    configuration = ReceptionistConfiguration(
        business_id=business.id,
        **payload.model_dump(),
    )
    db.add(configuration)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(
            select(ReceptionistConfiguration.id).where(
                ReceptionistConfiguration.business_id == business.id
            )
        ) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Receptionist configuration already exists",
            ) from None
        raise
    db.refresh(configuration)
    return configuration


@router.get("", response_model=ReceptionistConfigurationRead)
def get_receptionist_configuration(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> ReceptionistConfiguration:
    configuration = db.scalar(
        select(ReceptionistConfiguration).where(
            ReceptionistConfiguration.business_id == business.id
        )
    )
    if configuration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receptionist configuration not found",
        )
    return configuration


@router.patch("", response_model=ReceptionistConfigurationRead)
def update_receptionist_configuration(
    payload: ReceptionistConfigurationUpdate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> ReceptionistConfiguration:
    configuration = db.scalar(
        select(ReceptionistConfiguration).where(
            ReceptionistConfiguration.business_id == business.id
        )
    )
    if configuration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receptionist configuration not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(configuration, field, value)
    db.commit()
    db.refresh(configuration)
    return configuration
