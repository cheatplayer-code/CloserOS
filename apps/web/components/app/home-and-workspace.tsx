"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

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
      router.replace("/app/dashboard");
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
      <AppWorkspaceRedirect />
    </ProtectedRoute>
  );
}

function AppWorkspaceRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/app/dashboard");
  }, [router]);

  return (
    <div className="center-state">
      <section className="workspace-panel" aria-labelledby="app-redirect-title">
        <h1 id="app-redirect-title">Opening dashboard</h1>
        <p>
          Redirecting to your workspace dashboard. If nothing happens, open the{" "}
          <Link href="/app/dashboard">dashboard</Link> manually.
        </p>
        <Spinner label="Redirecting to dashboard" />
      </section>
    </div>
  );
}
