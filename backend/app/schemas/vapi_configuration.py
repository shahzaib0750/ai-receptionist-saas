from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VapiConfigurationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_id: str = Field(min_length=1, max_length=255, pattern=r"^\S+$")
    phone_number_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^\S+$",
    )
    is_enabled: bool = True

    @field_validator("assistant_id", "phone_number_id", mode="before")
    @classmethod
    def strip_identifiers(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class VapiConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^\S+$",
    )
    phone_number_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^\S+$",
    )
    is_enabled: bool | None = None

    @field_validator("assistant_id", "phone_number_id", mode="before")
    @classmethod
    def strip_identifiers(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_update_fields(self) -> "VapiConfigurationUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Fields must not be null")
        return self


class VapiConfigurationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    assistant_id: str
    phone_number_id: str | None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
