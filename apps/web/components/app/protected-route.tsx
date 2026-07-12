"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Spinner } from "../auth/spinner";
import { buildSignInHref } from "../../lib/auth/return-path";
import { useAuth } from "../../lib/auth/auth-provider";

interface ProtectedRouteProps {
  children: ReactNode;
  returnTo: string;
}

export function ProtectedRoute({ children, returnTo }: ProtectedRouteProps) {
  const router = useRouter();
  const auth = useAuth();

  useEffect(() => {
    if (auth.phase === "loading") {
      return;
    }

    if (auth.phase === "pending_mfa") {
      router.replace("/auth/mfa");
      return;
    }

    if (auth.phase === "anonymous") {
      router.replace(buildSignInHref(returnTo));
    }
  }, [auth.phase, returnTo, router]);

  if (auth.phase === "loading") {
    return (
      <div className="center-state">
        <Spinner label="Checking your session" />
      </div>
    );
  }

  if (auth.phase !== "authenticated" || !auth.session) {
    return (
      <div className="center-state">
        <Spinner label="Redirecting to sign in" />
      </div>
    );
  }

  return children;
}
