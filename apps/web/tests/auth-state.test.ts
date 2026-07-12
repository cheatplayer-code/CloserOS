import { describe, expect, it } from "vitest";

import { authReducer, initialAuthSnapshot } from "../lib/auth/auth-state";

describe("authReducer", () => {
  it("starts in loading state", () => {
    expect(initialAuthSnapshot().phase).toBe("loading");
  });

  it("transitions to authenticated state", () => {
    const next = authReducer(initialAuthSnapshot(), {
      type: "set_authenticated",
      session: {
        userId: "user-1",
        sessionId: "session-1",
        assuranceLevel: "single_factor",
        expiresAt: "2026-07-12T12:00:00.000Z",
        csrfToken: "csrf",
      },
    });

    expect(next.phase).toBe("authenticated");
    expect(next.session?.csrfToken).toBe("csrf");
  });

  it("transitions to pending MFA state", () => {
    const next = authReducer(initialAuthSnapshot(), {
      type: "set_pending_mfa",
      pendingMfa: {
        csrfToken: "csrf",
        expiresAt: "2026-07-12T12:00:00.000Z",
      },
    });

    expect(next.phase).toBe("pending_mfa");
    expect(next.pendingMfa?.csrfToken).toBe("csrf");
  });

  it("clears state on logout", () => {
    const authenticated = authReducer(initialAuthSnapshot(), {
      type: "set_authenticated",
      session: {
        userId: "user-1",
        sessionId: "session-1",
        assuranceLevel: "multi_factor",
        expiresAt: "2026-07-12T12:00:00.000Z",
        csrfToken: "csrf",
      },
    });

    const cleared = authReducer(authenticated, { type: "clear" });
    expect(cleared.phase).toBe("anonymous");
    expect(cleared.session).toBeNull();
  });
});
