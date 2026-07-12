import { describe, expect, it } from "vitest";

import {
  InvalidApiBaseUrlError,
  resolveApiBaseUrl,
} from "../lib/auth/api-base";

describe("resolveApiBaseUrl", () => {
  it("defaults to local development API base", () => {
    expect(resolveApiBaseUrl(undefined)).toBe("http://localhost:8000");
  });

  it("strips trailing slashes", () => {
    expect(resolveApiBaseUrl("http://localhost:8000/")).toBe(
      "http://localhost:8000",
    );
  });

  it("rejects credentials in the URL", () => {
    const user = "user";
    const pass = "pass";
    expect(() =>
      resolveApiBaseUrl(`http://${user}:${pass}@localhost:8000`),
    ).toThrow(InvalidApiBaseUrlError);
  });

  it("rejects query and hash values", () => {
    expect(() => resolveApiBaseUrl("http://localhost:8000?debug=1")).toThrow(
      InvalidApiBaseUrlError,
    );
    expect(() => resolveApiBaseUrl("http://localhost:8000#token")).toThrow(
      InvalidApiBaseUrlError,
    );
  });

  it("allows HTTP for localhost and 127.0.0.1", () => {
    expect(resolveApiBaseUrl("http://127.0.0.1:8000")).toBe(
      "http://127.0.0.1:8000",
    );
  });

  it("requires HTTPS for non-local hosts", () => {
    expect(resolveApiBaseUrl("https://app.example.test")).toBe(
      "https://app.example.test",
    );
    expect(() => resolveApiBaseUrl("http://app.example.test")).toThrow(
      InvalidApiBaseUrlError,
    );
  });
});
