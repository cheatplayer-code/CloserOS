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
import { Spinner } from "../auth/spinner";
import { WorkspaceEmptyState, WorkspaceStatusBanner } from "./workspace-status";
import {
  formatTimestamp,
  useWorkspaceLogoutHandlers,
  useWorkspaceRoleDenied,
  useWorkspaceSession,
} from "./workspace-utils";

const TASK_READ_ROLES = ["owner", "sales_head", "compliance_admin", "manager"];

export function TasksPage() {
  return (
    <ProtectedRoute returnTo="/app/tasks">
      <TenantGate>
        <TasksContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function TasksContent() {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(TASK_READ_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;
  const [statusFilter, setStatusFilter] = useState("");
  const [tasks, setTasks] = useState<FollowUpTaskV1[]>([]);

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFailure(null);

    void productApiClient
      .listTasks(tenant.tenantId, {
        limit: 50,
        status: statusFilter || undefined,
      })
      .then((result) => {
        if (cancelled) {
          return;
        }

        if (!result.ok) {
          setTasks([]);
          setFailure(result);
          return;
        }

        setTasks(result.data.tasks);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [permissionDenied, statusFilter, tenant.tenantId]);

  if (!session) {
    return null;
  }

  return (
    <AppShell session={session} onLogout={onLogout} onLogoutAll={onLogoutAll}>
      <section className="workspace-panel" aria-labelledby="tasks-title">
        <header className="workspace-header">
          <div>
            <p className="workspace-eyebrow">Operations</p>
            <h1 id="tasks-title">Follow-up tasks</h1>
          </div>
        </header>

        <WorkspaceStatusBanner
          failure={failure}
          permissionDenied={
            permissionDenied || failure?.kind === "security_failed"
          }
        />

        <form
          className="workspace-filters"
          onSubmit={(event) => event.preventDefault()}
        >
          <label htmlFor="task-status-filter">Status</label>
          <select
            id="task-status-filter"
            className="workspace-filter__input"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </form>

        {showLoading ? (
          <Spinner label="Loading tasks" />
        ) : tasks.length === 0 ? (
          <WorkspaceEmptyState
            title="No tasks"
            description="Follow-up tasks created from findings will appear here."
          />
        ) : (
          <div className="workspace-table-wrap">
            <table className="workspace-table">
              <caption className="visually-hidden">
                Tenant follow-up tasks
              </caption>
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Status</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Due</th>
                  <th scope="col">Open</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <th scope="row">{task.title}</th>
                    <td>{task.status}</td>
                    <td>{task.priority}</td>
                    <td>{task.due_at ? formatTimestamp(task.due_at) : "—"}</td>
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
    </AppShell>
  );
}
