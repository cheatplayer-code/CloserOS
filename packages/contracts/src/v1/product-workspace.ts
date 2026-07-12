import type { TimestampV1, UuidV1 } from "./enums.js";

export type FollowUpTaskStatusV1 =
  "open" | "in_progress" | "completed" | "cancelled";

export type FollowUpTaskPriorityV1 = "low" | "normal" | "high" | "urgent";

export interface CursorPageV1 {
  next_cursor: string | null;
}

export interface ApiErrorV1 {
  message?: string;
  detail?: string;
}

export interface DashboardMetricV1 {
  key: string;
  current_value: number;
  previous_value: number;
  delta: number;
}

export interface ManagerPerformanceV1 {
  manager_user_id: UuidV1;
  response_rate_basis_points: number;
  conversion_rate_basis_points: number;
  active_thread_count: number;
}

export interface DashboardResponseV1 {
  formula_version: string;
  window_start: TimestampV1;
  window_end: TimestampV1;
  previous_window_start: TimestampV1;
  previous_window_end: TimestampV1;
  total_conversations: number;
  open_high_severity_findings: number;
  overdue_follow_up_tasks: number;
  metrics: DashboardMetricV1[];
  manager_summaries: ManagerPerformanceV1[];
}

export interface ConversationListItemV1 {
  id: UuidV1;
  channel_connection_id: UuidV1;
  provider: string;
  external_conversation_id: string;
  lifecycle_status: string | null;
  manager_user_id: UuidV1 | null;
  updated_at: TimestampV1;
  open_finding_count: number;
  high_severity_finding_count: number;
  has_unresolved_task: boolean;
}

export interface ConversationListResponseV1 extends CursorPageV1 {
  conversations: ConversationListItemV1[];
}

export interface TimelineMessageV1 {
  message_id: UuidV1;
  sender_type: string;
  direction: string;
  sent_at: TimestampV1;
  received_at: TimestampV1;
  sanitized_text: string | null;
  is_deleted: boolean;
}

export interface AnalysisEvidenceV1 {
  message_id: UuidV1;
}

export interface AnalysisCitationV1 {
  chunk_id: UuidV1;
  document_id: UuidV1;
  document_version_id: UuidV1;
  retrieval_rank: number;
  relevance_basis_points: number;
}

export interface AnalysisFindingV1 {
  id: UuidV1;
  finding_code: string;
  severity: string;
  status: string;
  confidence_basis_points: number;
  created_at: TimestampV1;
  evidence: AnalysisEvidenceV1[];
  citations: AnalysisCitationV1[];
}

export interface AnalysisRunV1 {
  id: UuidV1;
  status: string;
  prompt_version: string;
  rubric_version: string;
  model_provider: string;
  requested_at: TimestampV1;
  completed_at: TimestampV1 | null;
  failure_code: string | null;
  findings: AnalysisFindingV1[];
}

export interface FollowUpTaskV1 {
  id: UuidV1;
  conversation_thread_id: UuidV1;
  source_finding_id: UuidV1 | null;
  title: string;
  status: FollowUpTaskStatusV1;
  priority: FollowUpTaskPriorityV1;
  assigned_membership_id: UuidV1 | null;
  due_at: TimestampV1 | null;
  completed_at: TimestampV1 | null;
  cancelled_at: TimestampV1 | null;
  created_at: TimestampV1;
  updated_at: TimestampV1;
  version: number;
}

export interface ConversationDetailResponseV1 {
  id: UuidV1;
  channel_connection_id: UuidV1;
  external_conversation_id: string;
  lifecycle_status: string | null;
  manager_user_id: UuidV1 | null;
  updated_at: TimestampV1;
  created_at: TimestampV1;
  messages: TimelineMessageV1[];
  analyses: AnalysisRunV1[];
  tasks: FollowUpTaskV1[];
}

export interface FindingCountV1 {
  finding_code: string;
  severity: string;
  count: number;
}

export interface ScorecardComponentsV1 {
  response_rate_basis_points: number;
  conversion_rate_basis_points: number;
  finding_discipline_basis_points: number;
  task_completion_basis_points: number;
}

export interface ManagerScorecardV1 {
  membership_id: UuidV1;
  manager_user_id: UuidV1;
  formula_version: string;
  window_start: TimestampV1;
  window_end: TimestampV1;
  components: ScorecardComponentsV1;
  composite_basis_points: number;
  composite_delta_basis_points: number;
  finding_counts: FindingCountV1[];
  task_counts: Record<string, number>;
}

export interface ManagerListItemV1 {
  membership_id: UuidV1;
  manager_user_id: UuidV1;
  roles: string[];
}

export interface ManagerListResponseV1 {
  managers: ManagerListItemV1[];
}

export interface ManagerScorecardListResponseV1 {
  scorecards: ManagerScorecardV1[];
}

export interface FollowUpTaskListResponseV1 extends CursorPageV1 {
  tasks: FollowUpTaskV1[];
}

export interface CreateFollowUpTaskRequestV1 {
  conversation_thread_id: UuidV1;
  title: string;
  priority?: FollowUpTaskPriorityV1;
  assigned_membership_id?: UuidV1 | null;
  source_finding_id?: UuidV1 | null;
  due_at?: TimestampV1 | null;
}

export interface UpdateFollowUpTaskRequestV1 {
  version: number;
  title?: string;
  priority?: FollowUpTaskPriorityV1;
  assigned_membership_id?: UuidV1 | null;
  due_at?: TimestampV1 | null;
  action?: string;
}

export interface TenantSummaryV1 {
  id: UuidV1;
  name: string;
  status: "active" | "suspended";
  time_zone: string;
  roles: string[];
}

export interface AcceptedResponseV1 {
  accepted: boolean;
}
