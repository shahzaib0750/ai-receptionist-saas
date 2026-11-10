from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BillingPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    monthly_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    included_minutes: int = Field(ge=0, le=10_000_000)
    max_phone_numbers: int = Field(ge=1, le=100_000)
    provider_price_id: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class BillingPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    monthly_price: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    currency: str | None = Field(
        default=None, min_length=3, max_length=3, pattern="^[A-Z]{3}$"
    )
    included_minutes: int | None = Field(default=None, ge=0, le=10_000_000)
    max_phone_numbers: int | None = Field(default=None, ge=1, le=100_000)
    provider_price_id: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_changes(self) -> "BillingPlanUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one plan field must be provided")
        for field in (
            "name",
            "monthly_price",
            "currency",
            "included_minutes",
            "max_phone_numbers",
            "is_active",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class BillingPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    monthly_price: Decimal
    currency: str
    provider_price_id: str | None
    included_minutes: int
    max_phone_numbers: int
    is_active: bool


class PublicBillingPlanRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    monthly_price: Decimal
    currency: str
    included_minutes: int
    max_phone_numbers: int


class BillingUsageRead(BaseModel):
    business_id: UUID
    subscription_id: UUID | None
    plan: BillingPlanRead | None
    status: str | None
    monthly_price: Decimal | None
    currency: str | None
    included_minutes: int
    used_seconds: int
    used_minutes: int
    remaining_minutes: int
    usage_percent: float
    billing_period_start: datetime | None
    billing_period_end: datetime | None
    next_billing_date: datetime | None
    additional_minutes: int


class BillingSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    plan_id: UUID
    provider: str
    status: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    trial_end: datetime | None
    cancel_at_period_end: bool
    created_at: datetime
    plan: BillingPlanRead


class BillingInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    amount: Decimal
    currency: str
    status: str
    due_date: date | None
    paid_at: datetime | None
    payment_reference: str | None
    failure_details: str | None
    hosted_invoice_url: str | None
    created_at: datetime


class BillingPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    subscription_id: UUID
    invoice_id: UUID | None
    amount: Decimal
    currency: str
    status: str
    payment_reference: str | None
    failure_details: str | None
    created_at: datetime


class CheckoutRequest(BaseModel):
    plan_id: UUID


class CheckoutSessionRead(BaseModel):
    checkout_url: str


class MinuteGrantRequest(BaseModel):
    minutes: int = Field(ge=1, le=1_000_000)
    reason: str = Field(min_length=3, max_length=500)


class BillingProviderEventPayload(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=80)
    created: int | None = Field(default=None, ge=0)
    data: dict[str, Any]
