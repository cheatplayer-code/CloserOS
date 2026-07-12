import type { ReactNode } from "react";

interface AuthShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

export function AuthShell({ title, subtitle, children }: AuthShellProps) {
  return (
    <div className="auth-page">
      <div className="auth-page__brand" aria-hidden="false">
        <div className="auth-page__brand-inner">
          <p className="auth-page__eyebrow">CloserOS AI</p>
          <h1 className="auth-page__headline">
            Sales operations for messaging teams
          </h1>
          <p className="auth-page__lede">
            Secure sign-in, verified accounts, and session-aware access to your
            workspace.
          </p>
        </div>
      </div>
      <div className="auth-page__panel">
        <main className="auth-page__main" aria-labelledby="auth-page-title">
          <AuthCard title={title} subtitle={subtitle}>
            {children}
          </AuthCard>
        </main>
      </div>
    </div>
  );
}

interface AuthCardProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

export function AuthCard({ title, subtitle, children }: AuthCardProps) {
  return (
    <section className="auth-card" aria-labelledby="auth-page-title">
      <header className="auth-card__header">
        <h2 id="auth-page-title">{title}</h2>
        <p>{subtitle}</p>
      </header>
      {children}
    </section>
  );
}
