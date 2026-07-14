"""Alembic revision: V1 integrity foundation constraints and synthetic provenance.

Revision ID: a1c3e5f7b9d0
Revises: c4e8a2b6d1f0

- Composite FK manager_assignments(tenant_id, manager_user_id) → memberships
- Repair synthetic membership-ID-as-user-ID assignments when possible
- Fail closed when unrepaired invalid assignments remain
- synthetic_seed_manifests / synthetic_seed_resources provenance tables
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c3e5f7b9d0"
down_revision: str | Sequence[str] | None = "c4e8a2b6d1f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE manager_assignments AS assignment
            SET manager_user_id = membership.user_id
            FROM memberships AS membership
            WHERE assignment.tenant_id = membership.tenant_id
              AND assignment.manager_user_id = membership.id
              AND NOT EXISTS (
                  SELECT 1
                  FROM memberships AS existing
                  WHERE existing.tenant_id = assignment.tenant_id
                    AND existing.user_id = assignment.manager_user_id
              )
            """
        )
    )
    invalid = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT COUNT(*) AS invalid_count
                FROM manager_assignments AS assignment
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM memberships AS membership
                    WHERE membership.tenant_id = assignment.tenant_id
                      AND membership.user_id = assignment.manager_user_id
                )
                """
            )
        )
        .scalar_one()
    )
    if int(invalid) > 0:
        raise RuntimeError(
            "a1c3e5f7b9d0 precondition failed: "
            f"{invalid} manager_assignments rows do not reference a tenant membership "
            "(tenant_id, user_id). Repair or delete invalid rows before upgrading."
        )

    op.create_foreign_key(
        op.f("fk_manager_assignments_tenant_manager_user_memberships"),
        "manager_assignments",
        "memberships",
        ["tenant_id", "manager_user_id"],
        ["tenant_id", "user_id"],
    )

    op.create_table(
        "synthetic_seed_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seed_version", sa.String(length=64), nullable=False),
        sa.Column("seed_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("reset_state", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "reset_state IN ('active', 'resetting', 'reset')",
            name=op.f("ck_synthetic_seed_manifests_reset_state"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_synthetic_seed_manifests_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_synthetic_seed_manifests")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_synthetic_seed_manifests_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "seed_run_id",
            name=op.f("uq_synthetic_seed_manifests_tenant_id_seed_run_id"),
        ),
    )
    op.create_index(
        op.f("ix_synthetic_seed_manifests_tenant_reset_state"),
        "synthetic_seed_manifests",
        ["tenant_id", "reset_state"],
        unique=False,
    )
    op.create_index(
        "uq_synthetic_seed_manifests_one_active_per_version",
        "synthetic_seed_manifests",
        ["tenant_id", "seed_version"],
        unique=True,
        postgresql_where=sa.text("reset_state = 'active'"),
    )

    op.create_table(
        "synthetic_seed_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deletion_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "deletion_order >= 0",
            name=op.f("ck_synthetic_seed_resources_deletion_order_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manifest_id"],
            ["synthetic_seed_manifests.tenant_id", "synthetic_seed_manifests.id"],
            name=op.f("fk_synthetic_seed_resources_manifest"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_synthetic_seed_resources")),
        sa.UniqueConstraint(
            "tenant_id",
            "manifest_id",
            "resource_type",
            "resource_id",
            name=op.f("uq_synthetic_seed_resources_tenant_manifest_type_resource"),
        ),
    )
    op.create_index(
        op.f("ix_synthetic_seed_resources_tenant_manifest_order"),
        "synthetic_seed_resources",
        ["tenant_id", "manifest_id", "deletion_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_synthetic_seed_resources_tenant_manifest_order"),
        table_name="synthetic_seed_resources",
    )
    op.drop_table("synthetic_seed_resources")
    op.drop_index(
        "uq_synthetic_seed_manifests_one_active_per_version",
        table_name="synthetic_seed_manifests",
    )
    op.drop_index(
        op.f("ix_synthetic_seed_manifests_tenant_reset_state"),
        table_name="synthetic_seed_manifests",
    )
    op.drop_table("synthetic_seed_manifests")
    op.drop_constraint(
        op.f("fk_manager_assignments_tenant_manager_user_memberships"),
        "manager_assignments",
        type_="foreignkey",
    )
