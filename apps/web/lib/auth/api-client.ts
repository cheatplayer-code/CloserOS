import { getConfiguredApiBaseUrl } from "./api-base";
import { mapHttpStatusToFailure, mapNetworkError } from "./errors";
import type {
  AcceptedResponse,
  ApiResult,
  LoginResponse,
  SessionResponse,
} from "./types";

const AUTH_PREFIX = "/api/v1/auth";
const DEFAULT_TIMEOUT_MS = 15_000;

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  csrfToken?: string;
  timeoutMs?: number;
}

async function parseJsonBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => {
    controller.abort();
  }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  const headers = new Headers({
    Accept: "application/json",
  });

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  if (options.csrfToken) {
    headers.set("X-CSRF-Token", options.csrfToken);
  }

  try {
    const response = await fetch(`${getConfiguredApiBaseUrl()}${path}`, {
      method: options.method ?? "GET",
      credentials: "include",
      cache: "no-store",
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });

    if (response.status === 204) {
      return { ok: true, data: undefined as T };
    }

    const body = await parseJsonBody(response);
    if (!response.ok) {
      return mapHttpStatusToFailure(
        response.status,
        body,
        response.headers.get("Retry-After"),
      );
    }

    return { ok: true, data: body as T };
  } catch {
    return mapNetworkError();
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function createAuthApiClient() {
  return {
    register(input: { email: string; password: string }) {
      return request<AcceptedResponse>(`${AUTH_PREFIX}/register`, {
        method: "POST",
        body: input,
      });
    },

    requestEmailVerification(input: { email: string }) {
      return request<AcceptedResponse>(
        `${AUTH_PREFIX}/email-verification/request`,
        {
          method: "POST",
          body: input,
        },
      );
    },

    confirmEmailVerification(input: { verification_token: string }) {
      return request<void>(`${AUTH_PREFIX}/email-verification/confirm`, {
        method: "POST",
        body: input,
      });
    },

    login(input: { email: string; password: string }) {
      return request<LoginResponse>(`${AUTH_PREFIX}/login`, {
        method: "POST",
        body: input,
      });
    },

    completeMfa(input: {
      method: "totp" | "webauthn";
      response: Record<string, string>;
      csrfToken: string;
    }) {
      return request<LoginResponse>(`${AUTH_PREFIX}/mfa/complete`, {
        method: "POST",
        body: {
          method: input.method,
          response: input.response,
        },
        csrfToken: input.csrfToken,
      });
    },

    getSession() {
      return request<SessionResponse>(`${AUTH_PREFIX}/session`, {
        method: "GET",
      });
    },

    logout(csrfToken: string) {
      return request<void>(`${AUTH_PREFIX}/logout`, {
        method: "POST",
        csrfToken,
      });
    },

    logoutAll(csrfToken: string) {
      return request<void>(`${AUTH_PREFIX}/logout-all`, {
        method: "POST",
        csrfToken,
      });
    },

    requestPasswordReset(input: { email: string }) {
      return request<AcceptedResponse>(
        `${AUTH_PREFIX}/password-reset/request`,
        {
          method: "POST",
          body: input,
        },
      );
    },

    confirmPasswordReset(input: { reset_token: string; new_password: string }) {
      return request<void>(`${AUTH_PREFIX}/password-reset/confirm`, {
        method: "POST",
        body: input,
      });
    },

    changePassword(input: {
      current_password: string;
      new_password: string;
      csrfToken: string;
    }) {
      return request<LoginResponse>(`${AUTH_PREFIX}/password/change`, {
        method: "POST",
        body: {
          current_password: input.current_password,
          new_password: input.new_password,
        },
        csrfToken: input.csrfToken,
      });
    },
  };
}

export type AuthApiClient = ReturnType<typeof createAuthApiClient>;

export const authApiClient = createAuthApiClient();

export async function requestForTests<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeout = setTimeout(() => {
    controller.abort();
  }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  const headers = new Headers({
    Accept: "application/json",
  });

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  if (options.csrfToken) {
    headers.set("X-CSRF-Token", options.csrfToken);
  }

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method: options.method ?? "GET",
      credentials: "include",
      cache: "no-store",
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });

    if (response.status === 204) {
      return { ok: true, data: undefined as T };
    }

    const body = await parseJsonBody(response);
    if (!response.ok) {
      return mapHttpStatusToFailure(
        response.status,
        body,
        response.headers.get("Retry-After"),
      );
    }

    return { ok: true, data: body as T };
  } catch {
    return mapNetworkError();
  } finally {
    clearTimeout(timeout);
  }
}
