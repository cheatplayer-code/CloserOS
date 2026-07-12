import type { TenantSummaryV1 } from "@closeros/contracts";

import type { ApiFailure } from "../auth/types";

export type TenantPhase = "idle" | "loading" | "ready" | "empty" | "error";

export interface TenantContextValue {
  phase: TenantPhase;
  tenantId: string | null;
  tenantName: string | null;
  roles: string[];
  tenants: TenantSummaryV1[];
  failure: ApiFailure | null;
  selectTenant: (tenantId: string) => void;
  refreshTenants: () => Promise<void>;
}
