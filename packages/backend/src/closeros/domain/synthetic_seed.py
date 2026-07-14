"""Synthetic demo seed provenance for fail-closed scoped reset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SyntheticSeedResetState(StrEnum):
    ACTIVE = "active"
    RESETTING = "resetting"
    RESET = "reset"


class SyntheticSeedResourceType(StrEnum):
    USER = "user"
    MEMBERSHIP = "membership"
    CHANNEL_CONNECTION = "channel_connection"
    LEAD = "lead"
    SALES_CASE = "sales_case"
    CONVERSATION_THREAD = "conversation_thread"
    MANAGER_ASSIGNMENT = "manager_assignment"
    CRM_OUTCOME = "crm_outcome"
    MESSAGE = "message"
    ENCRYPTED_CONTENT = "encrypted_content"
    OUTBOX_JOB = "outbox_job"
    FOLLOW_UP_TASK = "follow_up_task"
    TENANT_AI_POLICY = "tenant_ai_policy"
    ANALYSIS_RUN = "analysis_run"
    FINDING = "finding"
    FINDING_EVIDENCE = "finding_evidence"
    SANITIZATION = "sanitization"
    METRIC_SNAPSHOT = "metric_snapshot"


# Higher deletion_order is deleted first (dependents before parents).
RESOURCE_DELETION_ORDER: dict[SyntheticSeedResourceType, int] = {
    SyntheticSeedResourceType.FOLLOW_UP_TASK: 110,
    SyntheticSeedResourceType.FINDING_EVIDENCE: 100,
    SyntheticSeedResourceType.FINDING: 90,
    SyntheticSeedResourceType.ANALYSIS_RUN: 80,
    SyntheticSeedResourceType.SANITIZATION: 70,
    SyntheticSeedResourceType.OUTBOX_JOB: 60,
    SyntheticSeedResourceType.MESSAGE: 45,
    SyntheticSeedResourceType.MANAGER_ASSIGNMENT: 40,
    SyntheticSeedResourceType.CRM_OUTCOME: 35,
    SyntheticSeedResourceType.METRIC_SNAPSHOT: 30,
    SyntheticSeedResourceType.ENCRYPTED_CONTENT: 25,
    SyntheticSeedResourceType.CONVERSATION_THREAD: 20,
    SyntheticSeedResourceType.SALES_CASE: 15,
    SyntheticSeedResourceType.LEAD: 10,
    SyntheticSeedResourceType.CHANNEL_CONNECTION: 8,
    SyntheticSeedResourceType.TENANT_AI_POLICY: 6,
    SyntheticSeedResourceType.MEMBERSHIP: 4,
    SyntheticSeedResourceType.USER: 2,
}


@dataclass(frozen=True, slots=True)
class SyntheticManagerIdentity:
    user_id: UUID
    membership_id: UUID


@dataclass(frozen=True, slots=True)
class SyntheticSeedManifest:
    id: UUID
    tenant_id: UUID
    seed_version: str
    seed_run_id: UUID
    created_at: datetime
    reset_state: SyntheticSeedResetState


@dataclass(frozen=True, slots=True)
class SyntheticSeedResource:
    id: UUID
    tenant_id: UUID
    manifest_id: UUID
    resource_type: SyntheticSeedResourceType
    resource_id: UUID
    deletion_order: int


@dataclass(frozen=True, slots=True)
class SyntheticResetPlan:
    tenant_id: UUID
    manifest_id: UUID
    counts_by_type: dict[str, int]
    total_resources: int


__all__ = [
    "RESOURCE_DELETION_ORDER",
    "SyntheticManagerIdentity",
    "SyntheticResetPlan",
    "SyntheticSeedManifest",
    "SyntheticSeedResetState",
    "SyntheticSeedResource",
    "SyntheticSeedResourceType",
]
