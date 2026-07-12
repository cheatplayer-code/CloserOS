"use client";
/* eslint-disable react-hooks/set-state-in-effect -- workspace pages reset fetch state when tenant context changes */

import type { ManagerScorecardV1 } from "@closeros/contracts";
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
  defaultMetricWindow,
  formatTimestamp,
  useWorkspaceLogoutHandlers,
  useWorkspaceRoleDenied,
  useWorkspaceSession,
} from "./workspace-utils";

const MANAGER_ROLES = ["owner", "sales_head", "compliance_admin", "manager"];

interface ManagerScorecardPageProps {
  membershipId: string;
}

export function ManagerScorecardPage({
  membershipId,
}: ManagerScorecardPageProps) {
  return (
    <ProtectedRoute returnTo={`/app/managers/${membershipId}`}>
      <TenantGate>
        <ManagerScorecardContent membershipId={membershipId} />
      </TenantGate>
    </ProtectedRoute>
  );
}

function ManagerScorecardContent({ membershipId }: ManagerScorecardPageProps) {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(MANAGER_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;
  const [scorecard, setScorecard] = useState<ManagerScorecardV1 | null>(null);

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    const window = defaultMetricWindow();
    void productApiClient
      .getScorecard(tenant.tenantId, membershipId, window)
      .then((result) => {
        if (cancelled) {
          return;
        }

        if (!result.ok) {
          setScorecard(null);
          setFailure(result);
          return;
        }

        setScorecard(result.data);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [membershipId, permissionDenied, tenant.tenantId]);

  if (!session) {
    return null;
  }

  return (
    <AppShell session={session} onLogout={onLogout} onLogoutAll={onLogoutAll}>
      <section
        className="workspace-panel"
        aria-labelledby="manager-scorecard-title"
      >
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">
              <Link href="/app/managers">Managers</Link>
            </p>
            <h1 id="manager-scorecard-title">Manager scorecard</h1>
          </div>
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />

        {showLoading ? (
          <Spinner label="Loading scorecard" />
        ) : scorecard ? (
          <>
            <p className="workspace-meta">
              Window {formatTimestamp(scorecard.window_start)} to{" "}
              {formatTimestamp(scorecard.window_end)} · Formula{" "}
              {scorecard.formula_version}
            </p>

            <div className="workspace-cards">
              <article className="workspace-card">
                <h2>Composite score</h2>
                <p className="workspace-card__value">
                  {scorecard.composite_basis_points} bp
                </p>
                <p className="workspace-meta">
                  Delta {scorecard.composite_delta_basis_points} bp
                </p>
              </article>
              <article className="workspace-card">
                <h2>Response rate</h2>
                <p className="workspace-card__value">
                  {scorecard.components.response_rate_basis_points} bp
                </p>
              </article>
              <article className="workspace-card">
                <h2>Task completion</h2>
                <p className="workspace-card__value">
                  {scorecard.components.task_completion_basis_points} bp
                </p>
              </article>
            </div>

            {scorecard.finding_counts.length > 0 ? (
              <div className="workspace-table-wrap">
                <table className="workspace-table">
                  <caption className="visually-hidden">
                    Manager finding counts
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Finding code</th>
                      <th scope="col">Severity</th>
                      <th scope="col">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scorecard.finding_counts.map((item) => (
                      <tr key={`${item.finding_code}-${item.severity}`}>
                        <th scope="row">{item.finding_code}</th>
                        <td>{item.severity}</td>
                        <td>{item.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <WorkspaceEmptyState
                title="No finding counts"
                description="Finding discipline metrics will appear after analysis runs complete."
              />
            )}
          </>
        ) : !permissionDenied && !failure ? (
          <WorkspaceEmptyState
            title="Scorecard unavailable"
            description="This manager scorecard could not be loaded for the selected window."
          />
        ) : null}
      </section>
    </AppShell>
  );
}
