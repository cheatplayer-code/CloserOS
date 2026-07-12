"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useRef } from "react";

import { Alert } from "../../components/auth/alert";
import { Button } from "../../components/auth/button";
import { AuthShell } from "../../components/auth/auth-shell";
import { PasswordField, TextField } from "../../components/auth/fields";
import {
  FormErrorSummary,
  RateLimitNotice,
} from "../../components/auth/form-feedback";
import { Spinner } from "../../components/auth/spinner";
import { authApiClient } from "../../lib/auth/api-client";
import { useAuth } from "../../lib/auth/auth-provider";
import {
  GENERIC_EMAIL_VERIFIED,
  GENERIC_REGISTRATION,
  GENERIC_REQUEST_ACCEPTED,
} from "../../lib/auth/messages";
import { resolvePostAuthPath } from "../../lib/auth/return-path";
import {
  normalizeEmail,
  validatePasswordResetInput,
  validateRegistrationInput,
  validateTotpCode,
  validateVerificationToken,
} from "../../lib/auth/validation";
import { useFormAction } from "../../lib/auth/use-form-action";

export function SignInPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const form = useFormAction();
  const errorRef = useRef<HTMLDivElement | null>(null);
  const returnTo = searchParams.get("returnTo");

  useEffect(() => {
    if (auth.phase === "authenticated") {
      router.replace(resolvePostAuthPath(returnTo));
    }
    if (auth.phase === "pending_mfa") {
      router.replace("/auth/mfa");
    }
  }, [auth.phase, returnTo, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const email = normalizeEmail(String(formData.get("email") ?? ""));
    const password = String(formData.get("password") ?? "");
    event.currentTarget.reset();

    const result = await form.run(async () => {
      const signInResult = await auth.signIn({ email, password });
      if (!signInResult.ok) {
        return { ok: false as const, failure: signInResult.failure };
      }

      router.replace(
        signInResult.next === "mfa"
          ? "/auth/mfa"
          : resolvePostAuthPath(returnTo),
      );
      return { ok: true as const };
    });

    if (!result.ok && !result.stale) {
      errorRef.current?.focus();
    }
  }

  return (
    <AuthShell
      title="Sign in"
      subtitle="Access your CloserOS workspace with verified credentials."
    >
      <form className="stack" onSubmit={handleSubmit} noValidate>
        <FormErrorSummary failure={form.error} />
        <RateLimitNotice retryAfterSeconds={form.error?.retryAfterSeconds} />
        <div ref={errorRef} tabIndex={-1} className="visually-hidden" />
        <TextField
          name="email"
          label="Email"
          type="email"
          autoComplete="username"
          inputMode="email"
          required
        />
        <PasswordField
          name="password"
          label="Password"
          autoComplete="current-password"
          required
        />
        <Button type="submit" disabled={form.isSubmitting}>
          {form.isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <div className="auth-links">
        <Link href="/auth/forgot-password">Forgot password</Link>
        <Link href="/auth/register">Create account</Link>
        <Link href="/auth/verify-email">Verify email</Link>
      </div>
    </AuthShell>
  );
}

export function RegisterPage() {
  const router = useRouter();
  const form = useFormAction();
  const errorRef = useRef<HTMLDivElement | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const email = normalizeEmail(String(formData.get("email") ?? ""));
    const password = String(formData.get("password") ?? "");
    const confirmPassword = String(formData.get("confirmPassword") ?? "");

    const validationError = validateRegistrationInput({
      email,
      password,
      confirmPassword,
    });
    if (validationError) {
      form.setFieldError(validationError);
      errorRef.current?.focus();
      return;
    }

    event.currentTarget.reset();

    const result = await form.run(async () => {
      const response = await authApiClient.register({ email, password });
      if (!response.ok) {
        return { ok: false as const, failure: response };
      }
      return { ok: true as const, message: GENERIC_REGISTRATION };
    });

    if (result.ok && result.message) {
      router.push("/auth/verify-email");
    } else if (!result.ok && !result.stale) {
      errorRef.current?.focus();
    }
  }

  return (
    <AuthShell
      title="Create account"
      subtitle="Register with your work email to begin verification."
    >
      <form className="stack" onSubmit={handleSubmit} noValidate>
        <FormErrorSummary
          failure={form.error}
          fieldError={form.fieldError}
          successMessage={form.successMessage}
        />
        <RateLimitNotice retryAfterSeconds={form.error?.retryAfterSeconds} />
        {form.successMessage ? (
          <Alert tone="success" message={form.successMessage} />
        ) : null}
        <TextField
          name="email"
          label="Email"
          type="email"
          autoComplete="email"
          required
        />
        <PasswordField
          name="password"
          label="Password"
          autoComplete="new-password"
          required
        />
        <PasswordField
          name="confirmPassword"
          label="Confirm password"
          autoComplete="new-password"
          required
        />
        <Button type="submit" disabled={form.isSubmitting}>
          {form.isSubmitting ? "Submitting…" : "Create account"}
        </Button>
      </form>
      <div className="auth-links">
        <Link href="/auth/sign-in">Already have an account?</Link>
      </div>
    </AuthShell>
  );
}

export function VerifyEmailPage() {
  const router = useRouter();
  const requestForm = useFormAction();
  const confirmForm = useFormAction();

  async function handleRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const email = normalizeEmail(String(formData.get("email") ?? ""));
    event.currentTarget.reset();

    await requestForm.run(async () => {
      const response = await authApiClient.requestEmailVerification({ email });
      if (!response.ok) {
        return { ok: false as const, failure: response };
      }
      return { ok: true as const, message: GENERIC_REQUEST_ACCEPTED };
    });
  }

  async function handleConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const verificationToken = String(
      formData.get("verificationToken") ?? "",
    ).trim();
    const validationError = validateVerificationToken(verificationToken);
    if (validationError) {
      confirmForm.setFieldError(validationError);
      return;
    }

    event.currentTarget.reset();

    const result = await confirmForm.run(async () => {
      const response = await authApiClient.confirmEmailVerification({
        verification_token: verificationToken,
      });
      if (!response.ok) {
        return { ok: false as const, failure: response };
      }
      return { ok: true as const, message: GENERIC_EMAIL_VERIFIED };
    });

    if (result.ok) {
      router.push("/auth/sign-in");
    }
  }

  return (
    <AuthShell
      title="Verify email"
      subtitle="Request a verification message or confirm with a token pasted from email."
    >
      <div className="stack stack--sectioned">
        <section aria-labelledby="verify-request-title" className="stack">
          <h3 id="verify-request-title">Request verification</h3>
          <form className="stack" onSubmit={handleRequest} noValidate>
            <FormErrorSummary
              failure={requestForm.error}
              successMessage={requestForm.successMessage}
            />
            {requestForm.successMessage ? (
              <Alert tone="success" message={requestForm.successMessage} />
            ) : null}
            <TextField
              name="email"
              label="Email"
              type="email"
              autoComplete="email"
              required
            />
            <Button type="submit" disabled={requestForm.isSubmitting}>
              {requestForm.isSubmitting
                ? "Submitting…"
                : "Send verification request"}
            </Button>
          </form>
        </section>
        <section aria-labelledby="verify-confirm-title" className="stack">
          <h3 id="verify-confirm-title">Confirm verification token</h3>
          <form className="stack" onSubmit={handleConfirm} noValidate>
            <FormErrorSummary
              failure={confirmForm.error}
              fieldError={confirmForm.fieldError}
              successMessage={confirmForm.successMessage}
            />
            <TextField
              name="verificationToken"
              label="Verification token"
              autoComplete="off"
              spellCheck={false}
              minLength={43}
              maxLength={43}
              required
            />
            <Button type="submit" disabled={confirmForm.isSubmitting}>
              {confirmForm.isSubmitting ? "Confirming…" : "Confirm email"}
            </Button>
          </form>
        </section>
      </div>
      <div className="auth-links">
        <Link href="/auth/sign-in">Back to sign in</Link>
      </div>
    </AuthShell>
  );
}

export function ForgotPasswordPage() {
  const form = useFormAction();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const email = normalizeEmail(String(formData.get("email") ?? ""));
    event.currentTarget.reset();

    await form.run(async () => {
      const response = await authApiClient.requestPasswordReset({ email });
      if (!response.ok) {
        return { ok: false as const, failure: response };
      }
      return { ok: true as const, message: GENERIC_REQUEST_ACCEPTED };
    });
  }

  return (
    <AuthShell
      title="Forgot password"
      subtitle="Request a password reset without revealing account status."
    >
      <form className="stack" onSubmit={handleSubmit} noValidate>
        <FormErrorSummary
          failure={form.error}
          successMessage={form.successMessage}
        />
        {form.successMessage ? (
          <Alert tone="success" message={form.successMessage} />
        ) : null}
        <TextField
          name="email"
          label="Email"
          type="email"
          autoComplete="email"
          required
        />
        <Button type="submit" disabled={form.isSubmitting}>
          {form.isSubmitting ? "Submitting…" : "Send reset request"}
        </Button>
      </form>
      <div className="auth-links">
        <Link href="/auth/reset-password">Have a reset token?</Link>
        <Link href="/auth/sign-in">Back to sign in</Link>
      </div>
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  const router = useRouter();
  const auth = useAuth();
  const form = useFormAction();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const resetToken = String(formData.get("resetToken") ?? "").trim();
    const newPassword = String(formData.get("newPassword") ?? "");
    const confirmPassword = String(formData.get("confirmPassword") ?? "");

    const validationError = validatePasswordResetInput({
      resetToken,
      newPassword,
      confirmPassword,
    });
    if (validationError) {
      form.setFieldError(validationError);
      return;
    }

    event.currentTarget.reset();

    const result = await form.run(async () => {
      const response = await authApiClient.confirmPasswordReset({
        reset_token: resetToken,
        new_password: newPassword,
      });
      if (!response.ok) {
        return { ok: false as const, failure: response };
      }
      auth.clearAuthState();
      return { ok: true as const, message: GENERIC_REQUEST_ACCEPTED };
    });

    if (result.ok) {
      router.push("/auth/sign-in");
    }
  }

  return (
    <AuthShell
      title="Reset password"
      subtitle="Paste the reset token from your email and choose a new password."
    >
      <form className="stack" onSubmit={handleSubmit} noValidate>
        <FormErrorSummary failure={form.error} fieldError={form.fieldError} />
        <TextField
          name="resetToken"
          label="Reset token"
          autoComplete="off"
          spellCheck={false}
          minLength={43}
          maxLength={43}
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
          {form.isSubmitting ? "Resetting…" : "Reset password"}
        </Button>
      </form>
    </AuthShell>
  );
}

export function MfaPage() {
  const router = useRouter();
  const auth = useAuth();
  const form = useFormAction();

  useEffect(() => {
    if (auth.phase === "anonymous") {
      router.replace("/auth/sign-in");
    }
    if (auth.phase === "authenticated") {
      router.replace("/app");
    }
  }, [auth.phase, router]);

  if (auth.phase === "loading") {
    return (
      <div className="center-state">
        <Spinner label="Loading multi-factor sign in" />
      </div>
    );
  }

  if (auth.phase !== "pending_mfa") {
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const code = String(formData.get("code") ?? "");
    const validationError = validateTotpCode(code);
    if (validationError) {
      form.setFieldError(validationError);
      return;
    }

    event.currentTarget.reset();

    const result = await form.run(async () => {
      const response = await auth.completeMfa({ code });
      if (!response.ok) {
        return { ok: false as const, failure: response.failure };
      }
      router.replace("/app");
      return { ok: true as const };
    });

    if (!result.ok && !result.stale) {
      return;
    }
  }

  return (
    <AuthShell
      title="Multi-factor authentication"
      subtitle="Complete sign-in with your authenticator app."
    >
      <form className="stack" onSubmit={handleSubmit} noValidate>
        <FormErrorSummary failure={form.error} fieldError={form.fieldError} />
        <Alert
          tone="info"
          message="Security keys are not available yet. Use an authenticator code instead."
        />
        <TextField
          name="code"
          label="Authenticator code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          required
        />
        <Button type="button" variant="secondary" disabled aria-disabled="true">
          Use security key (unavailable)
        </Button>
        <Button type="submit" disabled={form.isSubmitting}>
          {form.isSubmitting ? "Verifying…" : "Verify and continue"}
        </Button>
      </form>
    </AuthShell>
  );
}
