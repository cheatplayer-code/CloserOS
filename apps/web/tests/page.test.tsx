import { describe, expect, it } from "vitest";

describe("app routes", () => {
  it("exports authentication route modules", async () => {
    const routes = await Promise.all([
      import("../app/auth/sign-in/page"),
      import("../app/auth/register/page"),
      import("../app/auth/verify-email/page"),
      import("../app/auth/mfa/page"),
      import("../app/app/page"),
      import("../app/settings/security/page"),
    ]);

    for (const route of routes) {
      expect(typeof route.default).toBe("function");
    }
  });
});
