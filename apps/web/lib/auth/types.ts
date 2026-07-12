export type AuthenticationState = "authenticated" | "mfa_required";

export type AssuranceLevel = "single_factor" | "multi_factor";

export type AuthPhase =
  "loading" | "anonymous" | "pending_mfa" | "authenticated";

export interface AcceptedResponse {
  message: string;
}

export interface LoginResponse {
  state: AuthenticationState;
  csrf_token: string;
  expires_at: string;
  user_id?: string;
  session_id?: string;
  assurance_level?: AssuranceLevel;
}

export interface SessionResponse {
  user_id: string;
  session_id: string;
  assurance_level: AssuranceLevel;
  expires_at: string;
  csrf_token: string;
}

export interface SanitizedValidationError {
  location: string;
  message: string;
  type: string;
}

export interface ValidationErrorBody {
  message: string;
  errors: SanitizedValidationError[];
}

export interface GenericErrorBody {
  detail?: string;
  message?: string;
}

export interface SessionMetadata {
  userId: string;
  sessionId: string;
  assuranceLevel: AssuranceLevel;
  expiresAt: string;
  csrfToken: string;
}

export interface PendingMfaMetadata {
  csrfToken: string;
  expiresAt: string;
}

export type ApiSuccess<T> = {
  ok: true;
  data: T;
};

export type ApiFailureKind =
  | "request_unavailable"
  | "authentication_failed"
  | "security_failed"
  | "validation_failed"
  | "rate_limited"
  | "service_unavailable";

export type ApiFailure = {
  ok: false;
  kind: ApiFailureKind;
  message: string;
  validationErrors?: SanitizedValidationError[];
  retryAfterSeconds?: number;
};

export type ApiResult<T> = ApiSuccess<T> | ApiFailure;
