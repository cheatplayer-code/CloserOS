"""Initial authentication persistence schema.

Revision ID: 7f3a9c2e1b04
Revises:
Create Date: 2026-07-12 06:30:00.000000

Creates the four authentication tables required by ADR-0010:

- ``users`` — minimal user lifecycle persistence;
- ``authentication_credentials`` — email/password credentials with Argon2id PHC;
- ``authentication_sessions`` — opaque server-side sessions with hashed tokens;
- ``authentication_one_time_tokens`` — email-verification and password-reset tokens.

Raw passwords and raw authentication tokens are never stored.

Rollback / remediation
----------------------
The downgrade drops all four tables in reverse dependency order. This is safe
only on an empty schema or in a dedicated test database. On a populated
production schema, prefer forward remediation: create replacement tables,
backfill, cut over, and retire old tables through expand/migrate/contract.

Locking risks
-------------
Table creation uses standard DDL and is safe on an empty database. Future
migrations that add indexes concurrently or rewrite large tables must be
reviewed separately. Bulk revocation updates acquire row-level locks on
matching session or token rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7f3a9c2e1b04"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name=op.f("ck_users_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )

    op.create_table(
        "authentication_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "email_verified_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_authentication_credentials_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authentication_credentials")),
        sa.UniqueConstraint("email", name=op.f("uq_authentication_credentials_email")),
        sa.UniqueConstraint(
            "user_id",
            name=op.f("uq_authentication_credentials_user_id"),
        ),
    )

    op.create_table(
        "authentication_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("assurance_level", sa.String(length=32), nullable=False),
        sa.Column("mfa_completed", sa.Boolean(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32",
            name=op.f("ck_authentication_sessions_token_hash_length"),
        ),
        sa.CheckConstraint(
            "stage IN ('pending_mfa', 'authenticated')",
            name=op.f("ck_authentication_sessions_stage"),
        ),
        sa.CheckConstraint(
            "assurance_level IN ('single_factor', 'multi_factor')",
            name=op.f("ck_authentication_sessions_assurance_level"),
        ),
        sa.CheckConstraint(
            "("
            "stage = 'pending_mfa' AND assurance_level = 'single_factor' "
            "AND mfa_completed = false"
            ") OR ("
            "stage = 'authenticated' AND assurance_level = 'single_factor' "
            "AND mfa_completed = false"
            ") OR ("
            "stage = 'authenticated' AND assurance_level = 'multi_factor' "
            "AND mfa_completed = true"
            ")",
            name=op.f("ck_authentication_sessions_stage_assurance_mfa"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_authentication_sessions_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authentication_sessions")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_authentication_sessions_token_hash"),
        ),
    )
    op.create_index(
        op.f("ix_authentication_sessions_user_id"),
        "authentication_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authentication_sessions_expires_at"),
        "authentication_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authentication_sessions_revoked_at"),
        "authentication_sessions",
        ["revoked_at"],
        unique=False,
    )

    op.create_table(
        "authentication_one_time_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32",
            name=op.f("ck_authentication_one_time_tokens_token_hash_length"),
        ),
        sa.CheckConstraint(
            "purpose IN ('email_verification', 'password_reset')",
            name=op.f("ck_authentication_one_time_tokens_purpose"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_authentication_one_time_tokens_user_id_users"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_authentication_one_time_tokens"),
        ),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_authentication_one_time_tokens_token_hash"),
        ),
    )
    op.create_index(
        op.f("ix_authentication_one_time_tokens_user_id_purpose"),
        "authentication_one_time_tokens",
        ["user_id", "purpose"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authentication_one_time_tokens_expires_at"),
        "authentication_one_time_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_authentication_one_time_tokens_expires_at"),
        table_name="authentication_one_time_tokens",
    )
    op.drop_index(
        op.f("ix_authentication_one_time_tokens_user_id_purpose"),
        table_name="authentication_one_time_tokens",
    )
    op.drop_table("authentication_one_time_tokens")
    op.drop_index(
        op.f("ix_authentication_sessions_revoked_at"),
        table_name="authentication_sessions",
    )
    op.drop_index(
        op.f("ix_authentication_sessions_expires_at"),
        table_name="authentication_sessions",
    )
    op.drop_index(
        op.f("ix_authentication_sessions_user_id"),
        table_name="authentication_sessions",
    )
    op.drop_table("authentication_sessions")
    op.drop_table("authentication_credentials")
    op.drop_table("users")
