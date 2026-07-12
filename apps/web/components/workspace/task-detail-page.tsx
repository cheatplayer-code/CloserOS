"use client";
/* eslint-disable react-hooks/set-state-in-effect -- workspace pages reset fetch state when tenant context changes */

import type { FollowUpTaskV1 } from "@closeros/contracts";
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

const TASK_READ_ROLES = ["owner", "sales_head", "compliance_admin", "manager"];
const TASK_WRITE_ROLES = ["owner", "sales_head"];

interface TaskDetailPageProps {
  taskId: string;
}

export function TaskDetailPage({ taskId }: TaskDetailPageProps) {
  return (
    <ProtectedRoute returnTo={`/app/tasks/${taskId}`}>
      <TenantGate>
        <TaskDetailContent taskId={taskId} />
      </TenantGate>
    </ProtectedRoute>
  );
}

function TaskDetailContent({ taskId }: TaskDetailPageProps) {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(TASK_READ_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateNotice, setUpdateNotice] = useState<string | null>(null);
  const [task, setTask] = useState<FollowUpTaskV1 | null>(null);

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    void productApiClient
      .getTask(tenant.tenantId, taskId)
      .then((result) => {
        if (cancelled) {
          return;
        }

        if (!result.ok) {
          setTask(null);
          setFailure(result);
          return;
        }

        setTask(result.data);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [permissionDenied, taskId, tenant.tenantId]);

  async function handleCompleteTask() {
    if (!tenant.tenantId || !session || !task) {
      return;
    }

    setUpdateBusy(true);
    setUpdateNotice(null);
    setFailure(null);

    const result = await productApiClient.updateTask(
      tenant.tenantId,
      task.id,
      {
        version: task.version,
        action: "complete",
      },
      session.csrfToken,
    );

    setUpdateBusy(false);

    if (!result.ok) {
      setFailure(result);
      return;
    }

    setTask(result.data);
    setUpdateNotice("Task marked as completed.");
  }

  if (!session) {
    return null;
  }

  const canUpdateTask = hasAnyRole(tenant.roles, TASK_WRITE_ROLES);

  return (
    <AppShell
      session={session}
      onLogout={onLogout}
      onLogoutAll={onLogoutAll}
      busy={updateBusy}
    >
      <section className="workspace-panel" aria-labelledby="task-detail-title">
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">
              <Link href="/app/tasks">Tasks</Link>
            </p>
            <h1 id="task-detail-title">Task detail</h1>
          </div>
          {canUpdateTask && task && task.status !== "completed" ? (
            <Button
              type="button"
              onClick={() => void handleCompleteTask()}
              disabled={updateBusy}
            >
              {updateBusy ? "Updating…" : "Mark completed"}
            </Button>
          ) : null}
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />

        {updateNotice ? <Alert tone="success" message={updateNotice} /> : null}

        {showLoading ? (
          <Spinner label="Loading task" />
        ) : task ? (
          <dl className="workspace-meta-list">
            <div>
              <dt>Title</dt>
              <dd>{task.title}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{task.status}</dd>
            </div>
            <div>
              <dt>Priority</dt>
              <dd>{task.priority}</dd>
            </div>
            <div>
              <dt>Conversation</dt>
              <dd>
                <Link
                  href={`/app/conversations/${task.conversation_thread_id}`}
                >
                  {task.conversation_thread_id}
                </Link>
              </dd>
            </div>
            <div>
              <dt>Due</dt>
              <dd>{task.due_at ? formatTimestamp(task.due_at) : "—"}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{formatTimestamp(task.updated_at)}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{task.version}</dd>
            </div>
          </dl>
        ) : !permissionDenied && !failure ? (
          <WorkspaceEmptyState
            title="Task not found"
            description="This follow-up task is unavailable or may have been removed."
          />
        ) : null}
      </section>
    </AppShell>
  );
}
