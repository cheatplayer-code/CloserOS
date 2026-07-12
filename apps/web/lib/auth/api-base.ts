const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1"]);

const DEFAULT_LOCAL_API_BASE = "http://localhost:8000";

export class InvalidApiBaseUrlError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidApiBaseUrlError";
  }
}

function isLocalHostname(hostname: string): boolean {
  return LOCAL_HOSTNAMES.has(hostname.toLowerCase());
}

export function resolveApiBaseUrl(rawValue: string | undefined): string {
  const trimmed = rawValue?.trim() ?? "";
  const candidate = (
    trimmed.length > 0 ? trimmed : DEFAULT_LOCAL_API_BASE
  ).replace(/\/+$/, "");

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new InvalidApiBaseUrlError("API base URL is not valid.");
  }

  if (parsed.username || parsed.password) {
    throw new InvalidApiBaseUrlError(
      "API base URL must not include credentials.",
    );
  }

  if (parsed.search || parsed.hash) {
    throw new InvalidApiBaseUrlError(
      "API base URL must not include query or hash values.",
    );
  }

  if (!parsed.protocol.startsWith("http")) {
    throw new InvalidApiBaseUrlError("API base URL must use HTTP or HTTPS.");
  }

  if (isLocalHostname(parsed.hostname)) {
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new InvalidApiBaseUrlError(
        "Local API base URL must use HTTP or HTTPS.",
      );
    }
    return `${parsed.protocol}//${parsed.host}`;
  }

  if (parsed.protocol !== "https:") {
    throw new InvalidApiBaseUrlError("Non-local API base URLs must use HTTPS.");
  }

  return `https://${parsed.host}`;
}

export function getConfiguredApiBaseUrl(): string {
  return resolveApiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
}
