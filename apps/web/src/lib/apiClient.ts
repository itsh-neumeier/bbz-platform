/**
 * Generic API client (E07-04 / #99).
 *
 * Mirrors `bbz_core.api` conventions:
 * - base path `/api/v1`, cookies always sent (`credentials: 'include'`);
 * - every write carries the command envelope — a generated `X-Command-Id`
 *   (idempotency, ADR-0012) plus optional `X-Expected-Version` / `X-Client-Id`
 *   / `X-Workplace-Id`;
 * - the CSRF cookie (`bbz_csrf`, E23-05) is echoed in `X-CSRF-Token`;
 * - the uniform error envelope `{error:{code,message,details,correlation_id}}`
 *   becomes a typed {@link ApiError}; `409` becomes {@link ConflictError} with
 *   the server's `expected_version` when present;
 * - `401` on a *cookie* session is surfaced as {@link AuthExpiredError} so the
 *   router can bounce to `/login` without losing the open form.
 *
 * No access token is ever read or stored client-side — it lives in an HttpOnly
 * cookie (security AC of #97).
 */

const BASE = '/api/v1';
const SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
  correlation_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly correlationId?: string;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.code || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? null;
    this.correlationId = body.correlation_id;
  }
}

/** 409 — an optimistic-concurrency or idempotency-key conflict. */
export class ConflictError extends ApiError {
  readonly expectedVersion?: number;
  constructor(status: number, body: ApiErrorBody) {
    super(status, body);
    this.name = 'ConflictError';
    const d = body.details as { expected_version?: number } | null;
    this.expectedVersion = d?.expected_version;
  }
}

/** 401 while a session cookie was present — the session lapsed / was revoked. */
export class AuthExpiredError extends ApiError {
  constructor(status: number, body: ApiErrorBody) {
    super(status, body);
    this.name = 'AuthExpiredError';
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  /** folded into `X-Expected-Version` for a guarded write. */
  expectedVersion?: number;
  /** reuse a command id to retry a write idempotently; defaults to a fresh v4. */
  commandId?: string;
  clientId?: string;
  workplaceId?: string;
  signal?: AbortSignal;
  /** override for tests. */
  fetchImpl?: typeof fetch;
}

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : null;
}

/** A v4 UUID — the server requires `X-Command-Id` to parse as a UUID.
 *  `crypto.randomUUID` needs a secure context (HTTPS / localhost), so fall back
 *  to `getRandomValues` (available on plain HTTP too), then to `Math.random`. */
function newCommandId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  const b = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0'));
  return `${h.slice(0, 4).join('')}-${h.slice(4, 6).join('')}-${h.slice(6, 8).join('')}-${h.slice(8, 10).join('')}-${h.slice(10, 16).join('')}`;
}

let hadSessionCookie = false;
/** the router sets this once a session exists, so a 401 can be classified. */
export function markAuthenticated(v: boolean): void {
  hadSessionCookie = v;
}

export async function apiRequest<T = unknown>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const method = (opts.method ?? 'GET').toUpperCase();
  const doFetch = opts.fetchImpl ?? fetch;
  const headers: Record<string, string> = { Accept: 'application/json' };

  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';

  if (!SAFE.has(method)) {
    headers['X-Command-Id'] = opts.commandId ?? newCommandId();
    if (opts.expectedVersion !== undefined)
      headers['X-Expected-Version'] = String(opts.expectedVersion);
    if (opts.clientId) headers['X-Client-Id'] = opts.clientId;
    if (opts.workplaceId) headers['X-Workplace-Id'] = opts.workplaceId;
    const csrf = readCookie('bbz_csrf');
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }

  const res = await doFetch(BASE + path, {
    method,
    headers,
    credentials: 'include',
    signal: opts.signal,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const payload: unknown = text ? JSON.parse(text) : null;

  if (res.ok) return payload as T;

  const body: ApiErrorBody =
    payload && typeof payload === 'object' && 'error' in payload
      ? (payload as { error: ApiErrorBody }).error
      : { code: 'http_error', message: `HTTP ${res.status}` };

  if (res.status === 409) throw new ConflictError(res.status, body);
  if (res.status === 401 && hadSessionCookie) throw new AuthExpiredError(res.status, body);
  throw new ApiError(res.status, body);
}

export const api = {
  get: <T>(path: string, o?: RequestOptions) => apiRequest<T>(path, { ...o, method: 'GET' }),
  post: <T>(path: string, body?: unknown, o?: RequestOptions) =>
    apiRequest<T>(path, { ...o, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, o?: RequestOptions) =>
    apiRequest<T>(path, { ...o, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, o?: RequestOptions) =>
    apiRequest<T>(path, { ...o, method: 'PATCH', body }),
  del: <T>(path: string, o?: RequestOptions) => apiRequest<T>(path, { ...o, method: 'DELETE' }),
};
