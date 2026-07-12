import { describe, expect, it } from "vitest";

import {
  buildSignInHref,
  resolvePostAuthPath,
  sanitizeReturnPath,
} from "../lib/auth/return-path";

describe("return path safety", () => {
  it("accepts safe relative paths", () => {
    expect(sanitizeReturnPath("/app")).toBe("/app");
    expect(sanitizeReturnPath("/settings/security")).toBe("/settings/security");
  });

  it("rejects external and auth redirect targets", () => {
    expect(sanitizeReturnPath("https://evil.test")).toBeNull();
    expect(sanitizeReturnPath("//evil.test")).toBeNull();
    expect(sanitizeReturnPath("/auth/sign-in")).toBeNull();
  });

  it("builds sign-in links with encoded return paths", () => {
    expect(buildSignInHref("/app")).toBe("/auth/sign-in?returnTo=%2Fapp");
    expect(buildSignInHref("https://evil.test")).toBe("/auth/sign-in");
  });

  it("falls back to the workspace route", () => {
    expect(resolvePostAuthPath(null)).toBe("/app");
    expect(resolvePostAuthPath("/settings/security")).toBe(
      "/settings/security",
    );
  });
});
