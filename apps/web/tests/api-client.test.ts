import { afterEach, describe, expect, it, vi } from "vitest";

import { requestForTests } from "../lib/auth/api-client";

function getFetchInit(fetchMock: ReturnType<typeof vi.fn>): RequestInit {
  const call = fetchMock.mock.calls[0];
  if (!call || call.length < 2) {
    throw new Error("missing fetch init");
  }

  return call[1] as RequestInit;
}

describe("auth API client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("includes credentials and no-store on requests", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json(
        {
          user_id: "00000000-0000-0000-0000-000000000010",
          session_id: "00000000-0000-0000-0000-000000000100",
          assurance_level: "single_factor",
          expires_at: "2026-07-12T12:00:00.000Z",
          csrf_token: "csrf-token",
        },
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await requestForTests(
      "http://localhost:8000",
      "/api/v1/auth/session",
      {
        method: "GET",
      },
    );

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledOnce();
    const init = getFetchInit(fetchMock);
    expect(init.credentials).toBe("include");
    expect(init.cache).toBe("no-store");
  });

  it("sends CSRF header on unsafe authenticated calls", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await requestForTests("http://localhost:8000", "/api/v1/auth/logout", {
      method: "POST",
      csrfToken: "csrf-token",
    });

    const init = getFetchInit(fetchMock);
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token");
  });

  it("maps login MFA responses", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json(
        {
          state: "mfa_required",
          csrf_token: "csrf-token",
          expires_at: "2026-07-12T12:00:00.000Z",
        },
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await requestForTests<{
      state: string;
      csrf_token: string;
    }>("http://localhost:8000", "/api/v1/auth/login", {
      method: "POST",
      body: { email: "user@example.test", password: "Synthetic-Password-1" },
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.state).toBe("mfa_required");
    }
  });

  it("aborts timed out requests safely", async () => {
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await requestForTests(
      "http://localhost:8000",
      "/api/v1/auth/session",
      {
        method: "GET",
        timeoutMs: 5,
      },
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.kind).toBe("service_unavailable");
    }
  });
});
