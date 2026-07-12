# Authentication HTTP API

Block C exposes framework-independent authentication workflows at
`/api/v1/auth` through a secure FastAPI layer.

## Routes

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/email-verification/request`
- `POST /api/v1/auth/email-verification/confirm`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/mfa/complete`
- `GET /api/v1/auth/session`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`
- `POST /api/v1/auth/password/change`

Process health remains at `/health`. Database readiness is exposed at `/ready`
without connection details.

## Browser security

- Production session cookie: `__Host-closeros_session` (`Secure`, `HttpOnly`,
  `SameSite=Lax`, `Path=/`, no `Domain`).
- Development session cookie: `closeros_dev_session` (`HttpOnly`, `SameSite=Lax`,
  `Path=/`).
- CSRF tokens are HMAC-SHA-256 values bound to the raw session token using
  `AUTH_CSRF_SECRET`. Unsafe cookie-authenticated requests require
  `X-CSRF-Token` and an allowed `Origin`.
- Raw session tokens never appear in JSON responses or URLs.

## Trusted server-side policy

Login MFA requirements are resolved only through the injected
`MfaRequirementPolicy` port after the user identity is known. Clients cannot
submit an MFA-required flag.

## Notification delivery

Email verification and password-reset workflows may produce internal delivery
payloads after the database transaction commits. Block C defines an async
`NotificationDispatcher` port only. Reliable outbox-backed delivery will be
added with the transactional outbox subsystem.

## Rate limiting

An async `RateLimiter` port enforces bounded limits using HMAC-derived keys.
Production requires an explicit distributed limiter implementation. Redis is
not used in Block C.

## Production configuration

Production startup fails closed unless explicit adapters are provided for:

- MFA requirement policy;
- notification dispatcher;
- distributed rate limiter;
- strong `AUTH_CSRF_SECRET` and `AUTH_RATE_LIMIT_SECRET`;
- HTTPS-only `AUTH_ALLOWED_ORIGINS`.
