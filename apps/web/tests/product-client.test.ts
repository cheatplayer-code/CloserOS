import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequestForTests } from "../lib/api/http";
import {
  buildQueryString,
  createProductApiClient,
} from "../lib/api/product-client";

const BASE_URL = "http://localhost:8000";
const TENANT_ID = "00000000-0000-0000-0000-000000000001";

function getFetchInit(fetchMock: ReturnType<typeof vi.fn>): RequestInit {
  const call = fetchMock.mock.calls[0];
  if (!call || call.length < 2) {
    throw new Error("missing fetch init");
  }

  return call[1] as RequestInit;
}

function getFetchUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  const call = fetchMock.mock.calls[0] as [string, RequestInit] | undefined;
  if (!call) {
    throw new Error("missing fetch call");
  }

  return call[0];
}

describe("product API client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds dashboard query paths with window parameters", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json(
        {
          formula_version: "v1",
          window_start: "2026-07-05T00:00:00.000Z",
          window_end: "2026-07-12T00:00:00.000Z",
          previous_window_start: "2026-06-28T00:00:00.000Z",
          previous_window_end: "2026-07-05T00:00:00.000Z",
          total_conversations: 0,
          open_high_severity_findings: 0,
          overdue_follow_up_tasks: 0,
          metrics: [],
          manager_summaries: [],
        },
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = createProductApiClient();
    const result = await client.getDashboard(TENANT_ID, {
      window_start: "2026-07-05T00:00:00.000Z",
      window_end: "2026-07-12T00:00:00.000Z",
    });

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(getFetchUrl(fetchMock)).toBe(
      `${BASE_URL}/api/v1/tenants/${TENANT_ID}/dashboard?window_start=2026-07-05T00%3A00%3A00.000Z&window_end=2026-07-12T00%3A00%3A00.000Z`,
    );
  });

  it("builds conversation list filters without empty values", () => {
    expect(
      buildQueryString({
        limit: 25,
        provider: "",
        has_unresolved_task: true,
      }),
    ).toBe("?limit=25&has_unresolved_task=true");
  });

  it("maps forbidden responses to security failures", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ detail: "access denied" }, { status: 403 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = createProductApiClient();
    const result = await client.listManagers(TENANT_ID);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.kind).toBe("security_failed");
    }
  });

  it("sends CSRF header when enqueueing analysis", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ accepted: true }, { status: 202 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = createProductApiClient();
    await client.enqueueAnalysis(
      TENANT_ID,
      "00000000-0000-0000-0000-000000000010",
      "csrf-token",
    );

    const init = getFetchInit(fetchMock);
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(init.method).toBe("POST");
  });

  it("uses PATCH for task updates", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json(
        {
          id: "00000000-0000-0000-0000-000000000020",
          conversation_thread_id: "00000000-0000-0000-0000-000000000010",
          source_finding_id: null,
          title: "Follow up",
          status: "completed",
          priority: "normal",
          assigned_membership_id: null,
          due_at: null,
          completed_at: "2026-07-12T12:00:00.000Z",
          cancelled_at: null,
          created_at: "2026-07-12T10:00:00.000Z",
          updated_at: "2026-07-12T12:00:00.000Z",
          version: 2,
        },
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = createProductApiClient();
    await client.updateTask(
      TENANT_ID,
      "00000000-0000-0000-0000-000000000020",
      { version: 1, action: "complete" },
      "csrf-token",
    );

    const init = getFetchInit(fetchMock);
    expect(init.method).toBe("PATCH");
    expect(getFetchUrl(fetchMock)).toBe(
      `${BASE_URL}/api/v1/tenants/${TENANT_ID}/tasks/00000000-0000-0000-0000-000000000020`,
    );
  });

  it("maps network failures through shared HTTP helper", async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiRequestForTests(
      BASE_URL,
      `/api/v1/tenants/${TENANT_ID}/tasks`,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.kind).toBe("service_unavailable");
    }
  });
});
