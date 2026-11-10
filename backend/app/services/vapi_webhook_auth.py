import hmac
import logging

from fastapi import HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def verify_vapi_webhook_authorization(authorization: str | None) -> None:
    expected_secret = get_settings().VAPI_WEBHOOK_SECRET
    if expected_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vapi webhook authentication is not configured",
        )

    authorization_present = authorization is not None
    bearer_scheme_received = False
    credential_matches_expected = False
    if authorization is not None:
        scheme, separator, credential = authorization.partition(" ")
        bearer_scheme_received = bool(separator) and scheme.casefold() == "bearer"
        if bearer_scheme_received:
            credential = credential.lstrip(" ")
            if credential:
                expected = expected_secret.get_secret_value().encode("utf-8")
                supplied = credential.encode("utf-8")
                credential_matches_expected = hmac.compare_digest(
                    supplied,
                    expected,
                )

    if not credential_matches_expected:
        logger.warning(
            "Vapi webhook authentication failed",
            extra={
                "authorization_present": authorization_present,
                "bearer_scheme_received": bearer_scheme_received,
                "credential_matches_expected": credential_matches_expected,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication",
        )
