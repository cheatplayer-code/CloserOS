import type {
  AcceptedResponseV1,
  ConversationDetailResponseV1,
  ConversationListResponseV1,
  CreateFollowUpTaskRequestV1,
  DashboardResponseV1,
  FollowUpTaskListResponseV1,
  FollowUpTaskV1,
  ManagerListResponseV1,
  ManagerScorecardV1,
  TenantSummaryV1,
  UpdateFollowUpTaskRequestV1,
} from "@closeros/contracts";

import { apiRequest } from "./http";

const API_PREFIX = "/api/v1";

export interface DashboardQuery {
  window_start: string;
  window_end: string;
}

export interface ScorecardQuery {
  window_start: string;
  window_end: string;
}

export interface ConversationListQuery {
  cursor?: string;
  limit?: number;
  updated_after?: string;
  updated_before?: string;
  provider?: string;
  manager_user_id?: string;
  lifecycle_status?: string;
  finding_code?: string;
  finding_severity?: string;
  has_unresolved_task?: boolean;
}

export interface TaskListQuery {
  cursor?: string;
  limit?: number;
  status?: string;
  assigned_membership_id?: string;
  conversation_thread_id?: string;
  overdue_only?: boolean;
}

function tenantPath(tenantId: string, suffix: string): string {
  return `${API_PREFIX}/tenants/${tenantId}${suffix}`;
}

export function buildQueryString(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }

  const query = search.toString();
  return query.length > 0 ? `?${query}` : "";
}

export function createProductApiClient() {
  return {
    listTenants() {
      return apiRequest<TenantSummaryV1[]>(`${API_PREFIX}/tenants`);
    },

    getDashboard(tenantId: string, query: DashboardQuery) {
      return apiRequest<DashboardResponseV1>(
        tenantPath(
          tenantId,
          `/dashboard${buildQueryString({
            window_start: query.window_start,
            window_end: query.window_end,
          })}`,
        ),
      );
    },

    listConversations(tenantId: string, query: ConversationListQuery = {}) {
      return apiRequest<ConversationListResponseV1>(
        tenantPath(
          tenantId,
          `/conversations${buildQueryString({
            cursor: query.cursor,
            limit: query.limit,
            updated_after: query.updated_after,
            updated_before: query.updated_before,
            provider: query.provider,
            manager_user_id: query.manager_user_id,
            lifecycle_status: query.lifecycle_status,
            finding_code: query.finding_code,
            finding_severity: query.finding_severity,
            has_unresolved_task: query.has_unresolved_task,
          })}`,
        ),
      );
    },

    getConversation(tenantId: string, conversationId: string) {
      return apiRequest<ConversationDetailResponseV1>(
        tenantPath(tenantId, `/conversations/${conversationId}`),
      );
    },

    enqueueAnalysis(tenantId: string, threadId: string, csrfToken: string) {
      return apiRequest<AcceptedResponseV1>(
        tenantPath(tenantId, `/threads/${threadId}/analyses`),
        {
          method: "POST",
          csrfToken,
        },
      );
    },

    listManagers(tenantId: string) {
      return apiRequest<ManagerListResponseV1>(
        tenantPath(tenantId, "/managers"),
      );
    },

    getScorecard(
      tenantId: string,
      membershipId: string,
      query: ScorecardQuery,
    ) {
      return apiRequest<ManagerScorecardV1>(
        tenantPath(
          tenantId,
          `/managers/${membershipId}/scorecard${buildQueryString({
            window_start: query.window_start,
            window_end: query.window_end,
          })}`,
        ),
      );
    },

    listTasks(tenantId: string, query: TaskListQuery = {}) {
      return apiRequest<FollowUpTaskListResponseV1>(
        tenantPath(
          tenantId,
          `/tasks${buildQueryString({
            cursor: query.cursor,
            limit: query.limit,
            status: query.status,
            assigned_membership_id: query.assigned_membership_id,
            conversation_thread_id: query.conversation_thread_id,
            overdue_only: query.overdue_only,
          })}`,
        ),
      );
    },

    getTask(tenantId: string, taskId: string) {
      return apiRequest<FollowUpTaskV1>(
        tenantPath(tenantId, `/tasks/${taskId}`),
      );
    },

    createTask(
      tenantId: string,
      body: CreateFollowUpTaskRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<FollowUpTaskV1>(tenantPath(tenantId, "/tasks"), {
        method: "POST",
        body,
        csrfToken,
      });
    },

    updateTask(
      tenantId: string,
      taskId: string,
      body: UpdateFollowUpTaskRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<FollowUpTaskV1>(
        tenantPath(tenantId, `/tasks/${taskId}`),
        {
          method: "PATCH",
          body,
          csrfToken,
        },
      );
    },
  };
}

export type ProductApiClient = ReturnType<typeof createProductApiClient>;

export const productApiClient = createProductApiClient();
