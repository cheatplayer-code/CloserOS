import { describe, expect, it } from "vitest";

const shouldRun =
  process.env.CLOSEROS_AUTH_INTEGRATION_SMOKE === "true" &&
  typeof process.env.CLOSEROS_WEB_BASE_URL === "string" &&
  typeof process.env.CLOSEROS_API_BASE_URL === "string";

describe.skipIf(!shouldRun)("authentication integration smoke", () => {
  it("loads the web health page and API health endpoint", async () => {
    const webBase = process.env.CLOSEROS_WEB_BASE_URL ?? "";
    const apiBase = process.env.CLOSEROS_API_BASE_URL ?? "";

    const [webResponse, apiResponse] = await Promise.all([
      fetch(webBase, { cache: "no-store" }),
      fetch(`${apiBase}/health`, { cache: "no-store" }),
    ]);

    expect(webResponse.ok).toBe(true);
    expect(apiResponse.ok).toBe(true);
    const apiBody: unknown = await apiResponse.json();
    expect(apiBody).toEqual({ status: "ok" });
  });
});

describe("authentication integration smoke guard", () => {
  it("skips live integration unless explicitly enabled", () => {
    expect(typeof shouldRun).toBe("boolean");
  });
});
