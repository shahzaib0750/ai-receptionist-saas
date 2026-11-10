from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models.business import BusinessRole


class BusinessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Business name must not be empty")
        return value


class BusinessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Business name must not be empty")
        return value

    @model_validator(mode="after")
    def validate_changes(self) -> "BusinessUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Fields must not be null")
        return self


class BusinessMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: Literal[BusinessRole.ADMIN, BusinessRole.MEMBER]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().casefold()
        return value


class BusinessMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal[BusinessRole.ADMIN, BusinessRole.MEMBER]


class BusinessMemberRead(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str
    role: BusinessRole
    created_at: datetime


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime
