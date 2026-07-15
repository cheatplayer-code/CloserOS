/** Reply suggestion copilot and buyer memory API client. */

import { apiRequest } from "./http";

export interface ReplySuggestionCandidateV1 {
  id: string;
  candidate_key: string;
  text: string;
  objective: string;
  confidence_basis_points: number;
  confidence_label: string;
  evidence_message_ids: string[];
  product_references: Array<{ product_id: string; variant_id: string }>;
  knowledge_citation_ids: string[];
  warnings: string[];
  is_recommended: boolean;
  created_at: string;
}

export interface ReplySuggestionRunV1 {
  id: string;
  conversation_thread_id: string;
  lead_id: string | null;
  status: string;
  prompt_version: string;
  rubric_version: string;
  provider_code: string | null;
  model_code: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_milliseconds: number | null;
  customer_state: {
    intent: string;
    sales_stage: string;
    primary_objection: string | null;
    urgency: string;
    language: string;
    missing_information: string[];
  } | null;
  next_best_action: { action_code: string; explanation: string } | null;
  escalation_reason: string | null;
  cost_status: string;
  estimated_cost_microunits: number | null;
  failure_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  candidates: ReplySuggestionCandidateV1[];
}

export interface BuyerMemoryFactV1 {
  id: string;
  fact_type: string;
  normalized_value: string;
  display_value: string;
  status: string;
  confidence_basis_points: number;
  confidence_label: string;
  source_message_id: string | null;
  conversation_thread_id: string;
}

const API_PREFIX = "/api/v1";

function tenantPath(tenantId: string, suffix: string): string {
  return `${API_PREFIX}/tenants/${tenantId}${suffix}`;
}

export function createReplyApiClient() {
  return {
    generateSuggestions(tenantId: string, threadId: string, csrfToken: string) {
      return apiRequest<ReplySuggestionRunV1>(
        tenantPath(tenantId, `/conversations/${threadId}/reply-suggestions`),
        { method: "POST", body: {}, csrfToken },
      );
    },
    getLatestSuggestions(tenantId: string, threadId: string) {
      return apiRequest<ReplySuggestionRunV1>(
        tenantPath(
          tenantId,
          `/conversations/${threadId}/reply-suggestions/latest`,
        ),
      );
    },
    selectCandidate(
      tenantId: string,
      runId: string,
      candidateId: string,
      body: { edited_text?: string; feedback?: string },
      csrfToken: string,
    ) {
      return apiRequest<{
        run_id: string;
        candidate_id: string;
        outbound_message_id: string;
        draft_status: string;
      }>(
        tenantPath(
          tenantId,
          `/reply-suggestions/${runId}/candidates/${candidateId}/select`,
        ),
        { method: "POST", body, csrfToken },
      );
    },
    rejectRun(tenantId: string, runId: string, csrfToken: string) {
      return apiRequest<{ status: string }>(
        tenantPath(tenantId, `/reply-suggestions/${runId}/reject`),
        { method: "POST", body: {}, csrfToken },
      );
    },
    listThreadMemory(tenantId: string, threadId: string) {
      return apiRequest<{ facts: BuyerMemoryFactV1[] }>(
        tenantPath(tenantId, `/conversations/${threadId}/memory`),
      );
    },
    confirmMemory(
      tenantId: string,
      factId: string,
      sourceMessageId: string,
      csrfToken: string,
    ) {
      return apiRequest<BuyerMemoryFactV1>(
        tenantPath(tenantId, `/memory/${factId}/confirm`),
        {
          method: "POST",
          body: { source_message_id: sourceMessageId },
          csrfToken,
        },
      );
    },
    correctMemory(
      tenantId: string,
      factId: string,
      body: {
        normalized_value: string;
        display_value: string;
        source_message_id?: string;
      },
      csrfToken: string,
    ) {
      return apiRequest<BuyerMemoryFactV1>(
        tenantPath(tenantId, `/memory/${factId}/correct`),
        { method: "POST", body, csrfToken },
      );
    },
    rejectMemory(tenantId: string, factId: string, csrfToken: string) {
      return apiRequest<BuyerMemoryFactV1>(
        tenantPath(tenantId, `/memory/${factId}/reject`),
        { method: "POST", body: {}, csrfToken },
      );
    },
    deleteMemory(tenantId: string, factId: string, csrfToken: string) {
      return apiRequest<{ status: string }>(
        tenantPath(tenantId, `/memory/${factId}`),
        {
          method: "DELETE",
          csrfToken,
        },
      );
    },
  };
}

export const replyApiClient = createReplyApiClient();
