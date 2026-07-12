import type {
  AdapterMetadataV1,
  SchemaVersionV1,
  TimestampV1,
  UuidV1,
} from "./enums.js";
import {
  ChannelConnectionStatus,
  CrmOutcomeType,
  DeliveryStatus,
  LeadStatus,
  MessageDirection,
  ParticipantSenderType,
  ProviderKind,
  SalesCaseStatus,
  WebhookProcessingStatus,
} from "./enums.js";

export interface ChannelConnectionV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  provider: ProviderKind;
  external_connection_id: string;
  status: ChannelConnectionStatus;
  adapter_metadata: AdapterMetadataV1;
  created_at: TimestampV1;
  updated_at: TimestampV1;
}

export interface LeadV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  external_identity_id: string;
  status: LeadStatus;
  adapter_metadata: AdapterMetadataV1;
  created_at: TimestampV1;
  updated_at: TimestampV1;
}

export interface SalesCaseV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  status: SalesCaseStatus;
  created_at: TimestampV1;
  updated_at: TimestampV1;
}

export interface ConversationThreadV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  channel_connection_id: UuidV1;
  external_conversation_id: string;
  sales_case_id?: UuidV1 | null;
  lifecycle_status?: SalesCaseStatus | null;
  adapter_metadata: AdapterMetadataV1;
  created_at: TimestampV1;
  updated_at: TimestampV1;
}

export interface MessageV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  conversation_thread_id: UuidV1;
  external_message_id: string;
  sender_type: ParticipantSenderType;
  direction: MessageDirection;
  sent_at: TimestampV1;
  received_at: TimestampV1;
  content_id?: UuidV1 | null;
  reply_to_message_id?: UuidV1 | null;
  adapter_metadata: AdapterMetadataV1;
}

export interface MessageEditEventV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  message_id: UuidV1;
  external_event_id: string;
  occurred_at: TimestampV1;
  content_id?: UuidV1 | null;
  adapter_metadata: AdapterMetadataV1;
}

export interface MessageDeletionEventV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  message_id: UuidV1;
  external_event_id: string;
  occurred_at: TimestampV1;
  adapter_metadata: AdapterMetadataV1;
}

export interface MessageDeliveryStatusEventV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  message_id: UuidV1;
  external_event_id: string;
  occurred_at: TimestampV1;
  delivery_status: DeliveryStatus;
  adapter_metadata: AdapterMetadataV1;
}

export interface ManagerAssignmentV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  manager_user_id: UuidV1;
  conversation_thread_id?: UuidV1 | null;
  sales_case_id?: UuidV1 | null;
  assigned_at: TimestampV1;
}

export interface CrmOutcomeV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  sales_case_id: UuidV1;
  external_deal_id: string;
  outcome_type: CrmOutcomeType;
  occurred_at: TimestampV1;
  adapter_metadata: AdapterMetadataV1;
}

export interface WebhookEventV1 {
  schema_version: SchemaVersionV1;
  id: UuidV1;
  tenant_id: UuidV1;
  channel_connection_id: UuidV1;
  external_event_id: string;
  processing_status: WebhookProcessingStatus;
  received_at: TimestampV1;
  processed_at?: TimestampV1 | null;
  adapter_metadata: AdapterMetadataV1;
}

export type CanonicalEntityV1 =
  | ChannelConnectionV1
  | LeadV1
  | SalesCaseV1
  | ConversationThreadV1
  | MessageV1
  | MessageEditEventV1
  | MessageDeletionEventV1
  | MessageDeliveryStatusEventV1
  | ManagerAssignmentV1
  | CrmOutcomeV1
  | WebhookEventV1;
