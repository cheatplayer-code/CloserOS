# Authentication database migrations

Alembic migrations for the authentication persistence subsystem live under
`packages/backend/src/closeros/infrastructure/migrations`.

## Initial revision

- **Revision ID:** `7f3a9c2e1b04`
- **Tables:** `users`, `authentication_credentials`, `authentication_sessions`,
  `authentication_one_time_tokens`

## Audit revision

- **Revision ID:** `8e4b1d0f6a23`
- **Revises:** `7f3a9c2e1b04`
- **Table:** `audit_events` with append-only trigger, query indexes, and domain-aligned
  CHECK constraints

## Platform persistence revision

- **Revision ID:** `d4e8f1a2b3c5`
- **Revises:** `8e4b1d0f6a23`
- **Tables:** `tenants`, `memberships`, `membership_roles`, `invitations`,
  `invitation_roles`, `channel_connections`, `leads`, `sales_cases`,
  `conversation_threads`, `messages`, `message_edit_events`,
  `message_deletion_events`, `message_delivery_status_events`,
  `manager_assignments`, `crm_outcomes`, `webhook_events`
- **Audit changes:** extends `audit_events` action and target_type CHECK constraints
  for tenant, membership, invitation, channel connection, and manager assignment
  lifecycle events

Raw passwords and raw authentication tokens are never stored. Session and
one-time-token tables store only 32-byte SHA-256 hashes.

## Running migrations locally

Set `DATABASE_URL` to a PostgreSQL URL (see `.env.example`), then:

```bash
uv run alembic -c path/to/config upgrade head
```

Programmatic use in tests builds the Alembic configuration through
`closeros.infrastructure.alembic_config.build_alembic_config`.

## Rollback / remediation

The initial downgrade drops all four authentication tables. This is safe only on
an empty schema or in an isolated test database. On populated production data,
use expand/migrate/contract instead of destructive downgrade.

## Locking risks

Initial table creation is safe on an empty database. Future migrations that add
indexes concurrently or rewrite large tables require separate locking review.

## Dependencies

- **SQLAlchemy 2.x** — async ORM and Core access;
- **Alembic** — forward migrations;
- **psycopg 3** — PostgreSQL driver with async and pool support;
- **argon2-cffi** — Argon2id password hashing per ADR-0010.
