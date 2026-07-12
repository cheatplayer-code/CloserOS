"""Application use cases and ports."""

from closeros.application.authentication_issuance import (
    AuthenticationSessionRotation,
    AuthenticationSessionTransitionError,
    IssuedAuthenticationOneTimeToken,
    IssuedAuthenticationSession,
    complete_pending_mfa_and_rotate_session,
    issue_authenticated_session,
    issue_authentication_one_time_token,
    issue_pending_mfa_session,
)
from closeros.application.authentication_persistence import (
    AuthenticationPersistenceError,
    AuthenticationRecordNotFoundError,
    AuthenticationReferenceError,
    AuthenticationUnitOfWork,
    CredentialRepository,
    DuplicateCredentialEmailError,
    DuplicateOneTimeTokenError,
    DuplicateSessionTokenError,
    DuplicateUserCredentialError,
    OneTimeTokenRepository,
    SessionRepository,
    UserRepository,
)
from closeros.application.password_hashing import (
    PasswordHasher,
    PasswordVerification,
)

__all__ = [
    "AuthenticationPersistenceError",
    "AuthenticationRecordNotFoundError",
    "AuthenticationReferenceError",
    "AuthenticationSessionRotation",
    "AuthenticationSessionTransitionError",
    "AuthenticationUnitOfWork",
    "CredentialRepository",
    "DuplicateCredentialEmailError",
    "DuplicateOneTimeTokenError",
    "DuplicateSessionTokenError",
    "DuplicateUserCredentialError",
    "IssuedAuthenticationOneTimeToken",
    "IssuedAuthenticationSession",
    "OneTimeTokenRepository",
    "PasswordHasher",
    "PasswordVerification",
    "SessionRepository",
    "UserRepository",
    "complete_pending_mfa_and_rotate_session",
    "issue_authenticated_session",
    "issue_authentication_one_time_token",
    "issue_pending_mfa_session",
]
