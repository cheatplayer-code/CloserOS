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


@dataclass(frozen=True, slots=True)
class AuthenticationEmail:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise TypeError("value must be a string")

        normalized_value = self.value.strip().lower()

        if not normalized_value:
            raise ValueError("value must not be empty")

        if any(character.isspace() for character in normalized_value):
            raise ValueError("value must not contain whitespace")

        if normalized_value.count("@") != 1:
            raise ValueError("value must contain exactly one @")

        local_part, domain_part = normalized_value.split("@", maxsplit=1)

        if not local_part:
            raise ValueError("email local part must not be empty")

        if not domain_part:
            raise ValueError("email domain part must not be empty")

        object.__setattr__(self, "value", normalized_value)
