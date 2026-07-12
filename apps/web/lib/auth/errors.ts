import {
  GENERIC_AUTH_UNAVAILABLE,
  GENERIC_RATE_LIMITED,
  GENERIC_REQUEST_UNAVAILABLE,
  GENERIC_SECURITY_FAILED,
  GENERIC_SERVICE_UNAVAILABLE,
  GENERIC_VALIDATION_FAILED,
} from "./messages";
import type {
  ApiFailure,
  ApiFailureKind,
  GenericErrorBody,
  ValidationErrorBody,
} from "./types";

function parseRetryAfter(headerValue: string | null): number | undefined {
  if (!headerValue) {
    return undefined;
  }

  const seconds = Number.parseInt(headerValue, 10);
  if (Number.isFinite(seconds) && seconds > 0) {
    return seconds;
  }

  return undefined;
}

function isValidationErrorBody(value: unknown): value is ValidationErrorBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as ValidationErrorBody;
  return (
    typeof candidate.message === "string" &&
    Array.isArray(candidate.errors) &&
    candidate.errors.every(
      (error) =>
        typeof error.location === "string" &&
        typeof error.message === "string" &&
        typeof error.type === "string",
    )
  );
}

function isGenericErrorBody(value: unknown): value is GenericErrorBody {
  return typeof value === "object" && value !== null;
}

export function mapHttpStatusToFailure(
  status: number,
  body: unknown,
  retryAfterHeader: string | null,
): ApiFailure {
  const retryAfterSeconds = parseRetryAfter(retryAfterHeader);

  if (status === 400) {
    return failure("request_unavailable", GENERIC_REQUEST_UNAVAILABLE);
  }

  if (status === 401) {
    return failure("authentication_failed", GENERIC_AUTH_UNAVAILABLE);
  }

  if (status === 403) {
    return failure("security_failed", GENERIC_SECURITY_FAILED);
  }

  if (status === 422 && isValidationErrorBody(body)) {
    return {
      ok: false,
      kind: "validation_failed",
      message: GENERIC_VALIDATION_FAILED,
      validationErrors: body.errors,
    };
  }

  if (status === 429) {
    const seconds = retryAfterSeconds ?? 60;
    return {
      ok: false,
      kind: "rate_limited",
      message: GENERIC_RATE_LIMITED(seconds),
      retryAfterSeconds: seconds,
    };
  }

  if (status >= 500) {
    return failure("service_unavailable", GENERIC_SERVICE_UNAVAILABLE);
  }

  if (isGenericErrorBody(body) && typeof body.detail === "string") {
    return failure("service_unavailable", GENERIC_SERVICE_UNAVAILABLE);
  }

  return failure("service_unavailable", GENERIC_SERVICE_UNAVAILABLE);
}

export function mapNetworkError(): ApiFailure {
  return failure("service_unavailable", GENERIC_SERVICE_UNAVAILABLE);
}

function failure(kind: ApiFailureKind, message: string): ApiFailure {
  return { ok: false, kind, message };
}
