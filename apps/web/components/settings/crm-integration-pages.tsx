"use client";
/* eslint-disable react-hooks/set-state-in-effect -- settings pages reset fetch state when tenant context changes */

import type { CrmConnectionV1 } from "@closeros/contracts";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { crmApiClient } from "../../lib/api/crm-client";
import type { ApiFailure } from "../../lib/auth/types";
import { useTenant } from "../../lib/tenant/use-tenant";
import { AppShell } from "../app/app-shell";
import { ProtectedRoute } from "../app/protected-route";
import { TenantGate } from "../app/tenant-gate";
import { Alert } from "../auth/alert";
import { Button } from "../auth/button";
import { Spinner } from "../auth/spinner";
import {
  WorkspaceEmptyState,
  WorkspaceStatusBanner,
} from "../workspace/workspace-status";
import {
  formatTimestamp,
  hasAnyRole,
  useWorkspaceLogoutHandlers,
  useWorkspaceRoleDenied,
  useWorkspaceSession,
} from "../workspace/workspace-utils";

const CRM_READ_ROLES = ["owner", "sales_head", "compliance_admin"];
const CRM_WRITE_ROLES = ["owner", "compliance_admin"];

export function CrmIntegrationsPage() {
  return (
    <ProtectedRoute returnTo="/settings/integrations/crm">
      <TenantGate>
        <CrmIntegrationsContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function CrmIntegrationsContent() {
  const session = useWorkspaceSession();
  const tenant = useTenant();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const permissionDenied = useWorkspaceRoleDenied(CRM_READ_ROLES);
  const canWrite = hasAnyRole(tenant.roles, CRM_WRITE_ROLES);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [connections, setConnections] = useState<CrmConnectionV1[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFailure(null);
    void crmApiClient
      .listCrmConnections(tenant.tenantId)
      .then((result) => {
        if (cancelled) {
          return;
        }
        if (!result.ok) {
          setConnections([]);
          setFailure(result);
          return;
        }
        setConnections(result.data.connections);
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

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenant.tenantId || !session || !canWrite) {
      return;
    }
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setNotice(null);
    setFailure(null);
    const result = await crmApiClient.createCrmConnection(
      tenant.tenantId,
      {
        provider: "bitrix24",
        portal_domain: String(formData.get("portalDomain") ?? "") || null,
        client_id_ref: String(formData.get("clientIdRef") ?? "") || null,
        client_secret_ref:
          String(formData.get("clientSecretRef") ?? "") || null,
        access_token_ref: String(formData.get("accessTokenRef") ?? "") || null,
        refresh_token_ref:
          String(formData.get("refreshTokenRef") ?? "") || null,
      },
      session.csrfToken,
    );
    setBusy(false);
    if (!result.ok) {
      setFailure(result);
      return;
    }
    setConnections((current) => [result.data, ...current]);
    setNotice("Draft CRM connection created.");
    event.currentTarget.reset();
  }

  if (!session) {
    return null;
  }

  return (
    <AppShell
      session={session}
      onLogout={onLogout}
      onLogoutAll={onLogoutAll}
      busy={busy}
    >
      <section className="workspace-panel" aria-labelledby="crm-title">
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">
              <Link href="/settings/integrations">Integrations</Link>
            </p>
            <h1 id="crm-title">CRM integrations</h1>
          </div>
        </header>
        <p className="workspace-meta">
          Bitrix24 support is provisional. Documentation reviewed 2026-07-12;
          sandbox verification is not completed. Store reference keys only.
        </p>
        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />
        {notice ? <Alert tone="success" message={notice} /> : null}
        {loading && !permissionDenied ? (
          <Spinner label="Loading CRM connections" />
        ) : (
          <>
            {connections.length === 0 ? (
              <WorkspaceEmptyState
                title="No CRM connections"
                description="Create a draft Bitrix24 connection to start mapping CRM outcome fields."
              />
            ) : (
              <div className="workspace-table-wrap">
                <table className="workspace-table">
                  <caption className="visually-hidden">CRM connections</caption>
                  <thead>
                    <tr>
                      <th scope="col">Provider</th>
                      <th scope="col">Portal</th>
                      <th scope="col">Status</th>
                      <th scope="col">Last sync</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connections.map((connection) => (
                      <tr key={connection.id}>
                        <th scope="row">{connection.provider}</th>
                        <td>{connection.portal_domain ?? "not set"}</td>
                        <td>{connection.status}</td>
                        <td>
                          {connection.last_successful_sync_at
                            ? formatTimestamp(
                                connection.last_successful_sync_at,
                              )
                            : "never"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {canWrite ? (
              <section className="workspace-card" aria-labelledby="crm-create">
                <h2 id="crm-create">Create draft Bitrix24 connection</h2>
                <p className="workspace-meta">
                  Enter the portal host and environment reference names. Do not
                  paste OAuth tokens or client secrets.
                </p>
                <form
                  className="auth-form"
                  onSubmit={(event) => void handleCreate(event)}
                >
                  <label>
                    Portal domain
                    <input
                      name="portalDomain"
                      placeholder="example.bitrix24.kz"
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    Client ID reference
                    <input
                      name="clientIdRef"
                      placeholder="BITRIX24_CLIENT_ID"
                    />
                  </label>
                  <label>
                    Client secret reference
                    <input
                      name="clientSecretRef"
                      placeholder="BITRIX24_CLIENT_SECRET"
                    />
                  </label>
                  <label>
                    Access token reference
                    <input
                      name="accessTokenRef"
                      placeholder="BITRIX24_ACCESS_TOKEN"
                    />
                  </label>
                  <label>
                    Refresh token reference
                    <input
                      name="refreshTokenRef"
                      placeholder="BITRIX24_REFRESH_TOKEN"
                    />
                  </label>
                  <Button type="submit" disabled={busy}>
                    {busy ? "Creating..." : "Create draft"}
                  </Button>
                </form>
              </section>
            ) : null}
          </>
        )}
      </section>
    </AppShell>
  );
}
