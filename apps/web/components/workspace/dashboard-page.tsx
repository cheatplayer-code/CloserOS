"use client";
/* eslint-disable react-hooks/set-state-in-effect -- workspace pages reset fetch state when tenant context changes */

import type { DashboardResponseV1 } from "@closeros/contracts";
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
  defaultMetricWindow,
  formatTimestamp,
  useWorkspaceRoleDenied,
  useWorkspaceLogoutHandlers,
  useWorkspaceSession,
} from "./workspace-utils";

const DASHBOARD_ROLES = ["owner", "sales_head", "compliance_admin"];

export function DashboardPage() {
  return (
    <ProtectedRoute returnTo="/app/dashboard">
      <TenantGate>
        <DashboardContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function DashboardContent() {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponseV1 | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(DASHBOARD_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    const window = defaultMetricWindow();
    void productApiClient
      .getDashboard(tenant.tenantId, window)
      .then((result) => {
        if (cancelled) {
          return;
        }

        if (!result.ok) {
          setDashboard(null);
          setFailure(result);
          return;
        }

        setDashboard(result.data);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [tenant.tenantId, tenant.roles, permissionDenied]);

  if (!session) {
    return null;
  }

  return (
    <AppShell session={session} onLogout={onLogout} onLogoutAll={onLogoutAll}>
      <section className="workspace-panel" aria-labelledby="dashboard-title">
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">Tenant workspace</p>
            <h1 id="dashboard-title">Dashboard</h1>
            {tenant.tenantName ? (
              <p className="workspace-subtitle">{tenant.tenantName}</p>
            ) : null}
          </div>
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />

        {showLoading ? (
          <Spinner label="Loading dashboard metrics" />
        ) : dashboard ? (
          <>
            <div className="workspace-cards">
              <article className="workspace-card">
                <h2>Total conversations</h2>
                <p className="workspace-card__value">
                  {dashboard.total_conversations}
                </p>
              </article>
              <article className="workspace-card">
                <h2>High severity findings</h2>
                <p className="workspace-card__value">
                  {dashboard.open_high_severity_findings}
                </p>
              </article>
              <article className="workspace-card">
                <h2>Overdue tasks</h2>
                <p className="workspace-card__value">
                  {dashboard.overdue_follow_up_tasks}
                </p>
              </article>
            </div>

            <p className="workspace-meta">
              Window {formatTimestamp(dashboard.window_start)} to{" "}
              {formatTimestamp(dashboard.window_end)} · Formula{" "}
              {dashboard.formula_version}
            </p>

            {dashboard.metrics.length === 0 ? (
              <WorkspaceEmptyState
                title="No metrics yet"
                description="Dashboard metrics will appear once conversations are ingested for this tenant."
              />
            ) : (
              <div className="workspace-table-wrap">
                <table className="workspace-table">
                  <caption className="visually-hidden">
                    Dashboard metric deltas
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Metric</th>
                      <th scope="col">Current</th>
                      <th scope="col">Previous</th>
                      <th scope="col">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.metrics.map((metric) => (
                      <tr key={metric.key}>
                        <th scope="row">{metric.key}</th>
                        <td>{metric.current_value}</td>
                        <td>{metric.previous_value}</td>
                        <td>{metric.delta}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {dashboard.manager_summaries.length > 0 ? (
              <section aria-labelledby="manager-summaries-title">
                <h2 id="manager-summaries-title">Manager summaries</h2>
                <div className="workspace-table-wrap">
                  <table className="workspace-table">
                    <caption className="visually-hidden">
                      Manager performance summaries
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Manager</th>
                        <th scope="col">Response rate (bp)</th>
                        <th scope="col">Conversion rate (bp)</th>
                        <th scope="col">Active threads</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.manager_summaries.map((summary) => (
                        <tr key={summary.manager_user_id}>
                          <th scope="row">{summary.manager_user_id}</th>
                          <td>{summary.response_rate_basis_points}</td>
                          <td>{summary.conversion_rate_basis_points}</td>
                          <td>{summary.active_thread_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}
          </>
        ) : !permissionDenied && !failure ? (
          <WorkspaceEmptyState
            title="Dashboard unavailable"
            description="No dashboard data is available for the selected window."
          />
        ) : null}
      </section>
    </AppShell>
  );
}
