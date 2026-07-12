"use client";

import { FormEvent, useState } from "react";

import { AppShell } from "../app/app-shell";
import { ProtectedRoute } from "../app/protected-route";
import { Alert } from "../auth/alert";
import { Button } from "../auth/button";
import { PasswordField } from "../auth/fields";
import { FormErrorSummary, RateLimitNotice } from "../auth/form-feedback";
import { authApiClient } from "../../lib/auth/api-client";
import { useAuth } from "../../lib/auth/auth-provider";
import {
  GENERIC_PASSWORD_CHANGED,
  GENERIC_SERVICE_UNAVAILABLE,
} from "../../lib/auth/messages";
import { toSessionMetadataFromLogin } from "../../lib/auth/session-format";
import { validatePasswordChangeInput } from "../../lib/auth/validation";
import { useFormAction } from "../../lib/auth/use-form-action";

export function SecuritySettingsPage() {
  return (
    <ProtectedRoute returnTo="/settings/security">
      <SecuritySettingsContent />
    </ProtectedRoute>
  );
}

function SecuritySettingsContent() {
  const auth = useAuth();
  const form = useFormAction();
  const [notice, setNotice] = useState<string | null>(null);

  if (!auth.session) {
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    const formData = new FormData(event.currentTarget);
    const currentPassword = String(formData.get("currentPassword") ?? "");
    const newPassword = String(formData.get("newPassword") ?? "");
    const confirmPassword = String(formData.get("confirmPassword") ?? "");

    const validationError = validatePasswordChangeInput({
      currentPassword,
      newPassword,
      confirmPassword,
    });
    if (validationError) {
      form.setFieldError(validationError);
      return;
    }

    event.currentTarget.reset();

    const result = await form.run(async () => {
      const response = await authApiClient.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        csrfToken: auth.session?.csrfToken ?? "",
      });

      if (!response.ok) {
        return { ok: false as const, failure: response };
      }

      const session = toSessionMetadataFromLogin(response.data);
      if (!session) {
        return {
          ok: false as const,
          failure: {
            ok: false,
            kind: "service_unavailable" as const,
            message: GENERIC_SERVICE_UNAVAILABLE,
          },
        };
      }

      auth.applyAuthenticatedSession(session);
      return { ok: true as const, message: GENERIC_PASSWORD_CHANGED };
    });

    if (result.ok && "message" in result && result.message) {
      setNotice(result.message);
    }
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
      busy={form.isSubmitting}
    >
      <section
        className="settings-panel"
        aria-labelledby="security-settings-title"
      >
        <h1 id="security-settings-title">Security settings</h1>
        <p>
          Update your password while keeping the current authenticated session
          active.
        </p>
        {notice ? <Alert tone="success" message={notice} /> : null}
        <form className="stack" onSubmit={handleSubmit} noValidate>
          <FormErrorSummary failure={form.error} fieldError={form.fieldError} />
          <RateLimitNotice retryAfterSeconds={form.error?.retryAfterSeconds} />
          <PasswordField
            name="currentPassword"
            label="Current password"
            autoComplete="current-password"
            required
          />
          <PasswordField
            name="newPassword"
            label="New password"
            autoComplete="new-password"
            required
          />
          <PasswordField
            name="confirmPassword"
            label="Confirm new password"
            autoComplete="new-password"
            required
          />
          <Button type="submit" disabled={form.isSubmitting}>
            {form.isSubmitting ? "Updating…" : "Change password"}
          </Button>
        </form>
      </section>
    </AppShell>
  );
}
