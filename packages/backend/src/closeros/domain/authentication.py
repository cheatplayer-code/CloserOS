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
