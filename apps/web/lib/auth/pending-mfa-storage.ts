import type { PendingMfaMetadata } from "./types";

const STORAGE_KEY = "closeros_pending_mfa";

function isPendingMfaMetadata(value: unknown): value is PendingMfaMetadata {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as PendingMfaMetadata;
  return (
    typeof candidate.csrfToken === "string" &&
    candidate.csrfToken.length > 0 &&
    typeof candidate.expiresAt === "string" &&
    candidate.expiresAt.length > 0
  );
}

function isExpired(expiresAt: string, now: Date): boolean {
  const expiry = Date.parse(expiresAt);
  return Number.isNaN(expiry) || expiry <= now.getTime();
}

export function readPendingMfaState(
  now: Date = new Date(),
): PendingMfaMetadata | null {
  if (typeof sessionStorage === "undefined") {
    return null;
  }

  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isPendingMfaMetadata(parsed) || isExpired(parsed.expiresAt, now)) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }

    return parsed;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function writePendingMfaState(state: PendingMfaMetadata): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }

  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function clearPendingMfaState(): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }

  sessionStorage.removeItem(STORAGE_KEY);
}

export function pendingMfaStorageKeyForTests(): string {
  return STORAGE_KEY;
}
