import type { TimestampV1, UuidV1 } from "./enums.js";

export type WhatsAppConnectionStatusV1 =
  "draft" | "verification_pending" | "active" | "degraded" | "disabled";

export type WebhookSubscriptionStatusV1 =
  "not_configured" | "pending" | "subscribed" | "failed";

export type ProviderCapabilityV1 =
  | "inbound_text"
  | "interactive_reply"
  | "reaction"
  | "message_status"
  | "media_reference"
  | "outbound_free_form_text"
  | "outbound_approved_template";

export type OutboundMessageKindV1 = "free_form_text" | "approved_template";

export type OutboundMessageStatusV1 =
  | "draft"
  | "pending_approval"
  | "approved"
  | "queued"
  | "sending"
  | "provider_accepted"
  | "delivery_unknown"
  | "delivered"
  | "read"
  | "failed"
  | "cancelled";

export type ProviderTemplateApprovalStatusV1 =
  "approved" | "pending" | "rejected" | "paused" | "disabled";

export type MediaQuarantineStatusV1 =
  | "quarantined_pending_scan"
  | "scan_passed"
  | "scan_failed"
  | "fetch_unavailable";

export interface WhatsAppConnectionV1 {
  id: UuidV1;
  channel_connection_id: UuidV1;
  provider: "whatsapp_cloud";
  app_id: string;
  waba_id: string;
  phone_number_id: string;
  display_phone_number: string | null;
  graph_api_version: string;
  access_token_ref: string | null;
  app_secret_ref: string | null;
  verify_token_ref: string | null;
  status: WhatsAppConnectionStatusV1;
  webhook_subscription_status: WebhookSubscriptionStatusV1;
  capabilities: ProviderCapabilityV1[];
  webhook_public_key: string;
  webhook_callback_path: string;
  created_at: TimestampV1;
  updated_at: TimestampV1;
  last_verified_at: TimestampV1 | null;
  version: number;
}

export interface WhatsAppConnectionListResponseV1 {
  connections: WhatsAppConnectionV1[];
}

export interface CreateWhatsAppConnectionRequestV1 {
  app_id: string;
  waba_id: string;
  phone_number_id: string;
  display_phone_number?: string | null;
  graph_api_version?: string;
  access_token_ref?: string | null;
  app_secret_ref?: string | null;
  verify_token_ref?: string | null;
}

export interface UpdateWhatsAppConnectionRequestV1 {
  version: number;
  app_id: string;
  waba_id: string;
  phone_number_id: string;
  display_phone_number?: string | null;
  graph_api_version: string;
  access_token_ref?: string | null;
  app_secret_ref?: string | null;
  verify_token_ref?: string | null;
}

export interface WhatsAppConnectionActionRequestV1 {
  version: number;
}

export interface ProviderTemplateV1 {
  id: UuidV1;
  whatsapp_connection_id: UuidV1;
  provider_template_id: string;
  name: string;
  language_code: string;
  category: string;
  approval_status: ProviderTemplateApprovalStatusV1;
  component_shape: string[];
  parameter_count: number;
  last_synced_at: TimestampV1;
  version: number;
}

export interface ProviderTemplateListResponseV1 {
  templates: ProviderTemplateV1[];
}

export interface OutboundMessageV1 {
  id: UuidV1;
  conversation_thread_id: UuidV1;
  channel_connection_id: UuidV1;
  kind: OutboundMessageKindV1;
  status: OutboundMessageStatusV1;
  provider_template_id: UuidV1 | null;
  created_by_user_id: UuidV1;
  approved_by_user_id: UuidV1 | null;
  failure_code: string | null;
  created_at: TimestampV1;
  approved_at: TimestampV1 | null;
  queued_at: TimestampV1 | null;
  sent_at: TimestampV1 | null;
  completed_at: TimestampV1 | null;
  updated_at: TimestampV1;
  version: number;
}

export interface CreateOutboundDraftRequestV1 {
  kind: OutboundMessageKindV1;
  body_text?: string | null;
  provider_template_id?: UuidV1 | null;
  template_parameters?: string[] | null;
}

export interface OutboundMessageActionRequestV1 {
  version: number;
}

export interface MediaQuarantineReferenceV1 {
  id: UuidV1;
  conversation_thread_id: UuidV1;
  media_type: string;
  quarantine_status: MediaQuarantineStatusV1;
  created_at: TimestampV1;
}
