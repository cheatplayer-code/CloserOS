"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";

import { authApiClient } from "./api-client";
import {
  authReducer,
  initialAuthSnapshot,
  type AuthSnapshot,
} from "./auth-state";
import { GENERIC_LOGIN_FAILED } from "./messages";
import {
  clearPendingMfaState,
  readPendingMfaState,
  writePendingMfaState,
} from "./pending-mfa-storage";
import {
  toSessionMetadataFromLogin,
  toSessionMetadataFromSession,
} from "./session-format";
import type { ApiFailure, SessionMetadata } from "./types";

interface AuthContextValue extends AuthSnapshot {
  refreshSession: () => Promise<void>;
  signIn: (input: {
    email: string;
    password: string;
  }) => Promise<
    { ok: true; next: "app" | "mfa" } | { ok: false; failure: ApiFailure }
  >;
  completeMfa: (input: {
    code: string;
  }) => Promise<{ ok: true } | { ok: false; failure: ApiFailure }>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  clearAuthState: () => void;
  applyAuthenticatedSession: (session: SessionMetadata) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [snapshot, dispatch] = useReducer(
    authReducer,
    undefined,
    initialAuthSnapshot,
  );
  const initializedRef = useRef(false);

  const clearAuthState = useCallback(() => {
    clearPendingMfaState();
    dispatch({ type: "clear" });
  }, []);

  const applyAuthenticatedSession = useCallback((session: SessionMetadata) => {
    clearPendingMfaState();
    dispatch({ type: "set_authenticated", session });
  }, []);

  const refreshSession = useCallback(async () => {
    dispatch({ type: "set_loading" });

    const pending = readPendingMfaState();
    if (pending) {
      dispatch({ type: "set_pending_mfa", pendingMfa: pending });
      return;
    }

    const result = await authApiClient.getSession();
    if (result.ok) {
      applyAuthenticatedSession(toSessionMetadataFromSession(result.data));
      return;
    }

    if (result.kind === "authentication_failed") {
      clearAuthState();
      return;
    }

    dispatch({ type: "set_anonymous" });
  }, [applyAuthenticatedSession, clearAuthState]);

  useEffect(() => {
    if (initializedRef.current) {
      return;
    }

    initializedRef.current = true;
    void refreshSession();
  }, [refreshSession]);

  const signIn = useCallback(
    async (input: { email: string; password: string }) => {
      const result = await authApiClient.login(input);
      if (!result.ok) {
        if (result.kind === "authentication_failed") {
          return {
            ok: false as const,
            failure: {
              ok: false,
              kind: "authentication_failed",
              message: GENERIC_LOGIN_FAILED,
            } satisfies ApiFailure,
          };
        }
        return { ok: false as const, failure: result };
      }

      if (result.data.state === "mfa_required") {
        const pendingMfa = {
          csrfToken: result.data.csrf_token,
          expiresAt: result.data.expires_at,
        };
        writePendingMfaState(pendingMfa);
        dispatch({ type: "set_pending_mfa", pendingMfa });
        return { ok: true as const, next: "mfa" as const };
      }

      const session = toSessionMetadataFromLogin(result.data);
      if (!session) {
        return {
          ok: false as const,
          failure: {
            ok: false,
            kind: "service_unavailable",
            message: GENERIC_LOGIN_FAILED,
          } satisfies ApiFailure,
        };
      }

      applyAuthenticatedSession(session);
      return { ok: true as const, next: "app" as const };
    },
    [applyAuthenticatedSession],
  );

  const completeMfa = useCallback(
    async (input: { code: string }) => {
      const pending = readPendingMfaState();
      if (!pending) {
        return {
          ok: false as const,
          failure: {
            ok: false,
            kind: "authentication_failed",
            message: GENERIC_LOGIN_FAILED,
          } satisfies ApiFailure,
        };
      }

      const result = await authApiClient.completeMfa({
        method: "totp",
        response: { code: input.code },
        csrfToken: pending.csrfToken,
      });

      if (!result.ok) {
        return { ok: false as const, failure: result };
      }

      const session = toSessionMetadataFromLogin(result.data);
      if (!session) {
        return {
          ok: false as const,
          failure: {
            ok: false,
            kind: "service_unavailable",
            message: GENERIC_LOGIN_FAILED,
          } satisfies ApiFailure,
        };
      }

      applyAuthenticatedSession(session);
      return { ok: true as const };
    },
    [applyAuthenticatedSession],
  );

  const logout = useCallback(async () => {
    const csrfToken =
      snapshot.session?.csrfToken ?? readPendingMfaState()?.csrfToken;
    if (csrfToken) {
      await authApiClient.logout(csrfToken);
    }
    clearAuthState();
  }, [clearAuthState, snapshot.session?.csrfToken]);

  const logoutAll = useCallback(async () => {
    const csrfToken = snapshot.session?.csrfToken;
    if (csrfToken) {
      await authApiClient.logoutAll(csrfToken);
    }
    clearAuthState();
  }, [clearAuthState, snapshot.session?.csrfToken]);

  const value = useMemo<AuthContextValue>(
    () => ({
      ...snapshot,
      refreshSession,
      signIn,
      completeMfa,
      logout,
      logoutAll,
      clearAuthState,
      applyAuthenticatedSession,
    }),
    [
      snapshot,
      refreshSession,
      signIn,
      completeMfa,
      logout,
      logoutAll,
      clearAuthState,
      applyAuthenticatedSession,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }

  return context;
}
