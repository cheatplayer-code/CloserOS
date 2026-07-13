"use client";
/* eslint-disable react-hooks/set-state-in-effect -- settings pages reset fetch state when tenant context changes */

import type { WhatsAppConnectionV1 } from "@closeros/contracts";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { whatsappApiClient } from "../../lib/api/whatsapp-client";
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

const WHATSAPP_READ_ROLES = ["owner", "sales_head", "compliance_admin"];
const WHATSAPP_WRITE_ROLES = ["owner", "compliance_admin"];

export function IntegrationsSettingsPage() {
  return (
    <ProtectedRoute returnTo="/settings/integrations">
      <TenantGate>
        <IntegrationsSettingsContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function IntegrationsSettingsContent() {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();

  if (!session) {
    return null;
  }

  return (
    <AppShell session={session} onLogout={onLogout} onLogoutAll={onLogoutAll}>
      <section className="workspace-panel" aria-labelledby="integrations-title">
        <header className="workspace-header">
          <h1 id="integrations-title">Integrations</h1>
        </header>
        <p className="workspace-meta">
          Connect official messaging providers. Secrets stay in your
          environment; only credential reference keys are stored.
        </p>
        <ul className="workspace-card-list">
          <li className="workspace-card">
            <h2>
              <Link href="/settings/integrations/whatsapp">WhatsApp Cloud</Link>
            </h2>
            <p>Meta WhatsApp Cloud API connections, webhooks, and templates.</p>
          </li>
          <li className="workspace-card">
            <h2>
              <Link href="/settings/integrations/crm">CRM</Link>
            </h2>
            <p>Provisional Bitrix24 CRM connections and outcome sync.</p>
          </li>
        </ul>
      </section>
    </AppShell>
  );
}

export function WhatsAppIntegrationsPage() {
  return (
    <ProtectedRoute returnTo="/settings/integrations/whatsapp">
      <TenantGate>
        <WhatsAppIntegrationsContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function WhatsAppIntegrationsContent() {
  const session = useWorkspaceSession();
  const tenant = useTenant();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const permissionDenied = useWorkspaceRoleDenied(WHATSAPP_READ_ROLES);
  const canWrite = hasAnyRole(tenant.roles, WHATSAPP_WRITE_ROLES);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [connections, setConnections] = useState<WhatsAppConnectionV1[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    void whatsappApiClient
      .listWhatsAppConnections(tenant.tenantId)
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

    const result = await whatsappApiClient.createWhatsAppConnection(
      tenant.tenantId,
      {
        app_id: String(formData.get("appId") ?? ""),
        waba_id: String(formData.get("wabaId") ?? ""),
        phone_number_id: String(formData.get("phoneNumberId") ?? ""),
        graph_api_version: String(formData.get("graphApiVersion") ?? "v21.0"),
        access_token_ref: String(formData.get("accessTokenRef") ?? "") || null,
        app_secret_ref: String(formData.get("appSecretRef") ?? "") || null,
        verify_token_ref: String(formData.get("verifyTokenRef") ?? "") || null,
      },
      session.csrfToken,
    );

    setBusy(false);
    if (!result.ok) {
      setFailure(result);
      return;
    }

    setConnections((current) => [result.data, ...current]);
    setNotice("Draft WhatsApp connection created.");
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
      <section
        className="workspace-panel"
        aria-labelledby="whatsapp-integrations-title"
      >
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">
              <Link href="/settings/integrations">Integrations</Link>
            </p>
            <h1 id="whatsapp-integrations-title">WhatsApp Cloud</h1>
          </div>
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />
        {notice ? <Alert tone="success" message={notice} /> : null}

        {loading && !permissionDenied ? (
          <Spinner label="Loading WhatsApp connections" />
        ) : (
          <>
            {connections.length === 0 ? (
              <WorkspaceEmptyState
                title="No WhatsApp connections"
                description="Create a draft connection to configure Meta WhatsApp Cloud."
              />
            ) : (
              <div className="workspace-table-wrap">
                <table className="workspace-table">
                  <caption className="visually-hidden">
                    WhatsApp connections
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Phone ID</th>
                      <th scope="col">Status</th>
                      <th scope="col">Webhook</th>
                      <th scope="col">Updated</th>
                      <th scope="col">Open</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connections.map((connection) => (
                      <tr key={connection.id}>
                        <th scope="row">{connection.phone_number_id}</th>
                        <td>{connection.status}</td>
                        <td>{connection.webhook_subscription_status}</td>
                        <td>{formatTimestamp(connection.updated_at)}</td>
                        <td>
                          <Link
                            href={`/settings/integrations/whatsapp/${connection.id}`}
                          >
                            Manage
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {canWrite ? (
              <section
                aria-labelledby="create-connection-title"
                className="workspace-card"
              >
                <h2 id="create-connection-title">Create draft connection</h2>
                <p className="workspace-meta">
                  Enter provider identifiers and environment reference keys
                  only. Never paste access tokens or secrets here.
                </p>
                <form
                  className="auth-form"
                  onSubmit={(event) => void handleCreate(event)}
                >
                  <label>
                    App ID
                    <input name="appId" required autoComplete="off" />
                  </label>
                  <label>
                    WABA ID
                    <input name="wabaId" required autoComplete="off" />
                  </label>
                  <label>
                    Phone number ID
                    <input name="phoneNumberId" required autoComplete="off" />
                  </label>
                  <label>
                    Graph API version
                    <input
                      name="graphApiVersion"
                      defaultValue="v21.0"
                      required
                    />
                  </label>
                  <label>
                    Access token reference
                    <input
                      name="accessTokenRef"
                      placeholder="ENV_VAR_NAME"
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    App secret reference
                    <input
                      name="appSecretRef"
                      placeholder="ENV_VAR_NAME"
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    Verify token reference
                    <input
                      name="verifyTokenRef"
                      placeholder="ENV_VAR_NAME"
                      autoComplete="off"
                    />
                  </label>
                  <Button type="submit" disabled={busy}>
                    {busy ? "Creating…" : "Create draft"}
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

interface WhatsAppConnectionDetailPageProps {
  connectionId: string;
}

export function WhatsAppConnectionDetailPage({
  connectionId,
}: WhatsAppConnectionDetailPageProps) {
  return (
    <ProtectedRoute
      returnTo={`/settings/integrations/whatsapp/${connectionId}`}
    >
      <TenantGate>
        <WhatsAppConnectionDetailContent connectionId={connectionId} />
      </TenantGate>
    </ProtectedRoute>
  );
}

function WhatsAppConnectionDetailContent({
  connectionId,
}: WhatsAppConnectionDetailPageProps) {
  const session = useWorkspaceSession();
  const tenant = useTenant();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const permissionDenied = useWorkspaceRoleDenied(WHATSAPP_READ_ROLES);
  const canWrite = hasAnyRole(tenant.roles, WHATSAPP_WRITE_ROLES);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [connection, setConnection] = useState<WhatsAppConnectionV1 | null>(
    null,
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const callbackUrl = useMemo(() => {
    if (!connection) {
      return null;
    }
    if (typeof window === "undefined") {
      return connection.webhook_callback_path;
    }
    return `${window.location.origin}${connection.webhook_callback_path}`;
  }, [connection]);

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    void whatsappApiClient
      .listWhatsAppConnections(tenant.tenantId)
      .then((result) => {
        if (cancelled) {
          return;
        }
        if (!result.ok) {
          setConnection(null);
          setFailure(result);
          return;
        }
        setConnection(
          result.data.connections.find((item) => item.id === connectionId) ??
            null,
        );
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [connectionId, permissionDenied, tenant.tenantId]);

  async function runAction(action: "verify" | "disable", version: number) {
    if (!tenant.tenantId || !session || !canWrite) {
      return;
    }

    setBusy(true);
    setNotice(null);
    setFailure(null);

    const request = { version };
    const result =
      action === "verify"
        ? await whatsappApiClient.verifyWhatsAppConnection(
            tenant.tenantId,
            connectionId,
            request,
            session.csrfToken,
          )
        : await whatsappApiClient.disableWhatsAppConnection(
            tenant.tenantId,
            connectionId,
            request,
            session.csrfToken,
          );

    setBusy(false);
    if (!result.ok) {
      setFailure(result);
      return;
    }

    setConnection(result.data);
    setNotice(
      action === "verify" ? "Verification completed." : "Connection disabled.",
    );
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
      <section
        className="workspace-panel"
        aria-labelledby="whatsapp-connection-title"
      >
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">
              <Link href="/settings/integrations/whatsapp">WhatsApp Cloud</Link>
            </p>
            <h1 id="whatsapp-connection-title">Connection detail</h1>
          </div>
          {canWrite && connection ? (
            <div className="app-header__actions">
              <Button
                type="button"
                onClick={() => void runAction("verify", connection.version)}
                disabled={busy}
              >
                Verify
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void runAction("disable", connection.version)}
                disabled={busy}
              >
                Disable
              </Button>
            </div>
          ) : null}
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />
        {notice ? <Alert tone="success" message={notice} /> : null}

        {loading && !permissionDenied ? (
          <Spinner label="Loading connection" />
        ) : connection ? (
          <>
            <dl className="workspace-meta-list">
              <div>
                <dt>Status</dt>
                <dd>{connection.status}</dd>
              </div>
              <div>
                <dt>Phone number ID</dt>
                <dd>{connection.phone_number_id}</dd>
              </div>
              <div>
                <dt>Graph API version</dt>
                <dd>{connection.graph_api_version}</dd>
              </div>
              <div>
                <dt>Webhook subscription</dt>
                <dd>{connection.webhook_subscription_status}</dd>
              </div>
              <div>
                <dt>Capabilities</dt>
                <dd>{connection.capabilities.join(", ")}</dd>
              </div>
              <div>
                <dt>Credential references</dt>
                <dd>
                  token={connection.access_token_ref ?? "—"}, secret=
                  {connection.app_secret_ref ?? "—"}, verify=
                  {connection.verify_token_ref ?? "—"}
                </dd>
              </div>
              <div>
                <dt>Last verified</dt>
                <dd>
                  {connection.last_verified_at
                    ? formatTimestamp(connection.last_verified_at)
                    : "never"}
                </dd>
              </div>
            </dl>

            <section
              aria-labelledby="webhook-setup-title"
              className="workspace-card"
            >
              <h2 id="webhook-setup-title">Webhook callback setup</h2>
              <p className="workspace-meta">
                Configure Meta with this callback URL and your verify token from
                the referenced environment variable. CloserOS never displays
                resolved secrets.
              </p>
              <p>
                <strong>Callback URL:</strong>{" "}
                {callbackUrl ?? connection.webhook_callback_path}
              </p>
              <p>
                <strong>Verify token:</strong> use the value behind{" "}
                {connection.verify_token_ref ?? "your verify token reference"}.
              </p>
            </section>

            <section
              aria-labelledby="templates-title"
              className="workspace-card"
            >
              <h2 id="templates-title">Approved templates</h2>
              <WorkspaceEmptyState
                title="Templates not loaded"
                description="Template catalog sync runs through the worker outbox. Trigger sync from operations tooling after verification."
              />
            </section>
          </>
        ) : !permissionDenied && !failure ? (
          <WorkspaceEmptyState
            title="Connection not found"
            description="This WhatsApp connection is unavailable or may have been removed."
          />
        ) : null}
      </section>
    </AppShell>
  );
}
