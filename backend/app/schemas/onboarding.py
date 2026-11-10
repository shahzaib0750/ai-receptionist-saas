from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

SupportedReceptionistService = Literal["call_answering"]


class BusinessOnboardingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    website: str | None = Field(default=None, max_length=2048)
    address: str | None = Field(default=None, max_length=1000)
    business_hours: str | None = Field(default=None, max_length=2000)
    contact_phone: str | None = Field(default=None, max_length=64)
    contact_email: EmailStr | None = None
    country_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    assistant_name: str | None = Field(default=None, max_length=120)
    greeting_message: str | None = Field(default=None, max_length=2000)
    requirements_text: str | None = Field(default=None, max_length=5000)
    fallback_instructions: str | None = Field(default=None, max_length=2000)
    selected_services: list[SupportedReceptionistService] = Field(
        min_length=1, max_length=1
    )
    business_timezone: str = Field(min_length=1, max_length=64)

    @field_validator(
        "name",
        "industry",
        "description",
        "address",
        "business_hours",
        "contact_phone",
        "website",
        "assistant_name",
        "greeting_message",
        "requirements_text",
        "fallback_instructions",
        "business_timezone",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("contact_email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError as error:
            raise ValueError("Website must be a valid HTTP(S) URL") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("Website must be a valid HTTP(S) URL")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("business_timezone")
    @classmethod
    def validate_business_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Invalid IANA timezone") from error
        return value


class BusinessOnboardingRead(BaseModel):
    business_id: UUID
    name: str
    industry: str | None
    description: str | None
    website: str | None
    address: str | None
    business_hours: str | None
    contact_phone: str | None
    contact_email: str | None
    country_code: str
    assistant_name: str | None
    greeting_message: str | None
    requirements_text: str | None
    fallback_instructions: str | None
    selected_services: list[str]
    business_timezone: str
    status: str
    phone_number: str | None
    safe_error_code: str | None
    error_message: str | None
    attempts: int
    phone_number_consent_given: bool


class PhoneNumberProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept_phone_number_provisioning: bool = False
