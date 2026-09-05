/**
 * HTTP client for the Authetec API.
 *
 * - Attaches tenant context and (if configured) the API key on every call.
 * - Translates backend error contracts into human-readable messages.
 * - Surfaces correlation ids so users can report issues traceably.
 * - Never logs or persists the raw API key beyond the session storage the
 *   user explicitly configured (dev convenience; production deployments
 *   replace this with server-side authentication).
 */

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  retryAfter?: number;

  constructor(status: number, code: string, message: string,
              requestId?: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

const TENANT_KEY = "authetec.tenant";
const API_KEY = "authetec.apiKey";

export function getTenantId(): string {
  return sessionStorage.getItem(TENANT_KEY) ?? "default";
}

export function setTenantId(tenant: string): void {
  sessionStorage.setItem(TENANT_KEY, tenant.trim() || "default");
}

export function getApiKey(): string {
  return sessionStorage.getItem(API_KEY) ?? "";
}

/** Returns the stored API key masked for display (never show the raw key). */
export function getMaskedApiKey(): string {
  const key = getApiKey();
  if (!key) return "";
  return key.slice(0, 5) + "…" + key.slice(-2);
}

export function setApiKey(key: string): void {
  if (key.trim()) sessionStorage.setItem(API_KEY, key.trim());
  else sessionStorage.removeItem(API_KEY);
}

export function hasApiKey(): boolean {
  return getApiKey().length > 0;
}

const HUMAN_MESSAGES: Record<number, string> = {
  400: "The request was rejected. Check the submitted values.",
  401: "Authentication required. Configure a valid API key.",
  403: "You do not have permission to perform this action.",
  404: "The requested resource was not found.",
  409: "The request conflicts with the current state.",
  413: "The uploaded file is too large.",
  415: "This file type is not supported.",
  429: "Rate limit reached. Please wait before retrying.",
  500: "An internal error occurred. The issue has been logged.",
  503: "The service is temporarily unavailable.",
};

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Tenant-ID", getTenantId());
  const apiKey = getApiKey();
  if (apiKey) headers.set("X-API-Key", apiKey);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "network_error",
      "Cannot reach the Authetec API. Check your connection and try again.");
  }

  if (!res.ok) {
    let code = "http_error";
    let message = HUMAN_MESSAGES[res.status] ?? `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.code) code = body.code;
      if (body?.message) message = body.message;
    } catch {
      /* non-JSON error body — keep fallback message */
    }
    const requestId = res.headers.get("X-Request-ID") ?? undefined;
    const retryAfter = res.headers.get("Retry-After") ?? undefined;
    throw new ApiError(res.status, code, message, requestId,
      retryAfter ? Number(retryAfter) : undefined);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
