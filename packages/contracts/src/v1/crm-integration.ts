import type { TimestampV1, UuidV1 } from "./enums.js";

export type CrmProviderCodeV1 = "bitrix24";
export type CrmConnectionStatusV1 =
  | "draft"
  | "active"
  | "degraded"
  | "reauthorization_required"
  | "revoked"
  | "disabled";

export interface CrmConnectionV1 {
  id: UuidV1;
  provider: CrmProviderCodeV1;
  portal_domain: string | null;
  client_id_ref: string | null;
  client_secret_ref: string | null;
  access_token_ref: string | null;
  refresh_token_ref: string | null;
  status: CrmConnectionStatusV1;
  created_at: TimestampV1;
  updated_at: TimestampV1;
  last_verified_at: TimestampV1 | null;
  last_successful_sync_at: TimestampV1 | null;
  version: number;
}

export interface CrmConnectionListResponseV1 {
  connections: CrmConnectionV1[];
}

export interface CreateCrmConnectionRequestV1 {
  provider: CrmProviderCodeV1;
  portal_domain?: string | null;
  client_id_ref?: string | null;
  client_secret_ref?: string | null;
  access_token_ref?: string | null;
  refresh_token_ref?: string | null;
}

export interface UpdateCrmConnectionRequestV1 extends CreateCrmConnectionRequestV1 {
  version: number;
}

export interface CrmConnectionActionRequestV1 {
  version: number;
}

export interface CrmSyncAttemptV1 {
  id: UuidV1;
  direction: "inbound" | "outbound";
  status: "started" | "succeeded" | "failed";
  resource_type: string;
  started_at: TimestampV1;
  finished_at: TimestampV1 | null;
  records_seen: number;
  records_changed: number;
  error_code: string | null;
}

export interface CrmSyncStatusResponseV1 {
  attempts: CrmSyncAttemptV1[];
}
