"use client";
/* eslint-disable react-hooks/set-state-in-effect -- workspace pages reset fetch state when tenant context changes */

import type { ManagerListItemV1 } from "@closeros/contracts";
import Link from "next/link";
import { useEffect, useState } from "react";

import { productApiClient } from "../../lib/api/product-client";
import type { ApiFailure } from "../../lib/auth/types";
import { useTenant } from "../../lib/tenant/use-tenant";
import { AppShell } from "../app/app-shell";
import { ProtectedRoute } from "../app/protected-route";
import { TenantGate } from "../app/tenant-gate";
import { Spinner } from "../auth/spinner";
import { WorkspaceEmptyState, WorkspaceStatusBanner } from "./workspace-status";
import {
  useWorkspaceLogoutHandlers,
  useWorkspaceRoleDenied,
  useWorkspaceSession,
} from "./workspace-utils";

const MANAGER_ROLES = ["owner", "sales_head", "compliance_admin", "manager"];

export function ManagersPage() {
  return (
    <ProtectedRoute returnTo="/app/managers">
      <TenantGate>
        <ManagersContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function ManagersContent() {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(MANAGER_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;
  const [managers, setManagers] = useState<ManagerListItemV1[]>([]);

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    void productApiClient
      .listManagers(tenant.tenantId)
      .then((result) => {
        if (cancelled) {
          return;
        }

        if (!result.ok) {
          setManagers([]);
          setFailure(result);
          return;
        }

        setManagers(result.data.managers);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [permissionDenied, tenant.tenantId]);

  if (!session) {
    return null;
  }

  return (
    <AppShell session={session} onLogout={onLogout} onLogoutAll={onLogoutAll}>
      <section className="workspace-panel" aria-labelledby="managers-title">
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">Coaching</p>
            <h1 id="managers-title">Managers</h1>
          </div>
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />

        {showLoading ? (
          <Spinner label="Loading managers" />
        ) : managers.length === 0 ? (
          <WorkspaceEmptyState
            title="No managers"
            description="Manager memberships will appear here once the tenant team is configured."
          />
        ) : (
          <div className="workspace-table-wrap">
            <table className="workspace-table">
              <caption className="visually-hidden">Tenant manager list</caption>
              <thead>
                <tr>
                  <th scope="col">Membership</th>
                  <th scope="col">User</th>
                  <th scope="col">Roles</th>
                  <th scope="col">Scorecard</th>
                </tr>
              </thead>
              <tbody>
                {managers.map((manager) => (
                  <tr key={manager.membership_id}>
                    <td>{manager.membership_id}</td>
                    <td>{manager.manager_user_id}</td>
                    <td>{manager.roles.join(", ")}</td>
                    <td>
                      <Link href={`/app/managers/${manager.membership_id}`}>
                        View scorecard
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppShell>
  );
}
