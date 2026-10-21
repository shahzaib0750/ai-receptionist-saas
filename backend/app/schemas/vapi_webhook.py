from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VapiCallStatus = Literal[
    "scheduled",
    "queued",
    "ringing",
    "in-progress",
    "forwarding",
    "ended",
]


class VapiWebhookMessageType(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = Field(min_length=1, max_length=100)


class VapiCallReference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=255, pattern=r"^\S+$")
    assistantId: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^\S+$",
    )
    phoneNumberId: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^\S+$",
    )


class VapiStatusUpdateMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["status-update"]
    status: VapiCallStatus
    call: VapiCallReference


class VapiWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: VapiWebhookMessageType


class VapiStatusUpdateEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: VapiStatusUpdateMessage
