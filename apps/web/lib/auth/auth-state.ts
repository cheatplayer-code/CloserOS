import type { AuthPhase, PendingMfaMetadata, SessionMetadata } from "./types";

export interface AuthSnapshot {
  phase: AuthPhase;
  session: SessionMetadata | null;
  pendingMfa: PendingMfaMetadata | null;
}

export type AuthAction =
  | { type: "set_loading" }
  | { type: "set_anonymous" }
  | { type: "set_pending_mfa"; pendingMfa: PendingMfaMetadata }
  | { type: "set_authenticated"; session: SessionMetadata }
  | { type: "clear" };

export function authReducer(
  state: AuthSnapshot,
  action: AuthAction,
): AuthSnapshot {
  switch (action.type) {
    case "set_loading":
      return { phase: "loading", session: null, pendingMfa: null };
    case "set_anonymous":
      return { phase: "anonymous", session: null, pendingMfa: null };
    case "set_pending_mfa":
      return {
        phase: "pending_mfa",
        session: null,
        pendingMfa: action.pendingMfa,
      };
    case "set_authenticated":
      return {
        phase: "authenticated",
        session: action.session,
        pendingMfa: null,
      };
    case "clear":
      return { phase: "anonymous", session: null, pendingMfa: null };
    default:
      return state;
  }
}

export function initialAuthSnapshot(): AuthSnapshot {
  return {
    phase: "loading",
    session: null,
    pendingMfa: null,
  };
}
