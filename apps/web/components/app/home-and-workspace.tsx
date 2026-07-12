"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell, EmptyWorkspaceState } from "../app/app-shell";
import { ProtectedRoute } from "../app/protected-route";
import { Spinner } from "../auth/spinner";
import { useAuth } from "../../lib/auth/auth-provider";

export function HomeRedirectPage() {
  const router = useRouter();
  const auth = useAuth();

  useEffect(() => {
    if (auth.phase === "loading") {
      return;
    }

    if (auth.phase === "authenticated") {
      router.replace("/app");
      return;
    }

    if (auth.phase === "pending_mfa") {
      router.replace("/auth/mfa");
      return;
    }

    router.replace("/auth/sign-in");
  }, [auth.phase, router]);

  return (
    <div className="center-state">
      <Spinner label="Loading CloserOS" />
    </div>
  );
}

export function AppWorkspacePage() {
  return (
    <ProtectedRoute returnTo="/app">
      <AppWorkspaceContent />
    </ProtectedRoute>
  );
}

function AppWorkspaceContent() {
  const auth = useAuth();

  if (!auth.session) {
    return null;
  }

  return (
    <AppShell
      session={auth.session}
      onLogout={() => {
        void auth.logout().then(() => {
          window.location.assign("/auth/sign-in");
        });
      }}
      onLogoutAll={() => {
        void auth.logoutAll().then(() => {
          window.location.assign("/auth/sign-in");
        });
      }}
    >
      <EmptyWorkspaceState />
    </AppShell>
  );
}
