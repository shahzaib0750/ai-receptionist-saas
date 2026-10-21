from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReceptionistConfigurationFields(BaseModel):
    assistant_name: str = Field(min_length=1, max_length=120)
    greeting_message: str = Field(min_length=1, max_length=2000)
    business_timezone: str = Field(min_length=1, max_length=64)
    is_enabled: bool = True

    @field_validator("assistant_name", "greeting_message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be empty")
        return value

    @field_validator("business_timezone")
    @classmethod
    def validate_business_timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Invalid IANA timezone") from error
        return value


class ReceptionistConfigurationCreate(ReceptionistConfigurationFields):
    model_config = ConfigDict(extra="forbid")


class ReceptionistConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_name: str | None = Field(default=None, min_length=1, max_length=120)
    greeting_message: str | None = Field(default=None, min_length=1, max_length=2000)
    business_timezone: str | None = Field(default=None, min_length=1, max_length=64)
    is_enabled: bool | None = None

    @field_validator("assistant_name", "greeting_message")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Value must not be empty")
        return value

    @field_validator("business_timezone")
    @classmethod
    def validate_optional_business_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Invalid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def require_update_fields(self) -> "ReceptionistConfigurationUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Fields must not be null")
        return self


class ReceptionistConfigurationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    assistant_name: str
    greeting_message: str
    business_timezone: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
