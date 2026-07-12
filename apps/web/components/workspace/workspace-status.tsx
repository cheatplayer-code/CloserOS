"use client";

import type { ApiFailure } from "../../lib/auth/types";
import { Alert } from "../auth/alert";

interface WorkspaceStatusProps {
  failure?: ApiFailure | null;
  permissionDenied?: boolean;
}

export function WorkspaceStatusBanner({
  failure,
  permissionDenied = false,
}: WorkspaceStatusProps) {
  if (permissionDenied) {
    return (
      <div aria-live="assertive">
        <Alert
          tone="error"
          title="Access denied"
          message="You do not have permission to view this workspace data."
        />
      </div>
    );
  }

  if (!failure) {
    return null;
  }

  return (
    <div aria-live="assertive">
      <Alert tone="error" message={failure.message} />
    </div>
  );
}

export function WorkspaceEmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section
      className="workspace-empty"
      aria-labelledby="workspace-empty-title"
    >
      <h2 id="workspace-empty-title">{title}</h2>
      <p>{description}</p>
    </section>
  );
}
