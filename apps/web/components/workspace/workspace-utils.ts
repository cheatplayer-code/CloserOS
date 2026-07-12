"use client";
/* eslint-disable react-hooks/set-state-in-effect -- deferred fetch lifecycle updates */

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../../lib/auth/auth-provider";
import type {
  ApiFailure,
  ApiResult,
  SessionMetadata,
} from "../../lib/auth/types";
import { useTenant } from "../../lib/tenant/use-tenant";

export function useWorkspaceSession(): SessionMetadata | null {
  const auth = useAuth();
  return auth.session;
}

export function useWorkspaceLogoutHandlers() {
  const auth = useAuth();

  const onLogout = useCallback(() => {
    void auth.logout().then(() => {
      window.location.assign("/auth/sign-in");
    });
  }, [auth]);

  const onLogoutAll = useCallback(() => {
    void auth.logoutAll().then(() => {
      window.location.assign("/auth/sign-in");
    });
  }, [auth]);

  return { onLogout, onLogoutAll };
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

export function defaultMetricWindow(): {
  window_start: string;
  window_end: string;
} {
  const windowEnd = new Date();
  const windowStart = new Date(windowEnd);
  windowStart.setDate(windowStart.getDate() - 7);

  return {
    window_start: windowStart.toISOString(),
    window_end: windowEnd.toISOString(),
  };
}

export function hasAnyRole(roles: string[], allowed: string[]): boolean {
  return allowed.some((role) => roles.includes(role));
}

export function useWorkspaceRoleDenied(allowed: string[]): boolean {
  const tenant = useTenant();
  if (!tenant.tenantId) {
    return false;
  }
  return !hasAnyRole(tenant.roles, allowed);
}

export function useWorkspaceResource<T>({
  enabled,
  deps,
  load,
}: {
  enabled: boolean;
  deps: readonly unknown[];
  load: () => Promise<ApiResult<T>>;
}): {
  loading: boolean;
  failure: ApiFailure | null;
  data: T | null;
  reload: () => void;
} {
  const [reloadToken, setReloadToken] = useState(0);
  const [loading, setLoading] = useState(enabled);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [data, setData] = useState<T | null>(null);

  const reload = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    const loadingTimer = globalThis.setTimeout(() => {
      if (!cancelled) {
        setLoading(true);
        setFailure(null);
      }
    }, 0);

    void load().then((result) => {
      if (cancelled) {
        return;
      }

      if (!result.ok) {
        setData(null);
        setFailure(result);
      } else {
        setData(result.data);
        setFailure(null);
      }
      setLoading(false);
    });

    return () => {
      cancelled = true;
      globalThis.clearTimeout(loadingTimer);
    };
  }, [enabled, load, reloadToken, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps

  return { loading, failure, data, reload };
}
