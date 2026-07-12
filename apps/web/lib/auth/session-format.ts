import type {
  AssuranceLevel,
  LoginResponse,
  SessionMetadata,
  SessionResponse,
} from "./types";

export function toSessionMetadataFromLogin(
  response: LoginResponse,
): SessionMetadata | null {
  if (
    response.state !== "authenticated" ||
    !response.user_id ||
    !response.session_id ||
    !response.assurance_level
  ) {
    return null;
  }

  return {
    userId: response.user_id,
    sessionId: response.session_id,
    assuranceLevel: response.assurance_level,
    expiresAt: response.expires_at,
    csrfToken: response.csrf_token,
  };
}

export function toSessionMetadataFromSession(
  response: SessionResponse,
): SessionMetadata {
  return {
    userId: response.user_id,
    sessionId: response.session_id,
    assuranceLevel: response.assurance_level,
    expiresAt: response.expires_at,
    csrfToken: response.csrf_token,
  };
}

export function formatAssuranceLevel(level: AssuranceLevel): string {
  return level === "multi_factor" ? "Multi-factor" : "Single-factor";
}

export function formatExpiryLabel(
  expiresAt: string,
  now: Date = new Date(),
): string {
  const expiry = Date.parse(expiresAt);
  if (Number.isNaN(expiry)) {
    return "Unknown";
  }

  const diffMs = expiry - now.getTime();
  if (diffMs <= 0) {
    return "Expired";
  }

  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) {
    return `${minutes} min remaining`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (remainingMinutes === 0) {
    return `${hours} hr remaining`;
  }

  return `${hours} hr ${remainingMinutes} min remaining`;
}

export function formatTimestamp(value: string): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return "Unknown";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(parsed));
}
