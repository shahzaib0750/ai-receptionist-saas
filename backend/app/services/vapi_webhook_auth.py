import hmac

from fastapi import HTTPException, status

from app.core.config import get_settings


def verify_vapi_webhook_authorization(authorization: str | None) -> None:
    expected_secret = get_settings().VAPI_WEBHOOK_SECRET
    if expected_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vapi webhook authentication is not configured",
        )

    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication",
        )

    scheme, separator, credential = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication",
        )

    expected = expected_secret.get_secret_value().encode("utf-8")
    supplied = credential.encode("utf-8")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication",
        )
