"use client";
/* eslint-disable react-hooks/set-state-in-effect -- workspace pages reset fetch state when tenant context changes */

import type { ConversationListItemV1 } from "@closeros/contracts";
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
  formatTimestamp,
  useWorkspaceLogoutHandlers,
  useWorkspaceRoleDenied,
  useWorkspaceSession,
} from "./workspace-utils";

const CONVERSATION_ROLES = [
  "owner",
  "sales_head",
  "compliance_admin",
  "manager",
];

export function ConversationsPage() {
  return (
    <ProtectedRoute returnTo="/app/conversations">
      <TenantGate>
        <ConversationsContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function ConversationsContent() {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(CONVERSATION_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;
  const [conversations, setConversations] = useState<ConversationListItemV1[]>(
    [],
  );

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    void productApiClient
      .listConversations(tenant.tenantId, { limit: 50 })
      .then((result) => {
        if (cancelled) {
          return;
        }

        if (!result.ok) {
          setConversations([]);
          setFailure(result);
          return;
        }

        setConversations(result.data.conversations);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [tenant.tenantId, permissionDenied]);

  if (!session) {
    return null;
  }

  return (
    <AppShell session={session} onLogout={onLogout} onLogoutAll={onLogoutAll}>
      <section
        className="workspace-panel"
        aria-labelledby="conversations-title"
      >
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">Review</p>
            <h1 id="conversations-title">Conversations</h1>
          </div>
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />

        {showLoading ? (
          <Spinner label="Loading conversations" />
        ) : conversations.length === 0 ? (
          <WorkspaceEmptyState
            title="No conversations"
            description="Connected channel conversations will appear here once ingestion starts."
          />
        ) : (
          <div className="workspace-table-wrap">
            <table className="workspace-table">
              <caption className="visually-hidden">
                Tenant conversation list
              </caption>
              <thead>
                <tr>
                  <th scope="col">Provider</th>
                  <th scope="col">External ID</th>
                  <th scope="col">Status</th>
                  <th scope="col">Findings</th>
                  <th scope="col">Updated</th>
                  <th scope="col">Open</th>
                </tr>
              </thead>
              <tbody>
                {conversations.map((conversation) => (
                  <tr key={conversation.id}>
                    <td>{conversation.provider}</td>
                    <td>{conversation.external_conversation_id}</td>
                    <td>{conversation.lifecycle_status ?? "unknown"}</td>
                    <td>
                      {conversation.open_finding_count} open /{" "}
                      {conversation.high_severity_finding_count} high
                    </td>
                    <td>{formatTimestamp(conversation.updated_at)}</td>
                    <td>
                      <Link href={`/app/conversations/${conversation.id}`}>
                        View
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
