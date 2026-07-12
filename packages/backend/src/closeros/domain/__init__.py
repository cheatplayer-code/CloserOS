"""Framework-independent business rules for the modular-monolith backend."""

from closeros.domain.access import TenantAccessDeniedError, require_tenant_access
from closeros.domain.adapter_metadata import AdapterMetadata
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
from closeros.domain.canonical_enums import (
    ChannelConnectionStatus,
    CrmOutcomeType,
    DeliveryStatus,
    LeadStatus,
    MessageDirection,
    ParticipantSenderType,
    ProviderKind,
    SalesCaseStatus,
    SchemaVersion,
    WebhookProcessingStatus,
)
from closeros.domain.channel_connection import ChannelConnection
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.crm_outcome import CRMOutcome
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.encrypted_content import (
    CONTENT_AAD_VERSION,
    DATA_ENCRYPTION_KEY_SIZE_BYTES,
    GCM_NONCE_SIZE_BYTES,
    PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES,
    RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES,
    ContentAccessPurpose,
    ContentEncoding,
    ContentUnavailableError,
    DecryptedContent,
    EncryptedContent,
    EncryptedContentError,
    EncryptedContentKind,
    EncryptionAlgorithm,
    WrappedDataKey,
    max_plaintext_bytes_for_kind,
    validate_plaintext_for_kind,
)
from closeros.domain.identity import (
    InvitationStatus,
    MembershipStatus,
    Role,
    TenantStatus,
    UserStatus,
)
from closeros.domain.invitation import Invitation
from closeros.domain.lead import Lead
from closeros.domain.manager_assignment import ManagerAssignment
from closeros.domain.membership import Membership
from closeros.domain.message import Message
from closeros.domain.message_events import (
    MessageDeletionEvent,
    MessageDeliveryStatusEvent,
    MessageEditEvent,
)
from closeros.domain.message_projection import MessageProjection, project_message
from closeros.domain.retention import RetentionPolicy
from closeros.domain.sales_case import SalesCase
from closeros.domain.tenant import Tenant
from closeros.domain.user import User
from closeros.domain.webhook_event import WebhookEvent

__all__ = [
    "AdapterMetadata",
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
    "ChannelConnection",
    "ChannelConnectionStatus",
    "CONTENT_AAD_VERSION",
    "ContentAccessPurpose",
    "ContentEncoding",
    "ContentUnavailableError",
    "ConversationThread",
    "CRMOutcome",
    "CrmOutcomeType",
    "DATA_ENCRYPTION_KEY_SIZE_BYTES",
    "DeliveryStatus",
    "DecryptedContent",
    "EmailPasswordCredential",
    "EncryptedContent",
    "EncryptedContentError",
    "EncryptedContentKind",
    "EncryptionAlgorithm",
    "EmailVerificationRequiredError",
    "Invitation",
    "InvitationStatus",
    "Lead",
    "LeadStatus",
    "ManagerAssignment",
    "Message",
    "MessageDeletionEvent",
    "MessageDeliveryStatusEvent",
    "MessageDirection",
    "MessageEditEvent",
    "MessageProjection",
    "MfaMethod",
    "ParticipantSenderType",
    "PasswordHash",
    "PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES",
    "ProviderKind",
    "RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES",
    "GCM_NONCE_SIZE_BYTES",
    "Membership",
    "MembershipStatus",
    "MfaRequiredError",
    "RetentionPolicy",
    "Role",
    "SalesCase",
    "SalesCaseStatus",
    "SchemaVersion",
    "Tenant",
    "TenantAccessDeniedError",
    "TenantStatus",
    "User",
    "UserStatus",
    "WebhookEvent",
    "WebhookProcessingStatus",
    "WrappedDataKey",
    "calculate_authentication_one_time_token_expiry",
    "calculate_authentication_session_absolute_expiry",
    "calculate_authentication_session_idle_expiry",
    "require_privileged_mfa",
    "require_tenant_access",
    "require_usable_authentication_session",
    "require_usable_authentication_token",
    "require_verified_email",
    "requires_mfa_for_roles",
    "max_plaintext_bytes_for_kind",
    "project_message",
    "validate_plaintext_for_kind",
]
