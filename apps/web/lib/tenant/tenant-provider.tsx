"use client";

import type { TenantSummaryV1 } from "@closeros/contracts";
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";

import { productApiClient } from "../api/product-client";
import { useAuth } from "../auth/auth-provider";
import type { ApiFailure } from "../auth/types";
import type { TenantContextValue, TenantPhase } from "./types";

const TENANT_PREFERENCE_KEY = "closeros:tenant-id-preference";
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface TenantState {
  phase: TenantPhase;
  tenants: TenantSummaryV1[];
  selectedTenantId: string | null;
  failure: ApiFailure | null;
}

type TenantAction =
  | { type: "reset" }
  | { type: "loading" }
  | { type: "ready"; tenants: TenantSummaryV1[]; selectedTenantId: string }
  | { type: "empty"; tenants: TenantSummaryV1[] }
  | { type: "error"; failure: ApiFailure }
  | { type: "select"; tenantId: string };

function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value);
}

function readTenantPreference(): string | null {
  if (typeof sessionStorage === "undefined") {
    return null;
  }

  const stored = sessionStorage.getItem(TENANT_PREFERENCE_KEY);
  if (!stored || !isUuid(stored)) {
    return null;
  }

  return stored;
}

function writeTenantPreference(tenantId: string): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }

  sessionStorage.setItem(TENANT_PREFERENCE_KEY, tenantId);
}

function clearTenantPreference(): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }

  sessionStorage.removeItem(TENANT_PREFERENCE_KEY);
}

function pickInitialTenant(tenants: TenantSummaryV1[]): string | null {
  if (tenants.length === 0) {
    return null;
  }

  const preference = readTenantPreference();
  if (preference) {
    const preferred = tenants.find((tenant) => tenant.id === preference);
    if (preferred && preferred.status === "active") {
      return preferred.id;
    }
  }

  const firstActive = tenants.find((tenant) => tenant.status === "active");
  if (firstActive) {
    return firstActive.id;
  }

  return tenants[0]?.id ?? null;
}

function tenantReducer(state: TenantState, action: TenantAction): TenantState {
  switch (action.type) {
    case "reset":
      return {
        phase: "idle",
        tenants: [],
        selectedTenantId: null,
        failure: null,
      };
    case "loading":
      return { ...state, phase: "loading", failure: null };
    case "ready":
      return {
        phase: "ready",
        tenants: action.tenants,
        selectedTenantId: action.selectedTenantId,
        failure: null,
      };
    case "empty":
      return {
        phase: "empty",
        tenants: action.tenants,
        selectedTenantId: null,
        failure: null,
      };
    case "error":
      return {
        ...state,
        phase: "error",
        failure: action.failure,
      };
    case "select":
      return {
        ...state,
        selectedTenantId: action.tenantId,
      };
    default:
      return state;
  }
}

export const TenantContext = createContext<TenantContextValue | null>(null);

export function TenantProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [state, dispatch] = useReducer(tenantReducer, {
    phase: "idle",
    tenants: [],
    selectedTenantId: null,
    failure: null,
  });
  const loadGenerationRef = useRef(0);

  const refreshTenants = useCallback(async () => {
    const generation = ++loadGenerationRef.current;
    dispatch({ type: "loading" });

    const result = await productApiClient.listTenants();
    if (generation !== loadGenerationRef.current) {
      return;
    }

    if (!result.ok) {
      dispatch({ type: "error", failure: result });
      return;
    }

    const selectedTenantId = pickInitialTenant(result.data);
    if (!selectedTenantId) {
      dispatch({ type: "empty", tenants: result.data });
      return;
    }

    writeTenantPreference(selectedTenantId);
    dispatch({
      type: "ready",
      tenants: result.data,
      selectedTenantId,
    });
  }, []);

  const selectTenant = useCallback(
    (tenantId: string) => {
      const tenant = state.tenants.find((item) => item.id === tenantId);
      if (!tenant) {
        return;
      }

      writeTenantPreference(tenantId);
      dispatch({ type: "select", tenantId });
    },
    [state.tenants],
  );

  useEffect(() => {
    if (auth.phase === "loading" || auth.phase === "pending_mfa") {
      return;
    }

    if (auth.phase !== "authenticated") {
      loadGenerationRef.current += 1;
      clearTenantPreference();
      dispatch({ type: "reset" });
      return;
    }

    void refreshTenants();
  }, [auth.phase, refreshTenants]);

  const selectedTenant = useMemo(
    () =>
      state.tenants.find((tenant) => tenant.id === state.selectedTenantId) ??
      null,
    [state.selectedTenantId, state.tenants],
  );

  const value = useMemo<TenantContextValue>(
    () => ({
      phase: state.phase,
      tenantId: state.selectedTenantId,
      tenantName: selectedTenant?.name ?? null,
      roles: selectedTenant?.roles ?? [],
      tenants: state.tenants,
      failure: state.failure,
      selectTenant,
      refreshTenants,
    }),
    [selectTenant, refreshTenants, selectedTenant, state],
  );

  return (
    <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
  );
}
