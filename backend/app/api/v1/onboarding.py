from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_business_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.business import Business
from app.models.receptionist_configuration import ReceptionistConfiguration
from app.models.receptionist_provisioning import ReceptionistProvisioning
from app.models.user import User
from app.models.vapi_configuration import VapiConfiguration
from app.schemas.onboarding import (
    BusinessOnboardingRead,
    BusinessOnboardingUpdate,
    PhoneNumberProvisionRequest,
)
from app.services.billing import enforce_provisioning_entitlements
from app.services.business_authorization import BusinessPermission
from app.services.receptionist_provisioning import (
    DEFAULT_FALLBACK_INSTRUCTIONS,
    activate_receptionist,
    provision_receptionist,
    provisioning_error_message,
    update_provisioned_assistant,
)

router = APIRouter(prefix="/businesses/{business_id}", tags=["business onboarding"])


def _read_onboarding(
    business: Business,
    configuration: ReceptionistConfiguration | None,
    provisioning: ReceptionistProvisioning | None,
) -> BusinessOnboardingRead:
    return BusinessOnboardingRead(
        business_id=business.id,
        name=business.name,
        industry=business.industry,
        description=business.description,
        website=business.website,
        address=business.address,
        business_hours=business.business_hours,
        contact_phone=business.contact_phone,
        contact_email=business.contact_email,
        country_code=business.country_code,
        assistant_name=(
            configuration.assistant_name if configuration is not None else None
        ),
        greeting_message=(
            configuration.greeting_message if configuration is not None else None
        ),
        requirements_text=(
            configuration.requirements_text if configuration is not None else None
        ),
        fallback_instructions=(
            configuration.fallback_instructions
            if configuration is not None
            else DEFAULT_FALLBACK_INSTRUCTIONS
        ),
        selected_services=(
            configuration.selected_services
            if configuration is not None
            else ["call_answering"]
        ),
        business_timezone=(
            configuration.business_timezone if configuration is not None else "UTC"
        ),
        status=provisioning.status if provisioning is not None else "draft",
        phone_number=provisioning.phone_number if provisioning is not None else None,
        safe_error_code=(
            provisioning.safe_error_code if provisioning is not None else None
        ),
        error_message=(
            provisioning_error_message(provisioning.safe_error_code)
            if provisioning is not None
            else None
        ),
        attempts=provisioning.attempts if provisioning is not None else 0,
        phone_number_consent_given=(
            provisioning.consented_at is not None if provisioning is not None else False
        ),
    )


@router.get("/onboarding", response_model=BusinessOnboardingRead)
def get_business_onboarding(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> BusinessOnboardingRead:
    configuration = db.scalar(
        select(ReceptionistConfiguration).where(
            ReceptionistConfiguration.business_id == business.id
        )
    )
    provisioning = db.scalar(
        select(ReceptionistProvisioning).where(
            ReceptionistProvisioning.business_id == business.id
        )
    )
    return _read_onboarding(business, configuration, provisioning)


@router.put("/onboarding", response_model=BusinessOnboardingRead)
def save_business_onboarding(
    payload: BusinessOnboardingUpdate,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.MANAGE_SETTINGS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> BusinessOnboardingRead:
    for field in (
        "name",
        "industry",
        "description",
        "website",
        "address",
        "business_hours",
        "contact_phone",
        "country_code",
    ):
        setattr(business, field, getattr(payload, field))
    business.contact_email = (
        str(payload.contact_email) if payload.contact_email is not None else None
    )

    provisioning = db.scalar(
        select(ReceptionistProvisioning)
        .where(ReceptionistProvisioning.business_id == business.id)
        .with_for_update()
    )
    configuration = db.scalar(
        select(ReceptionistConfiguration).where(
            ReceptionistConfiguration.business_id == business.id
        )
    )
    if configuration is None:
        configuration = ReceptionistConfiguration(
            business_id=business.id,
            assistant_name=payload.assistant_name
            or f"{business.name} Receptionist",
            greeting_message=payload.greeting_message
            or f"Thank you for calling {business.name}. How can I help you today?",
            business_timezone=payload.business_timezone,
            is_enabled=False,
        )
        db.add(configuration)
    else:
        configuration.assistant_name = (
            payload.assistant_name or f"{business.name} Receptionist"
        )
        configuration.greeting_message = payload.greeting_message or (
            f"Thank you for calling {business.name}. How can I help you today?"
        )
        configuration.business_timezone = payload.business_timezone
        if provisioning is not None:
            configuration.is_enabled = provisioning.status == "active"

    configuration.requirements_text = payload.requirements_text
    configuration.fallback_instructions = (
        payload.fallback_instructions or DEFAULT_FALLBACK_INSTRUCTIONS
    )
    configuration.selected_services = list(payload.selected_services)

    if provisioning is None:
        provisioning = ReceptionistProvisioning(business_id=business.id)
        db.add(provisioning)

    try:
        if provisioning.assistant_id is not None:
            update_provisioned_assistant(
                business,
                configuration,
                provisioning,
                get_settings(),
            )
        db.commit()
    except HTTPException:
        db.rollback()
        raise

    db.refresh(business)
    db.refresh(configuration)
    db.refresh(provisioning)
    return _read_onboarding(business, configuration, provisioning)


@router.post("/receptionist/provision", response_model=BusinessOnboardingRead)
def start_or_retry_provisioning(
    payload: PhoneNumberProvisionRequest,
    business: Annotated[
        Business,
        Depends(
            require_business_permission(BusinessPermission.PROVISION_RECEPTIONIST)
        ),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BusinessOnboardingRead:
    if not payload.accept_phone_number_provisioning:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Confirm that the platform may provision a phone number before "
                "starting setup."
            ),
        )
    configuration = db.scalar(
        select(ReceptionistConfiguration).where(
            ReceptionistConfiguration.business_id == business.id
        )
    )
    if configuration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Save your business onboarding before starting setup.",
        )
    enforce_provisioning_entitlements(db, business.id)
    db.commit()
    provisioning = db.scalar(
        select(ReceptionistProvisioning)
        .where(ReceptionistProvisioning.business_id == business.id)
        .with_for_update()
    )
    if provisioning is None:
        provisioning = ReceptionistProvisioning(business_id=business.id)
        db.add(provisioning)
        db.commit()
        db.refresh(provisioning)
    if provisioning.consented_at is None:
        provisioning.consented_at = datetime.now(UTC)
        provisioning.consented_by_user_id = current_user.id
        db.commit()
    provisioning = provision_receptionist(
        business,
        configuration,
        provisioning,
        db,
    )
    return _read_onboarding(business, configuration, provisioning)


@router.post("/receptionist/activate", response_model=BusinessOnboardingRead)
def activate_business_receptionist(
    business: Annotated[
        Business,
        Depends(
            require_business_permission(BusinessPermission.PROVISION_RECEPTIONIST)
        ),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> BusinessOnboardingRead:
    provisioning = db.scalar(
        select(ReceptionistProvisioning).where(
            ReceptionistProvisioning.business_id == business.id
        )
    )
    if provisioning is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete receptionist setup before activation.",
        )
    receptionist_configuration = db.scalar(
        select(ReceptionistConfiguration).where(
            ReceptionistConfiguration.business_id == business.id
        )
    )
    vapi_configuration = db.scalar(
        select(VapiConfiguration).where(VapiConfiguration.business_id == business.id)
    )
    if receptionist_configuration is None or vapi_configuration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete receptionist setup before activation.",
        )

    result = activate_receptionist(
        business,
        provisioning,
        receptionist_configuration,
        vapi_configuration,
        db,
    )
    return _read_onboarding(business, receptionist_configuration, result)
