# ADR-0010: Authentication and session strategy

Status: accepted
Date: 2026-07-11
Decision owners: Product and engineering owner

## Context

CloserOS requires a secure authentication and session architecture before
commercial onboarding. The framework-independent `User` domain entity already
defines lifecycle status only. Authentication credentials, sessions, email
verification, password reset, and MFA must remain separate from domain entities
while integrating with existing tenant access guards.

`CLS-011` requires a documented secure session strategy, modern password
hashing, designed email verification and reset flows, and MFA for privileged
roles before first commercial onboarding. `CLS-012` will later require audited
security-sensitive actions without logging secrets.

## Decision

### Authentication ownership

CloserOS uses self-hosted authentication in the FastAPI backend.

No paid external authentication provider is required for the first release.

Authentication data remains separate from the framework-independent `User`
domain entity.

Email, password credentials, sessions, verification tokens, reset tokens, and
MFA authenticators belong to the authentication subsystem.

Do not add email or password fields to the existing `User` entity.

### Login method

Initial login method is verified email plus password.

Future OIDC or enterprise SSO may be added through a separate adapter and ADR.

No social login is included initially.

Passwordless email links are not included initially.

### Password storage

Passwords are never stored or logged in plaintext.

Use Argon2id through a maintained library.

Initial minimum parameters:

- memory cost: 19 MiB;
- iterations: 2;
- parallelism: 1.

Parameters must be stored with the hash.

Parameters may be increased after deployment benchmarking.

A password is rehashed after successful authentication when stored parameters are
below the current policy.

Do not create custom cryptography.

Do not use SHA-256, MD5, SHA-1, or reversible encryption for password storage.

### Session model

Use opaque server-side sessions, not self-contained JWT access tokens for browser
sessions.

Generate session tokens using a cryptographically secure random generator with
256 bits of randomness.

The raw session token exists only in the browser cookie and during the request
that creates it.

Store only a SHA-256 hash of the session token in PostgreSQL.

PostgreSQL is the source of truth for sessions.

Redis may later cache session lookups but is never the authority.

Session records will later include:

- `id`;
- `user_id`;
- `created_at`;
- `last_seen_at`;
- `expires_at`;
- `revoked_at`;
- authentication assurance level;
- MFA completion state;
- token hash;
- request-safe metadata needed for abuse detection.

Do not store raw session tokens.

### Session cookie

Use a production cookie with these properties:

- name: `__Host-closeros_session`;
- `Secure`;
- `HttpOnly`;
- `SameSite=Lax`;
- `Path=/`;
- no `Domain` attribute;
- never place the token in URLs;
- never expose the token to frontend JavaScript.

Local development may use a separate explicitly development-only cookie
configuration because `Secure` cookies require HTTPS.

### Session expiration and rotation

- authenticated session idle timeout: 30 minutes;
- authenticated session absolute timeout: 12 hours;
- pending-MFA session timeout: 5 minutes;
- rotate the session token after:
  - successful login;
  - successful MFA;
  - password reset;
  - password change;
  - privilege or membership change;
  - suspicious authentication event.

Logout revokes the server-side session.

Password reset revokes all existing sessions for that user.

Tenant suspension, user disabling, membership suspension, and membership
removal deny access even when a session has not yet expired.

### CSRF protection

Cookie-authenticated state-changing requests require CSRF protection.

Use a server-issued CSRF token bound to the authenticated session.

Validate the CSRF token server-side for unsafe HTTP methods.

`SameSite` is defense in depth and is not the only CSRF control.

Do not use GET requests for state-changing operations.

### Email verification

Verification uses a cryptographically random 256-bit token.

Store only the token hash.

Token is single-use.

Token expires after 24 hours.

Issuing a new token invalidates earlier active verification tokens.

Verification responses must not expose secrets.

Email sending will be implemented later through a provider adapter.

This ADR does not select an email provider.

### Password reset

Reset request responses must be generic and must not reveal whether an account
exists.

Reset tokens use 256 bits of cryptographically secure randomness.

Store only the token hash.

Token is single-use.

Token expires after 30 minutes.

Issuing a new reset token invalidates earlier active reset tokens.

Successful reset invalidates all active sessions.

Reset endpoints require rate limiting.

Password reset must not automatically log the user in.

### MFA

Define privileged roles as:

- `Role.OWNER`;
- `Role.SALES_HEAD`;
- `Role.COMPLIANCE_ADMIN`.

Requirements:

- privileged users must enroll MFA before first commercial onboarding;
- privileged users cannot access privileged functions without completed MFA;
- WebAuthn/passkeys are the preferred phishing-resistant method;
- TOTP is an allowed initial fallback;
- SMS is not an accepted MFA method;
- recovery codes are random, hashed at rest, single-use, and displayed only
  once;
- MFA recovery and reset are security-sensitive audited actions;
- implementation libraries and WebAuthn/TOTP details belong to later tasks.

### Enumeration and abuse resistance

Login, verification, and reset responses must avoid exposing whether an email
exists.

Apply rate limits by account identifier and network source.

Do not permanently lock accounts solely because of unauthenticated failed
attempts.

Record security events without logging passwords, raw tokens, MFA secrets, email
contents, or session cookies.

### Authorization boundary

Authentication proves identity only.

Existing tenant access guards remain authoritative for active tenant, user, and
membership checks.

Role-specific authorization will be implemented separately.

Never trust `tenant_id` or roles supplied by the frontend.

Every request resolves tenant and role information server-side.

### Explicit non-goals

Do not include:

- OAuth provider implementation;
- social login;
- enterprise SSO implementation;
- authentication database schema;
- SQLAlchemy models;
- Alembic migrations;
- FastAPI routes;
- Next.js login UI;
- email provider integration;
- actual password hashing code;
- actual session token generation code;
- actual MFA implementation.

## Alternatives considered

### Paid hosted authentication provider

Rejected because the first implementation must not depend on a paid external
service and tenant controls still require backend integration.

### Browser JWT stored in localStorage

Rejected because token exposure to JavaScript increases the impact of XSS and
makes immediate server-side revocation harder.

### Stateless browser JWT in HttpOnly cookie

Rejected as the primary session model because suspension, membership changes,
password reset, and immediate revocation require authoritative server-side state.

### Redis-only sessions

Rejected because Redis is not the system of record.

### SMS-only MFA

Rejected because it is weaker and creates provider cost and account-recovery
risk.

## Consequences

- PostgreSQL session lookup is required on authenticated requests.
- Session cleanup and revocation jobs will be required later.
- Local development and production cookie behavior differ because production
  requires HTTPS.
- Email verification, reset, and MFA require later persistence and provider
  tasks.
- Future SSO can coexist with server-side application sessions.
- Authentication and authorization remain separate concerns.

## Security and privacy impact

- No raw passwords or tokens in logs.
- Token hashes are still confidential security data.
- Email addresses are personal data.
- MFA secrets require encryption at rest.
- Session lifecycle events require audit records later.
- Generic error responses reduce account enumeration.
- Privileged access requires MFA.

## Migration and rollback/remediation

- No runtime migration is required because this ADR adds documentation only.
- A future provider migration must preserve stable `User` IDs and tenant
  memberships.
- All sessions can be revoked if token or session storage is compromised.
- Password hash parameters can be upgraded on successful login.

## Sources verified

- OWASP Session Management Cheat Sheet — verified 2026-07-11
- OWASP Password Storage Cheat Sheet — verified 2026-07-11
- OWASP Forgot Password Cheat Sheet — verified 2026-07-11
- NIST SP 800-63B / 800-63-4 — verified 2026-07-11
- CloserOS `SECURITY_COMPLIANCE.md`
- CloserOS `TASKS.md` CLS-011
