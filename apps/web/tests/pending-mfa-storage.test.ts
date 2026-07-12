import { beforeEach, describe, expect, it } from "vitest";

import {
  clearPendingMfaState,
  pendingMfaStorageKeyForTests,
  readPendingMfaState,
  writePendingMfaState,
} from "../lib/auth/pending-mfa-storage";

class MemoryStorage {
  private readonly store = new Map<string, string>();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }
}

describe("pending MFA storage", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "sessionStorage", {
      configurable: true,
      value: new MemoryStorage(),
    });
    clearPendingMfaState();
  });

  it("stores only CSRF metadata", () => {
    writePendingMfaState({
      csrfToken: "csrf-token-value",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });

    const raw = sessionStorage.getItem(pendingMfaStorageKeyForTests());
    expect(raw).toContain("csrf-token-value");
    expect(raw).not.toContain("password");
    expect(raw).not.toContain("closeros_dev_session");
  });

  it("restores pending MFA state before expiry", () => {
    writePendingMfaState({
      csrfToken: "csrf-token-value",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });

    expect(readPendingMfaState()?.csrfToken).toBe("csrf-token-value");
  });

  it("clears expired pending MFA state", () => {
    writePendingMfaState({
      csrfToken: "csrf-token-value",
      expiresAt: new Date(Date.now() - 1_000).toISOString(),
    });

    expect(readPendingMfaState()).toBeNull();
  });
});
