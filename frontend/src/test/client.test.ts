import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, getTenantId, setApiKey, setTenantId } from "../lib/api/client";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("apiRequest", () => {
  beforeEach(() => {
    sessionStorage.clear();
    setTenantId("test-tenant");
    setApiKey("");
  });
  afterEach(() => vi.restoreAllMocks());

  it("sends tenant header and parses JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const data = await apiRequest<{ ok: boolean }>("/health");
    expect(data.ok).toBe(true);
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("X-Tenant-ID")).toBe("test-tenant");
  });

  it("sends API key header when configured", async () => {
    setApiKey("ak_test_key");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/health");
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("X-API-Key")).toBe("ak_test_key");
  });

  it("maps backend error contract to ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      jsonResponse(429, { code: "rate_limited", message: "Too many requests" },
        { "Retry-After": "30", "X-Request-ID": "req-9" }),
    ));
    const err = await apiRequest("/api/v1/payments/score", { method: "POST", body: "{}" })
      .catch((e) => e) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(429);
    expect(err.code).toBe("rate_limited");
    expect(err.retryAfter).toBe(30);
    expect(err.requestId).toBe("req-9");
  });

  it("produces a network error when the server is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    const err = await apiRequest("/health").catch((e) => e) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network_error");
  });

  it("returns human-readable fallback for non-JSON errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response("gateway timeout", { status: 503 }),
    ));
    const err = await apiRequest("/health").catch((e) => e) as ApiError;
    expect(err.status).toBe(503);
    expect(err.message).toMatch(/temporarily unavailable/i);
  });

  it("uses the fallback tenant when none is set", () => {
    sessionStorage.removeItem("authetec.tenant");
    expect(getTenantId()).toBe("default");
  });
});
