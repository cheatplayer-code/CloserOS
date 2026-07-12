import type { ApiFailure } from "../../lib/auth/types";

interface FormErrorSummaryProps {
  failure: ApiFailure | null;
  fieldError?: string | null;
  successMessage?: string | null;
}

export function FormErrorSummary({
  failure,
  fieldError,
  successMessage,
}: FormErrorSummaryProps) {
  if (successMessage) {
    return null;
  }

  const message = fieldError ?? failure?.message ?? null;
  if (!message) {
    return null;
  }

  return (
    <div
      className="form-summary"
      role="alert"
      aria-live="assertive"
      tabIndex={-1}
    >
      {message}
    </div>
  );
}

interface RateLimitNoticeProps {
  retryAfterSeconds?: number;
}

export function RateLimitNotice({ retryAfterSeconds }: RateLimitNoticeProps) {
  if (!retryAfterSeconds) {
    return null;
  }

  return (
    <p className="rate-limit" role="status" aria-live="polite">
      Retry available in about {retryAfterSeconds} seconds.
    </p>
  );
}
