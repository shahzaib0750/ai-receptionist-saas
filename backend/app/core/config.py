from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
    env_file="../.env",
    env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "AI Receptionist SaaS"
    APP_ENV: Literal["development", "test", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_NAME: str = "ai_receptionist"
    DB_USER: str = "receptionist_app"
    DB_PASSWORD: SecretStr
    SECRET_KEY: SecretStr
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    VAPI_API_KEY: SecretStr | None = None
    VAPI_WEBHOOK_SECRET: SecretStr | None = None
    PUBLIC_API_BASE_URL: str | None = None
    VAPI_RECOVERY_ENABLED: bool = True
    VAPI_RECOVERY_POLL_INTERVAL_SECONDS: int = 5
    VAPI_RECOVERY_BATCH_SIZE: int = 50
    VAPI_RECOVERY_MAX_ATTEMPTS: int = 10
    VAPI_RECOVERY_MAX_BACKOFF_SECONDS: int = 300
    VAPI_MODEL_PROVIDER: str = "openai"
    VAPI_MODEL: str = "gpt-4o-mini"
    VAPI_VOICE_PROVIDER: str = "11labs"
    VAPI_VOICE_ID: str = "paula"
    KNOWLEDGE_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    KNOWLEDGE_EMBEDDING_DIMENSIONS: int = 384
    KNOWLEDGE_EMBEDDING_BATCH_SIZE: int = 8
    KNOWLEDGE_CHUNK_SIZE: int = 1000
    KNOWLEDGE_CHUNK_OVERLAP: int = 150
    KNOWLEDGE_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    KNOWLEDGE_MAX_EXTRACTED_CHARACTERS: int = 1_000_000
    KNOWLEDGE_MAX_PDF_PAGES: int = 500
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: SecretStr | None = None

    PAYMENT_PROVIDER: str | None = None
    PAYMENT_SECRET_KEY: SecretStr | None = None
    PAYMENT_WEBHOOK_SECRET: SecretStr | None = None
    BILLING_ADMIN_USER_IDS: str = ""

    FRONTEND_ORIGIN: str = "http://localhost:5173"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        return value

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_token_expiry(cls, value: int) -> int:
        if not 1 <= value <= 1440:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440")
        return value

    @field_validator("API_V1_PREFIX")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API_V1_PREFIX must start with / and must not end with /")
        return value

    @field_validator("VAPI_WEBHOOK_SECRET")
    @classmethod
    def validate_vapi_webhook_secret(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("VAPI_WEBHOOK_SECRET must not be empty")
        return value

    @field_validator(
        "VAPI_RECOVERY_POLL_INTERVAL_SECONDS",
        "VAPI_RECOVERY_MAX_ATTEMPTS",
        "VAPI_RECOVERY_MAX_BACKOFF_SECONDS",
    )
    @classmethod
    def validate_positive_recovery_setting(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Vapi recovery settings must be at least 1")
        return value

    @field_validator("VAPI_RECOVERY_BATCH_SIZE")
    @classmethod
    def validate_recovery_batch_size(cls, value: int) -> int:
        if not 1 <= value <= 1000:
            raise ValueError("VAPI_RECOVERY_BATCH_SIZE must be between 1 and 1000")
        return value

    @field_validator(
        "KNOWLEDGE_EMBEDDING_BATCH_SIZE",
        "KNOWLEDGE_CHUNK_SIZE",
        "KNOWLEDGE_MAX_UPLOAD_BYTES",
        "KNOWLEDGE_MAX_EXTRACTED_CHARACTERS",
        "KNOWLEDGE_MAX_PDF_PAGES",
    )
    @classmethod
    def validate_positive_knowledge_setting(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Knowledge settings must be at least 1")
        return value

    @field_validator("KNOWLEDGE_CHUNK_OVERLAP")
    @classmethod
    def validate_chunk_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("KNOWLEDGE_CHUNK_OVERLAP must not be negative")
        return value

    @model_validator(mode="after")
    def validate_knowledge_chunk_settings(self) -> "Settings":
        if self.KNOWLEDGE_CHUNK_OVERLAP >= self.KNOWLEDGE_CHUNK_SIZE:
            raise ValueError(
                "KNOWLEDGE_CHUNK_OVERLAP must be smaller than KNOWLEDGE_CHUNK_SIZE"
            )
        if self.KNOWLEDGE_EMBEDDING_DIMENSIONS != 384:
            raise ValueError(
                "KNOWLEDGE_EMBEDDING_DIMENSIONS must be 384 for the configured model"
            )
        return self

    @field_validator("TWILIO_ACCOUNT_SID")
    @classmethod
    def validate_twilio_account_sid(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) != 34
            or not value.startswith("AC")
            or any(character not in "0123456789abcdefABCDEF" for character in value[2:])
        ):
            raise ValueError("TWILIO_ACCOUNT_SID must be a Twilio account SID")
        return value

    @field_validator("PUBLIC_API_BASE_URL")
    @classmethod
    def validate_public_api_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError as error:
            raise ValueError("PUBLIC_API_BASE_URL must be a valid HTTP(S) URL") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("PUBLIC_API_BASE_URL must be a valid HTTP(S) URL")
        return value.rstrip("/")

    @field_validator("FRONTEND_ORIGIN")
    @classmethod
    def validate_frontend_origin(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as error:
            raise ValueError("FRONTEND_ORIGIN must be a valid origin") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or value == "*"
        ):
            raise ValueError("FRONTEND_ORIGIN must be a single HTTP(S) origin")
        authority = parsed.hostname
        if ":" in authority:
            authority = f"[{authority}]"
        if port is not None:
            authority = f"{authority}:{port}"
        return f"{parsed.scheme}://{authority}"

    @property
    def cors_allowed_origins(self) -> list[str]:
        origins = [self.FRONTEND_ORIGIN]
        if self.APP_ENV != "development":
            return origins

        parsed = urlsplit(self.FRONTEND_ORIGIN)
        local_aliases = {"localhost": "127.0.0.1", "127.0.0.1": "localhost"}
        alias = local_aliases.get(parsed.hostname or "")
        if alias is not None:
            port = f":{parsed.port}" if parsed.port is not None else ""
            alias_origin = f"{parsed.scheme}://{alias}{port}"
            if alias_origin not in origins:
                origins.append(alias_origin)
        return origins

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.APP_ENV == "production":
            if self.DEBUG:
                raise ValueError("DEBUG must be false in production")
            if not self.FRONTEND_ORIGIN.startswith("https://"):
                raise ValueError("FRONTEND_ORIGIN must use HTTPS in production")
            if self.PUBLIC_API_BASE_URL is not None and not self.PUBLIC_API_BASE_URL.startswith(
                "https://"
            ):
                raise ValueError("PUBLIC_API_BASE_URL must use HTTPS in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
