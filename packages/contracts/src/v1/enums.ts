/** Canonical contract version for v1 entities. */
export const SCHEMA_VERSION_V1 = "1.0" as const;

export type SchemaVersionV1 = typeof SCHEMA_VERSION_V1;

/** ISO 8601 timestamp with explicit UTC or numeric offset. */
export type TimestampV1 = string;

/** RFC 4122 UUID in canonical string form. */
export type UuidV1 = string;

export enum ProviderKind {
  Whatsapp = "whatsapp",
  Instagram = "instagram",
  TelegramBusiness = "telegram_business",
}

export enum ChannelConnectionStatus {
  Draft = "draft",
  Authorizing = "authorizing",
  Active = "active",
  Degraded = "degraded",
  ReauthorizationRequired = "reauthorization_required",
  Revoked = "revoked",
  Disconnected = "disconnected",
}

export enum LeadStatus {
  Active = "active",
  Merged = "merged",
  Archived = "archived",
}

export enum SalesCaseStatus {
  New = "new",
  AwaitingBusiness = "awaiting_business",
  AwaitingCustomer = "awaiting_customer",
  Qualified = "qualified",
  AppointmentProposed = "appointment_proposed",
  AppointmentBooked = "appointment_booked",
  Won = "won",
  Lost = "lost",
  ClosedUnknown = "closed_unknown",
}

export enum ParticipantSenderType {
  Customer = "customer",
  Bot = "bot",
  Manager = "manager",
  System = "system",
  Unknown = "unknown",
}

export enum MessageDirection {
  Inbound = "inbound",
  Outbound = "outbound",
}

export enum DeliveryStatus {
  Pending = "pending",
  Sent = "sent",
  Delivered = "delivered",
  Read = "read",
  Failed = "failed",
  Unknown = "unknown",
}

export enum CrmOutcomeType {
  Won = "won",
  Lost = "lost",
  Cancelled = "cancelled",
  Unknown = "unknown",
}

export enum WebhookProcessingStatus {
  Received = "received",
  Acknowledged = "acknowledged",
  Processing = "processing",
  Processed = "processed",
  Failed = "failed",
  DeadLetter = "dead_letter",
}

/** JSON scalar values allowed in adapter metadata. */
export type AdapterScalarV1 = string | number | boolean | null;

/**
 * Bounded provider-specific metadata. Keys must not contain sensitive fragments
 * (body, text, content, token, etc.). Values are JSON scalars only.
 */
export type AdapterMetadataV1 = Record<string, AdapterScalarV1>;

export const FORBIDDEN_ADAPTER_METADATA_KEY_PATTERN =
  /body|text|message|content|token|secret|password|authorization|cookie|email|phone|payload/i;

export const FORBIDDEN_CONTENT_FIELD_NAMES = new Set([
  "body",
  "text",
  "content",
  "message_body",
  "message_text",
]);
