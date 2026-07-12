const DEFAULT_AUTHENTICATED_PATH = "/app";

export function sanitizeReturnPath(
  value: string | null | undefined,
): string | null {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) {
    return null;
  }

  if (trimmed.includes("://")) {
    return null;
  }

  if (trimmed.includes("\\")) {
    return null;
  }

  if (trimmed.startsWith("/auth/")) {
    return null;
  }

  return trimmed;
}

export function buildSignInHref(returnPath: string | null): string {
  const safePath = sanitizeReturnPath(returnPath);
  if (!safePath) {
    return "/auth/sign-in";
  }

  const encoded = encodeURIComponent(safePath);
  return `/auth/sign-in?returnTo=${encoded}`;
}

export function resolvePostAuthPath(
  returnPath: string | null | undefined,
): string {
  return sanitizeReturnPath(returnPath) ?? DEFAULT_AUTHENTICATED_PATH;
}
