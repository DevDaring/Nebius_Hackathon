import { useAuth } from "@/store/auth";

export class ApiError extends Error {
  status: number;
  body: unknown;
  /** Machine-readable code from a structured detail ({detail: {code, message}}), e.g. "stale_observation". */
  code: string | null;
  /** Seconds from a Retry-After header (HTTP 429). */
  retryAfter: number | null;
  constructor(status: number, message: string, body?: unknown, retryAfter: number | null = null) {
    super(message);
    this.status = status;
    this.body = body;
    this.retryAfter = retryAfter;
    const d = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
    this.code = d && typeof d === "object" && "code" in d && typeof (d as { code: unknown }).code === "string" ? (d as { code: string }).code : null;
  }
}

/** Parse a Retry-After header (seconds or an HTTP date). */
export function parseRetryAfter(v: string | null, now = Date.now()): number | null {
  if (!v) return null;
  const n = Number(v);
  if (Number.isFinite(n)) return Math.max(0, Math.round(n));
  const d = Date.parse(v);
  return Number.isFinite(d) ? Math.max(0, Math.round((d - now) / 1000)) : null;
}

/** The human message inside a FastAPI error body: {detail: "..."} or {detail: {message: "..."}}. */
export function detailMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const d = (body as { detail: unknown }).detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && "message" in d && typeof (d as { message: unknown }).message === "string") return (d as { message: string }).message;
  return null;
}

/** Thrown when the backend cannot be reached at all (network error / proxy cannot connect). */
export class UnreachableError extends Error {}

const BASE = "/api";

type Body = FormData | Record<string, unknown> | unknown[] | undefined;

interface Opts {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: Body;
  auth?: boolean;
  raw?: boolean;
  /** Return the body as text (e.g. a Markdown receipt). */
  text?: boolean;
  signal?: AbortSignal;
}

export async function request<T>(path: string, opts: Opts = {}): Promise<T> {
  const { method = opts.body ? "POST" : "GET", body, auth = true, raw = false, text: asText = false, signal } = opts;
  const headers: Record<string, string> = { Accept: raw || asText ? "*/*" : "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (auth) {
    const token = useAuth.getState().token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers, body: payload, signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new UnreachableError((e as Error).message || "Network error");
  }

  if (!res.ok) {
    let detail: unknown = null;
    const text = await res.text().catch(() => "");
    try {
      detail = text ? JSON.parse(text) : null;
    } catch {
      detail = text;
    }
    // Vite's proxy (or Caddy) answers 500/502/503/504 with a non-JSON body when the backend is down.
    // A JSON body with a "detail" means the backend itself answered (e.g. 503 "needs live mode").
    const backendAnswered = detail !== null && typeof detail === "object";
    if (!backendAnswered && [500, 502, 503, 504].includes(res.status)) {
      throw new UnreachableError(`Backend unreachable (${res.status})`);
    }
    if (res.status === 401 && auth) useAuth.getState().logout();
    const msg = detailMessage(detail) ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, detail, parseRetryAfter(res.headers.get("Retry-After")));
  }

  if (raw) return (await res.blob()) as T;
  if (asText) return (await res.text()) as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Media URLs from the backend are used as given (absolute, or root-relative under /api). */
export function mediaUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return url;
}
