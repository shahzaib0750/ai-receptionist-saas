import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.vapi_webhook import (
    VapiEndOfCallReportEnvelope,
    VapiStatusUpdateEnvelope,
    VapiWebhookEnvelope,
)
from app.services.vapi_call_events import (
    VapiCallEventResult,
    process_vapi_end_of_call_report,
    process_vapi_status_update,
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

    if envelope.message.type == "end-of-call-report":
        try:
            event = VapiEndOfCallReportEnvelope.model_validate(payload).message
        except ValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid end-of-call report",
            ) from error
        result = process_vapi_end_of_call_report(event, db)
    elif envelope.message.type == "status-update":
        try:
            event = VapiStatusUpdateEnvelope.model_validate(payload).message
        except ValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid status-update event",
            ) from error
        result = process_vapi_status_update(event, db)
    else:
        return {"status": "ignored"}

    if result is VapiCallEventResult.FAILED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vapi call could not be associated with a business",
        )
    return {"status": result.value}
