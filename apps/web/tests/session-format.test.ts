import { describe, expect, it } from "vitest";

import {
  formatAssuranceLevel,
  formatExpiryLabel,
  toSessionMetadataFromLogin,
  toSessionMetadataFromSession,
} from "../lib/auth/session-format";

describe("session formatting", () => {
  it("maps authenticated login responses", () => {
    const session = toSessionMetadataFromLogin({
      state: "authenticated",
      csrf_token: "csrf",
      expires_at: "2026-07-12T12:00:00.000Z",
      user_id: "00000000-0000-0000-0000-000000000010",
      session_id: "00000000-0000-0000-0000-000000000100",
      assurance_level: "multi_factor",
    });

    expect(session?.assuranceLevel).toBe("multi_factor");
    expect(session?.csrfToken).toBe("csrf");
  });

  it("ignores pending MFA login responses", () => {
    expect(
      toSessionMetadataFromLogin({
        state: "mfa_required",
        csrf_token: "csrf",
        expires_at: "2026-07-12T12:00:00.000Z",
      }),
    ).toBeNull();
  });

  it("maps session responses", () => {
    const session = toSessionMetadataFromSession({
      user_id: "00000000-0000-0000-0000-000000000010",
      session_id: "00000000-0000-0000-0000-000000000100",
      assurance_level: "single_factor",
      expires_at: "2026-07-12T12:00:00.000Z",
      csrf_token: "csrf",
    });

    expect(session.userId).toBe("00000000-0000-0000-0000-000000000010");
  });

  it("formats assurance labels", () => {
    expect(formatAssuranceLevel("multi_factor")).toBe("Multi-factor");
    expect(formatAssuranceLevel("single_factor")).toBe("Single-factor");
  });

  it("formats expiry labels", () => {
    const label = formatExpiryLabel(
      new Date(Date.now() + 90 * 60_000).toISOString(),
      new Date(),
    );
    expect(label).toContain("remaining");
  });
});
