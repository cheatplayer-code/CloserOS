"""Framework-independent authentication primitives."""

from dataclasses import dataclass, field
from enum import StrEnum


class AuthenticationAssuranceLevel(StrEnum):
    SINGLE_FACTOR = "single_factor"
    MULTI_FACTOR = "multi_factor"


class MfaMethod(StrEnum):
    WEBAUTHN = "webauthn"
    TOTP = "totp"


class AuthenticationTokenPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


@dataclass(frozen=True, slots=True)
class AuthenticationTokenHash:
    digest: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.digest) is not bytes:
            raise TypeError("digest must be bytes")

        if len(self.digest) != 32:
            raise ValueError("digest must contain exactly 32 bytes")


@dataclass(frozen=True, slots=True)
class PasswordHash:
    encoded: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.encoded) is not str:
            raise TypeError("encoded must be a string")

        if not self.encoded:
            raise ValueError("encoded must not be empty")

        if self.encoded != self.encoded.strip():
            raise ValueError("encoded must not contain surrounding whitespace")

        if any(character.isspace() for character in self.encoded):
            raise ValueError("encoded must not contain whitespace")

        if not self.encoded.startswith("$argon2id$"):
            raise ValueError("encoded must be an Argon2id PHC string")
