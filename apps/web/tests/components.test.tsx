import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EmptyWorkspaceState } from "../components/app/app-shell";
import { Alert } from "../components/auth/alert";
import { AuthShell } from "../components/auth/auth-shell";
import { GENERIC_REGISTRATION } from "../lib/auth/messages";

describe("auth UI components", () => {
  it("renders auth shell landmarks", () => {
    const markup = renderToStaticMarkup(
      <AuthShell title="Sign in" subtitle="Access your workspace.">
        <p>Form content</p>
      </AuthShell>,
    );

    expect(markup).toContain("CloserOS AI");
    expect(markup).toContain("Sign in");
    expect(markup).toContain("<main");
  });

  it("renders generic success alerts", () => {
    const markup = renderToStaticMarkup(
      <Alert tone="success" message={GENERIC_REGISTRATION} />,
    );

    expect(markup).toContain(GENERIC_REGISTRATION);
    expect(markup).toContain('role="status"');
  });

  it("renders the workspace empty state without invented metrics", () => {
    const markup = renderToStaticMarkup(<EmptyWorkspaceState />);

    expect(markup).toContain("Product modules are being implemented");
    expect(markup).not.toContain("testimonial");
    expect(markup).not.toContain("revenue");
  });
});

describe("public auth exports", () => {
  it("exports the typed auth client surface", async () => {
    const auth = await import("../lib/auth");
    expect(typeof auth.createAuthApiClient).toBe("function");
    expect(typeof auth.resolveApiBaseUrl).toBe("function");
    expect(typeof auth.useAuth).toBe("function");
  });
});
