"use client";
/* eslint-disable react-hooks/set-state-in-effect -- workspace pages reset fetch state when tenant context changes */

import type { ConversationDetailResponseV1 } from "@closeros/contracts";
import Link from "next/link";
import { useEffect, useState } from "react";

import { productApiClient } from "../../lib/api/product-client";
import type { ApiFailure } from "../../lib/auth/types";
import { useTenant } from "../../lib/tenant/use-tenant";
import { AppShell } from "../app/app-shell";
import { ProtectedRoute } from "../app/protected-route";
import { TenantGate } from "../app/tenant-gate";
import { Alert } from "../auth/alert";
import { Button } from "../auth/button";
import { Spinner } from "../auth/spinner";
import { WorkspaceEmptyState, WorkspaceStatusBanner } from "./workspace-status";
import {
  formatTimestamp,
  hasAnyRole,
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
const ANALYSIS_ROLES = ["owner", "sales_head", "compliance_admin"];

interface ConversationDetailPageProps {
  conversationId: string;
}

export function ConversationDetailPage({
  conversationId,
}: ConversationDetailPageProps) {
  return (
    <ProtectedRoute returnTo={`/app/conversations/${conversationId}`}>
      <TenantGate>
        <ConversationDetailContent conversationId={conversationId} />
      </TenantGate>
    </ProtectedRoute>
  );
}

function ConversationDetailContent({
  conversationId,
}: ConversationDetailPageProps) {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(CONVERSATION_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;
  const [analysisNotice, setAnalysisNotice] = useState<string | null>(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [detail, setDetail] = useState<ConversationDetailResponseV1 | null>(
    null,
  );

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    void productApiClient
      .getConversation(tenant.tenantId, conversationId)
      .then((result) => {
        if (cancelled) {
          return;
        }

        if (!result.ok) {
          setDetail(null);
          setFailure(result);
          return;
        }

        setDetail(result.data);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId, permissionDenied, tenant.tenantId]);

  async function handleEnqueueAnalysis() {
    if (!tenant.tenantId || !session) {
      return;
    }

    setAnalysisBusy(true);
    setAnalysisNotice(null);
    setFailure(null);

    const result = await productApiClient.enqueueAnalysis(
      tenant.tenantId,
      conversationId,
      session.csrfToken,
    );

    setAnalysisBusy(false);

    if (!result.ok) {
      setFailure(result);
      return;
    }

    setAnalysisNotice("Analysis request accepted.");
  }

  if (!session) {
    return null;
  }

  const canRequestAnalysis = hasAnyRole(tenant.roles, ANALYSIS_ROLES);

  return (
    <AppShell
      session={session}
      onLogout={onLogout}
      onLogoutAll={onLogoutAll}
      busy={analysisBusy}
    >
      <section
        className="workspace-panel"
        aria-labelledby="conversation-detail-title"
      >
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">
              <Link href="/app/conversations">Conversations</Link>
            </p>
            <h1 id="conversation-detail-title">Conversation detail</h1>
          </div>
          {canRequestAnalysis ? (
            <Button
              type="button"
              onClick={() => void handleEnqueueAnalysis()}
              disabled={analysisBusy}
            >
              {analysisBusy ? "Requesting…" : "Request analysis"}
            </Button>
          ) : null}
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />

        {analysisNotice ? (
          <Alert tone="success" message={analysisNotice} />
        ) : null}

        {showLoading ? (
          <Spinner label="Loading conversation" />
        ) : detail ? (
          <>
            <dl className="workspace-meta-list">
              <div>
                <dt>External ID</dt>
                <dd>{detail.external_conversation_id}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{detail.lifecycle_status ?? "unknown"}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatTimestamp(detail.updated_at)}</dd>
              </div>
            </dl>

            <section aria-labelledby="timeline-title">
              <h2 id="timeline-title">Message timeline</h2>
              {detail.messages.length === 0 ? (
                <WorkspaceEmptyState
                  title="No messages"
                  description="Messages will appear here after channel ingestion."
                />
              ) : (
                <ol className="workspace-timeline">
                  {detail.messages.map((message) => (
                    <li key={message.message_id} className="workspace-card">
                      <p className="workspace-meta">
                        {message.direction} · {message.sender_type} ·{" "}
                        {formatTimestamp(message.sent_at)}
                      </p>
                      <p>
                        {message.is_deleted
                          ? "[deleted]"
                          : (message.sanitized_text ?? "[content unavailable]")}
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </section>

            <section aria-labelledby="analysis-title">
              <h2 id="analysis-title">AI analysis runs</h2>
              {detail.analyses.length === 0 ? (
                <WorkspaceEmptyState
                  title="No analysis runs"
                  description="Request an analysis to generate evidence-backed findings."
                />
              ) : (
                <div className="workspace-table-wrap">
                  <table className="workspace-table">
                    <caption className="visually-hidden">
                      Conversation analysis runs
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Status</th>
                        <th scope="col">Model</th>
                        <th scope="col">Findings</th>
                        <th scope="col">Requested</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.analyses.map((run) => (
                        <tr key={run.id}>
                          <td>{run.status}</td>
                          <td>
                            {run.model_provider} · {run.prompt_version}
                          </td>
                          <td>{run.findings.length}</td>
                          <td>{formatTimestamp(run.requested_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section aria-labelledby="conversation-tasks-title">
              <h2 id="conversation-tasks-title">Follow-up tasks</h2>
              {detail.tasks.length === 0 ? (
                <WorkspaceEmptyState
                  title="No tasks"
                  description="Follow-up tasks linked to this conversation will appear here."
                />
              ) : (
                <div className="workspace-table-wrap">
                  <table className="workspace-table">
                    <caption className="visually-hidden">
                      Conversation follow-up tasks
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Title</th>
                        <th scope="col">Status</th>
                        <th scope="col">Priority</th>
                        <th scope="col">Open</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.tasks.map((task) => (
                        <tr key={task.id}>
                          <th scope="row">{task.title}</th>
                          <td>{task.status}</td>
                          <td>{task.priority}</td>
                          <td>
                            <Link href={`/app/tasks/${task.id}`}>View</Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        ) : !permissionDenied && !failure ? (
          <WorkspaceEmptyState
            title="Conversation not found"
            description="This conversation is unavailable or may have been removed."
          />
        ) : null}
      </section>
    </AppShell>
  );
}
