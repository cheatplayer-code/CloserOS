import Link from "next/link";
import type { ReactNode } from "react";

import {
  formatAssuranceLevel,
  formatExpiryLabel,
} from "../../lib/auth/session-format";
import type { SessionMetadata } from "../../lib/auth/types";
import { Button } from "../auth/button";

interface AppHeaderProps {
  session: SessionMetadata;
  onLogout: () => void;
  onLogoutAll: () => void;
  busy?: boolean;
}

export function AppHeader({
  session,
  onLogout,
  onLogoutAll,
  busy = false,
}: AppHeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header__brand">
        <Link href="/app" className="app-header__logo">
          CloserOS AI
        </Link>
        <span className="session-badge">
          {formatAssuranceLevel(session.assuranceLevel)}
        </span>
      </div>
      <nav className="app-header__nav" aria-label="Primary">
        <Link href="/app">Workspace</Link>
        <Link href="/settings/security">Security</Link>
      </nav>
      <div className="app-header__session">
        <p className="app-header__meta">
          Session {formatExpiryLabel(session.expiresAt)}
        </p>
        <div className="app-header__actions">
          <Button
            type="button"
            variant="ghost"
            onClick={onLogout}
            disabled={busy}
          >
            Sign out
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={onLogoutAll}
            disabled={busy}
          >
            Sign out everywhere
          </Button>
        </div>
      </div>
    </header>
  );
}

interface AppShellProps {
  session: SessionMetadata;
  onLogout: () => void;
  onLogoutAll: () => void;
  busy?: boolean;
  children: ReactNode;
}

export function AppShell({
  session,
  onLogout,
  onLogoutAll,
  busy,
  children,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <AppHeader
        session={session}
        onLogout={onLogout}
        onLogoutAll={onLogoutAll}
        busy={busy}
      />
      <main className="app-shell__main">{children}</main>
    </div>
  );
}

export function EmptyWorkspaceState() {
  return (
    <section className="empty-state" aria-labelledby="workspace-empty-title">
      <p className="empty-state__eyebrow">Workspace</p>
      <h1 id="workspace-empty-title">Product modules are being implemented</h1>
      <p>
        Your authenticated session is active. Messaging, CRM, and coaching
        surfaces will appear here as later blocks land.
      </p>
    </section>
  );
}
