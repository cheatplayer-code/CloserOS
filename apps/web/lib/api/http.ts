import { getConfiguredApiBaseUrl } from "../auth/api-base";
import { mapHttpStatusToFailure, mapNetworkError } from "../auth/errors";
import type { ApiResult } from "../auth/types";

export type { ApiResult } from "../auth/types";

const DEFAULT_TIMEOUT_MS = 15_000;

export interface HttpRequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
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

export async function apiRequest<T>(
  path: string,
  options: HttpRequestOptions = {},
): Promise<ApiResult<T>> {
  return executeRequest<T>(`${getConfiguredApiBaseUrl()}${path}`, options);
}

export async function apiRequestForTests<T>(
  baseUrl: string,
  path: string,
  options: HttpRequestOptions = {},
): Promise<ApiResult<T>> {
  return executeRequest<T>(`${baseUrl}${path}`, options);
}

async function executeRequest<T>(
  url: string,
  options: HttpRequestOptions,
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
    const response = await fetch(url, {
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
