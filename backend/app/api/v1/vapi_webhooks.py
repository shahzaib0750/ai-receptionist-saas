import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.vapi_configuration import VapiConfiguration
from app.schemas.vapi_webhook import (
    VapiStatusUpdateEnvelope,
    VapiWebhookEnvelope,
)
from app.services.vapi_webhook_auth import verify_vapi_webhook_authorization

router = APIRouter(prefix="/integrations/vapi", tags=["Vapi webhooks"])
MAX_WEBHOOK_BODY_BYTES = 64 * 1024


async def _read_bounded_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        if not content_length.isascii() or not content_length.isdecimal():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook payload",
            )
        if int(content_length) > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Webhook payload is too large",
            )

    chunks: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Webhook payload is too large",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _resolve_vapi_configuration(
    assistant_id: str | None,
    phone_number_id: str | None,
    db: Session,
) -> VapiConfiguration:
    identifiers = []
    if assistant_id is not None:
        identifiers.append(VapiConfiguration.assistant_id == assistant_id)
    if phone_number_id is not None:
        identifiers.append(VapiConfiguration.phone_number_id == phone_number_id)
    if not identifiers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Call event is missing configured Vapi identifiers",
        )

    configurations = db.scalars(
        select(VapiConfiguration)
        .where(
            VapiConfiguration.is_enabled.is_(True),
            or_(*identifiers),
        )
        .limit(2)
    ).all()
    if len(configurations) != 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vapi configuration not found",
        )

    configuration = configurations[0]
    if (
        assistant_id is not None
        and configuration.assistant_id != assistant_id
    ) or (
        phone_number_id is not None
        and configuration.phone_number_id != phone_number_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vapi configuration not found",
        )
    return configuration


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_vapi_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    verify_vapi_webhook_authorization(authorization)

    body = await _read_bounded_body(request)
    try:
        payload = json.loads(body)
        envelope = VapiWebhookEnvelope.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        ) from error

    if envelope.message.type != "status-update":
        return {"status": "ignored"}

    try:
        event = VapiStatusUpdateEnvelope.model_validate(payload).message
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid status-update event",
        ) from error

    _resolve_vapi_configuration(
        event.call.assistantId,
        event.call.phoneNumberId,
        db,
    )
    return {"status": "accepted"}
