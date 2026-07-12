"use client";

import type { ReactNode } from "react";

import { Alert } from "../auth/alert";
import { Button } from "../auth/button";
import { Spinner } from "../auth/spinner";
import { useTenant } from "../../lib/tenant/use-tenant";

interface TenantGateProps {
  children: ReactNode;
}

export function TenantGate({ children }: TenantGateProps) {
  const tenant = useTenant();

  if (tenant.phase === "idle" || tenant.phase === "loading") {
    return (
      <div className="center-state">
        <Spinner label="Loading workspace tenant" />
      </div>
    );
  }

  if (tenant.phase === "error" && tenant.failure) {
    return (
      <div className="center-state">
        <section
          className="workspace-panel"
          aria-labelledby="tenant-error-title"
        >
          <h1 id="tenant-error-title">Workspace unavailable</h1>
          <div aria-live="assertive">
            <Alert tone="error" message={tenant.failure.message} />
          </div>
          <Button type="button" onClick={() => void tenant.refreshTenants()}>
            Try again
          </Button>
        </section>
      </div>
    );
  }

  if (tenant.phase === "empty" || !tenant.tenantId) {
    return (
      <div className="center-state">
        <section
          className="workspace-panel"
          aria-labelledby="tenant-empty-title"
        >
          <h1 id="tenant-empty-title">No workspace tenant</h1>
          <p>
            Your account is signed in, but no active tenant workspace is
            available yet.
          </p>
          <Button type="button" onClick={() => void tenant.refreshTenants()}>
            Refresh tenants
          </Button>
        </section>
      </div>
    );
  }

  return children;
}
