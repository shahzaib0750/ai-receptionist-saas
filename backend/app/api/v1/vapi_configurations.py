from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_business_permission
from app.db.session import get_db
from app.models.business import Business
from app.models.vapi_configuration import VapiConfiguration
from app.schemas.vapi_configuration import (
    VapiConfigurationCreate,
    VapiConfigurationRead,
    VapiConfigurationUpdate,
)
from app.services.business_authorization import BusinessPermission

router = APIRouter(
    prefix="/businesses/{business_id}/vapi-configuration",
    tags=["Vapi configuration"],
)


@router.post(
    "",
    response_model=VapiConfigurationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_vapi_configuration(
    payload: VapiConfigurationCreate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> VapiConfiguration:
    configuration = VapiConfiguration(
        business_id=business.id,
        **payload.model_dump(),
    )
    db.add(configuration)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_business_config = db.scalar(
            select(VapiConfiguration.id).where(
                VapiConfiguration.business_id == business.id
            )
        )
        if existing_business_config is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vapi configuration already exists",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vapi identifiers are already configured",
        ) from None
    db.refresh(configuration)
    return configuration


@router.get("", response_model=VapiConfigurationRead)
def get_vapi_configuration(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> VapiConfiguration:
    configuration = db.scalar(
        select(VapiConfiguration).where(
            VapiConfiguration.business_id == business.id
        )
    )
    if configuration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vapi configuration not found",
        )
    return configuration


@router.patch("", response_model=VapiConfigurationRead)
def update_vapi_configuration(
    payload: VapiConfigurationUpdate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> VapiConfiguration:
    configuration = db.scalar(
        select(VapiConfiguration).where(
            VapiConfiguration.business_id == business.id
        )
    )
    if configuration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vapi configuration not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(configuration, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vapi identifiers are already configured",
        ) from None
    db.refresh(configuration)
    return configuration
