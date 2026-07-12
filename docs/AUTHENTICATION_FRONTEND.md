# Frontend authentication (Block D)

The Next.js app calls the Block C FastAPI authentication API directly from the
browser using cookie credentials and CSRF headers.

## Local URLs

Use the same hostname family for frontend and API during browser testing:

- frontend: `http://localhost:3000`
- API: `http://localhost:8000`

Do not mix `localhost` and `127.0.0.1` in the same browser session. Configure
`AUTH_ALLOWED_ORIGINS` on the API to include the exact frontend origin.

Set in an untracked local `.env`:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Browser integration

- Session cookies remain HttpOnly; JavaScript never reads the raw session token.
- Unsafe authenticated requests send `X-CSRF-Token` from in-memory auth state.
- The browser supplies the allowed `Origin` header automatically.
- Pending MFA stores only CSRF metadata in `sessionStorage` to survive refresh.
- Email verification and password reset use manual 43-character token entry until
  a safe email-link exchange design is implemented.

## Remaining provider work

- concrete email delivery and outbox;
- WebAuthn ceremony UI;
- server-side TOTP provisioning;
- distributed rate limiting;
- audit events;
- production CSP and deployment hardening.
