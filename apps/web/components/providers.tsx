"use client";

import type { ReactNode } from "react";

import { AuthProvider } from "../lib/auth/auth-provider";
import { TenantProvider } from "../lib/tenant/tenant-provider";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <TenantProvider>{children}</TenantProvider>
    </AuthProvider>
  );
}
