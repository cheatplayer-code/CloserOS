"""Pydantic schemas for RSTU product workspace APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CursorPageResponse(BaseModel):
    next_cursor: str | None = None


class DashboardMetricResponse(BaseModel):
    key: str
    current_value: int
    previous_value: int
    delta: int


class ManagerPerformanceResponse(BaseModel):
    manager_user_id: UUID
    response_rate_basis_points: int
    conversion_rate_basis_points: int
    active_thread_count: int


class DashboardResponse(BaseModel):
    formula_version: str
    window_start: datetime
    window_end: datetime
    previous_window_start: datetime
    previous_window_end: datetime
    total_conversations: int
    open_high_severity_findings: int
    overdue_follow_up_tasks: int
    metrics: list[DashboardMetricResponse]
    manager_summaries: list[ManagerPerformanceResponse]


class ConversationListItemResponse(BaseModel):
    id: UUID
    channel_connection_id: UUID
    provider: str
    external_conversation_id: str
    lifecycle_status: str | None
    manager_user_id: UUID | None
    updated_at: datetime
    open_finding_count: int
    high_severity_finding_count: int
    has_unresolved_task: bool


class ConversationListResponse(CursorPageResponse):
    conversations: list[ConversationListItemResponse]


class TimelineMessageResponse(BaseModel):
    message_id: UUID
    sender_type: str
    direction: str
    sent_at: datetime
    received_at: datetime
    sanitized_text: str | None
    is_deleted: bool


class AnalysisEvidenceResponse(BaseModel):
    message_id: UUID


class AnalysisCitationResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    retrieval_rank: int
    relevance_basis_points: int


class AnalysisFindingResponse(BaseModel):
    id: UUID
    finding_code: str
    severity: str
    status: str
    confidence_basis_points: int
    created_at: datetime
    evidence: list[AnalysisEvidenceResponse]
    citations: list[AnalysisCitationResponse]


class AnalysisRunResponse(BaseModel):
    id: UUID
    status: str
    prompt_version: str
    rubric_version: str
    model_provider: str
    requested_at: datetime
    completed_at: datetime | None
    failure_code: str | None
    findings: list[AnalysisFindingResponse]


class FollowUpTaskResponse(BaseModel):
    id: UUID
    conversation_thread_id: UUID
    source_finding_id: UUID | None
    title: str
    status: str
    priority: str
    assigned_membership_id: UUID | None
    due_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class ConversationDetailResponse(BaseModel):
    id: UUID
    channel_connection_id: UUID
    external_conversation_id: str
    lifecycle_status: str | None
    manager_user_id: UUID | None
    updated_at: datetime
    created_at: datetime
    messages: list[TimelineMessageResponse]
    analyses: list[AnalysisRunResponse]
    tasks: list[FollowUpTaskResponse]


class AcceptedResponse(BaseModel):
    accepted: bool = True


class FindingCountResponse(BaseModel):
    finding_code: str
    severity: str
    count: int


class ScorecardComponentsResponse(BaseModel):
    response_rate_basis_points: int
    conversion_rate_basis_points: int
    finding_discipline_basis_points: int
    task_completion_basis_points: int


class ManagerScorecardResponse(BaseModel):
    membership_id: UUID
    manager_user_id: UUID
    formula_version: str
    window_start: datetime
    window_end: datetime
    components: ScorecardComponentsResponse
    composite_basis_points: int
    composite_delta_basis_points: int
    finding_counts: list[FindingCountResponse]
    task_counts: dict[str, int]


class ManagerListItemResponse(BaseModel):
    membership_id: UUID
    manager_user_id: UUID
    roles: list[str]


class ManagerListResponse(BaseModel):
    managers: list[ManagerListItemResponse]


class ManagerScorecardListResponse(BaseModel):
    scorecards: list[ManagerScorecardResponse]


class FollowUpTaskListResponse(CursorPageResponse):
    tasks: list[FollowUpTaskResponse]


class CreateFollowUpTaskRequest(BaseModel):
    conversation_thread_id: UUID
    title: str = Field(min_length=1, max_length=200)
    priority: str = "normal"
    assigned_membership_id: UUID | None = None
    source_finding_id: UUID | None = None
    due_at: datetime | None = None


class UpdateFollowUpTaskRequest(BaseModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    priority: str | None = None
    assigned_membership_id: UUID | None = None
    due_at: datetime | None = None
    action: str | None = None
