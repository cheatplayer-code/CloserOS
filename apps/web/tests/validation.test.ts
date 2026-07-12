import { describe, expect, it } from "vitest";

import {
  passwordsMatch,
  validatePasswordChangeInput,
  validatePasswordResetInput,
  validateRegistrationInput,
  validateTotpCode,
  validateVerificationToken,
} from "../lib/auth/validation";

describe("validation helpers", () => {
  it("validates registration input", () => {
    expect(
      validateRegistrationInput({
        email: "user@example.test",
        password: "Synthetic-Password-1",
        confirmPassword: "Synthetic-Password-1",
      }),
    ).toBeNull();
  });

  it("rejects mismatched registration passwords", () => {
    expect(
      validateRegistrationInput({
        email: "user@example.test",
        password: "Synthetic-Password-1",
        confirmPassword: "Different-Password-2",
      }),
    ).toContain("match");
  });

  it("validates token lengths", () => {
    expect(validateVerificationToken("a".repeat(43))).toBeNull();
    expect(validateVerificationToken("short")).not.toBeNull();
  });

  it("validates password reset input", () => {
    expect(
      validatePasswordResetInput({
        resetToken: "a".repeat(43),
        newPassword: "Synthetic-Password-2",
        confirmPassword: "Synthetic-Password-2",
      }),
    ).toBeNull();
  });

  it("validates password change input", () => {
    expect(
      validatePasswordChangeInput({
        currentPassword: "Synthetic-Password-1",
        newPassword: "Synthetic-Password-2",
        confirmPassword: "Synthetic-Password-2",
      }),
    ).toBeNull();
  });

  it("validates TOTP codes", () => {
    expect(validateTotpCode("123456")).toBeNull();
    expect(validateTotpCode("12")).not.toBeNull();
  });

  it("checks password confirmation", () => {
    expect(passwordsMatch("abc", "abc")).toBe(true);
    expect(passwordsMatch("abc", "def")).toBe(false);
  });
});
