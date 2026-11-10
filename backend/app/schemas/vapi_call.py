from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

VapiCallStatusFilter = Literal[
    "scheduled",
    "queued",
    "ringing",
    "in-progress",
    "forwarding",
    "ended",
]


class VapiCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    vapi_call_id: str
    assistant_id: str
    phone_number_id: str | None
    direction: Literal["inbound", "outbound"] | None
    status: VapiCallStatusFilter
    caller_number: str | None
    recipient_number: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    transcript: str | None
    recording_url: str | None
    ended_reason: str | None
    created_at: datetime
    updated_at: datetime


class VapiCallSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    vapi_call_id: str
    assistant_id: str
    phone_number_id: str | None
    direction: Literal["inbound", "outbound"] | None
    status: VapiCallStatusFilter
    caller_number: str | None
    recipient_number: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    ended_reason: str | None
    created_at: datetime
    updated_at: datetime


class VapiCallPage(BaseModel):
    items: list[VapiCallSummary]
    total: int
    limit: int
    offset: int
