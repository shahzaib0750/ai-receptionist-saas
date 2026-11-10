from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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


class VapiCallParty(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: str | None = Field(default=None, max_length=64)


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
    call_type: (
        Literal[
            "inboundPhoneCall",
            "outboundPhoneCall",
            "webCall",
            "vapi.websocketCall",
        ]
        | None
    ) = Field(default=None, alias="type")
    customer: VapiCallParty | None = None
    phoneNumber: VapiCallParty | None = None
    startedAt: AwareDatetime | None = None
    endedAt: AwareDatetime | None = None
    duration: float | None = Field(default=None, ge=0, le=86400)


class VapiCallArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transcript: str | None = Field(default=None, max_length=64 * 1024)
    recordingUrl: str | None = Field(default=None, max_length=2048)
    recording: dict[str, object] | None = None


class VapiStatusUpdateMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["status-update"]
    status: VapiCallStatus
    call: VapiCallReference
    timestamp: AwareDatetime | None = None


class VapiWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: VapiWebhookMessageType


class VapiStatusUpdateEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: VapiStatusUpdateMessage


class VapiEndOfCallReportMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["end-of-call-report"]
    call: VapiCallReference
    timestamp: AwareDatetime | None = None
    artifact: VapiCallArtifact | None = None
    endedReason: str | None = Field(default=None, max_length=128)


class VapiEndOfCallReportEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: VapiEndOfCallReportMessage
