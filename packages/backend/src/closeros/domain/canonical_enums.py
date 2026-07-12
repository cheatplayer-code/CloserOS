"""Framework-independent canonical conversation enums."""

from enum import StrEnum


class ProviderKind(StrEnum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    TELEGRAM_BUSINESS = "telegram_business"
    SYNTHETIC = "synthetic"


class ChannelConnectionStatus(StrEnum):
    DRAFT = "draft"
    AUTHORIZING = "authorizing"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    REVOKED = "revoked"
    DISCONNECTED = "disconnected"


class LeadStatus(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    ARCHIVED = "archived"


class SalesCaseStatus(StrEnum):
    NEW = "new"
    AWAITING_BUSINESS = "awaiting_business"
    AWAITING_CUSTOMER = "awaiting_customer"
    QUALIFIED = "qualified"
    APPOINTMENT_PROPOSED = "appointment_proposed"
    APPOINTMENT_BOOKED = "appointment_booked"
    WON = "won"
    LOST = "lost"
    CLOSED_UNKNOWN = "closed_unknown"


class ParticipantSenderType(StrEnum):
    CUSTOMER = "customer"
    BOT = "bot"
    MANAGER = "manager"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CrmOutcomeType(StrEnum):
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class WebhookProcessingStatus(StrEnum):
    RECEIVED = "received"
    ACKNOWLEDGED = "acknowledged"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class SchemaVersion(StrEnum):
    V1_0 = "1.0"
