"""Framework-independent business rules for the modular-monolith backend."""

from closeros.domain.access import TenantAccessDeniedError, require_tenant_access
from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationEmail,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
    MfaMethod,
    PasswordHash,
)
from closeros.domain.authentication_policy import (
    AuthenticationSessionUnavailableError,
    AuthenticationTokenUnavailableError,
    EmailVerificationRequiredError,
    MfaRequiredError,
    require_privileged_mfa,
    require_usable_authentication_session,
    require_usable_authentication_token,
    require_verified_email,
    requires_mfa_for_roles,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_timeout import (
    AUTHENTICATION_SESSION_TIMEOUT_POLICY,
    AuthenticationSessionTimeoutPolicy,
    calculate_authentication_session_absolute_expiry,
    calculate_authentication_session_idle_expiry,
)
from closeros.domain.authentication_token import AuthenticationOneTimeToken
from closeros.domain.authentication_token_timeout import (
    AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY,
    AuthenticationOneTimeTokenTimeoutPolicy,
    calculate_authentication_one_time_token_expiry,
)
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.identity import (
    InvitationStatus,
    MembershipStatus,
    Role,
    TenantStatus,
    UserStatus,
)
from closeros.domain.invitation import Invitation
from closeros.domain.membership import Membership
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant
from closeros.domain.user import User

__all__ = [
    "AuthenticationAssuranceLevel",
    "AuthenticationEmail",
    "AuthenticationOneTimeToken",
    "AuthenticationOneTimeTokenTimeoutPolicy",
    "AuthenticationSession",
    "AuthenticationSessionStage",
    "AuthenticationSessionTimeoutPolicy",
    "AuthenticationSessionUnavailableError",
    "AuthenticationTokenHash",
    "AuthenticationTokenPurpose",
    "AuthenticationTokenUnavailableError",
    "AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY",
    "AUTHENTICATION_SESSION_TIMEOUT_POLICY",
    "EmailPasswordCredential",
    "EmailVerificationRequiredError",
    "Invitation",
    "InvitationStatus",
    "MfaMethod",
    "PasswordHash",
    "Membership",
    "MembershipStatus",
    "MfaRequiredError",
    "RetentionPolicy",
    "Role",
    "Tenant",
    "TenantAccessDeniedError",
    "TenantStatus",
    "User",
    "UserStatus",
    "calculate_authentication_one_time_token_expiry",
    "calculate_authentication_session_absolute_expiry",
    "calculate_authentication_session_idle_expiry",
    "require_privileged_mfa",
    "require_tenant_access",
    "require_usable_authentication_session",
    "require_usable_authentication_token",
    "require_verified_email",
    "requires_mfa_for_roles",
]
