"""Framework-independent authentication enums."""

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
