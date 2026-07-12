import { describe, expect, it } from "vitest";

import { mapHttpStatusToFailure } from "../lib/auth/errors";

describe("mapHttpStatusToFailure", () => {
  it("maps authentication failures generically", () => {
    const failure = mapHttpStatusToFailure(401, {}, null);
    expect(failure.ok).toBe(false);
    if (!failure.ok) {
      expect(failure.kind).toBe("authentication_failed");
    }
  });

  it("maps security failures generically", () => {
    const failure = mapHttpStatusToFailure(403, {}, null);
    expect(failure.ok).toBe(false);
    if (!failure.ok) {
      expect(failure.kind).toBe("security_failed");
    }
  });

  it("maps sanitized validation errors", () => {
    const failure = mapHttpStatusToFailure(
      422,
      {
        message: "validation failed",
        errors: [
          {
            location: "body.email",
            message: "invalid email",
            type: "value_error",
          },
        ],
      },
      null,
    );

    expect(failure.ok).toBe(false);
    if (!failure.ok) {
      expect(failure.kind).toBe("validation_failed");
      expect(failure.validationErrors?.[0]?.location).toBe("body.email");
    }
  });

  it("maps rate limits with retry duration", () => {
    const failure = mapHttpStatusToFailure(
      429,
      { detail: "too many requests" },
      "45",
    );
    expect(failure.ok).toBe(false);
    if (!failure.ok) {
      expect(failure.kind).toBe("rate_limited");
      expect(failure.retryAfterSeconds).toBe(45);
    }
  });
});
