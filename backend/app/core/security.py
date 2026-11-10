from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

ALGORITHM = "HS256"
_password_hasher = PasswordHasher()


class InvalidAccessTokenError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedAccessToken:
    user_id: UUID
    token_version: int


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def create_access_token(user_id: UUID, token_version: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
        "ver": token_version,
    }
    return jwt.encode(
        payload,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> DecodedAccessToken:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub", "ver"]},
        )
        if payload.get("type") != "access":
            raise InvalidAccessTokenError("Invalid access token type")
        token_version = payload["ver"]
        if (
            not isinstance(token_version, int)
            or isinstance(token_version, bool)
            or token_version < 0
        ):
            raise InvalidAccessTokenError("Invalid access token version")
        return DecodedAccessToken(
            user_id=UUID(payload["sub"]),
            token_version=token_version,
        )
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise InvalidAccessTokenError("Invalid access token") from error
