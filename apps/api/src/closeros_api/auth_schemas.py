"""Safe authentication API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or normalized.count("@") != 1:
        raise ValueError("invalid email")
    local, domain = normalized.split("@", maxsplit=1)
    if not local or not domain:
        raise ValueError("invalid email")
    return normalized


class RegisterRequest(_StrictModel):
    email: str = Field(max_length=320)
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class EmailOnlyRequest(_StrictModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class VerificationConfirmRequest(_StrictModel):
    verification_token: str = Field(min_length=43, max_length=43)


class LoginRequest(_StrictModel):
    email: str = Field(max_length=320)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class MfaCompleteRequest(_StrictModel):
    method: Literal["webauthn", "totp"]
    response: dict[str, Any] = Field(default_factory=dict)


class PasswordResetConfirmRequest(_StrictModel):
    reset_token: str = Field(min_length=43, max_length=43)
    new_password: SecretStr = Field(min_length=8, max_length=128)


class PasswordChangeRequest(_StrictModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=128)


class AcceptedResponse(_StrictModel):
    message: str = "request accepted"


class LoginResponse(_StrictModel):
    state: Literal["authenticated", "mfa_required"]
    csrf_token: str
    expires_at: datetime
    user_id: UUID | None = None
    session_id: UUID | None = None
    assurance_level: Literal["single_factor", "multi_factor"] | None = None


class SessionResponse(_StrictModel):
    user_id: UUID
    session_id: UUID
    assurance_level: Literal["single_factor", "multi_factor"]
    expires_at: datetime
    csrf_token: str


class ErrorResponse(_StrictModel):
    message: str


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    sanitized: list[dict[str, str]] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()))
        sanitized.append(
            {
                "location": location,
                "message": str(error.get("msg", "invalid value")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return sanitized
