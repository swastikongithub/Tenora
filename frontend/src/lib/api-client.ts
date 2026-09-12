/**
 * The single fetch wrapper. Every request to the Django API goes through
 * `request()` — Stage C2 spec §4.1: "per-call header logic is exactly how a
 * request accidentally ships without X-Tenant-ID, or ships it when it
 * shouldn't." Centralizing it is the whole point.
 *
 * Responsibilities, in order:
 *   1. Reject any body that tries to carry a tenant identifier.
 *   2. Attach `Authorization: Bearer <access>` except on the no-auth paths.
 *   3. Attach `X-Tenant-ID: <current tenant>` except on GLOBAL_PATHS (exact
 *      match, mirroring the backend).
 *   4. On a 401: one silent refresh + one retry, then end the session. Never
 *      more than one retry, never a loop.
 *   5. Normalize every failure into an `ApiError`.
 */

import { ApiError } from './api-error'
import { refreshOnce } from './auth/refresh'
import { endSession } from './auth/session'
import { getAccessToken } from './auth/token-store'
import { API_BASE_URL, apiBasePath } from './config'
import { isGlobalPath, isNoAuthPath } from './global-paths'
import { getCurrentTenantId } from './tenant/current-tenant'

type Json = unknown

interface RequestOptions {
  /** Extra headers. Merged over the client's own; the client's win for the ones it owns. */
  headers?: HeadersInit
  signal?: AbortSignal
}

const TENANT_BODY_KEYS = ['tenant_id', 'tenant', 'tenantId']

function assertNoTenantInBody(body: Json): void {
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    for (const key of TENANT_BODY_KEYS) {
      if (key in (body as Record<string, unknown>)) {
        throw new Error(
          `Refusing to send "${key}" in a request body. Tenant is set only via ` +
            `the X-Tenant-ID header (CLAUDE.md: "tenant_id is NEVER accepted ` +
            `from a request body, on any endpoint").`,
        )
      }
    }
  }
}

async function parseBody<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T
  const text = await response.text()
  if (!text) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    return text as unknown as T
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Non-JSON error body (HTML 500 page, empty response) — status only.
  }
  return ApiError.fromBody(response.status, response.statusText, body)
}

async function request<T = unknown>(
  method: string,
  path: string,
  body?: Json,
  options: RequestOptions = {},
  isRetry = false,
): Promise<T> {
  const djangoPath = apiBasePath() + path
  // Operator Control Plane Phase 1 (docs/operator-control-plane-spec.md) is
  // the first caller to ever pass a query string here (`?id=...` for a
  // detail lookup, `?page=...` for pagination) — GLOBAL_PATHS/NO_AUTH_PATHS
  // are exact-match sets of bare paths, so the lookup must run against the
  // path only, never the query string. For every existing call site (no
  // "?"), djangoPathOnly === djangoPath, so this changes nothing for them.
  const djangoPathOnly = djangoPath.split('?')[0]
  const global = isGlobalPath(djangoPathOnly)
  const noAuth = isNoAuthPath(djangoPathOnly)
  const hasBody = body !== undefined && body !== null

  if (hasBody) assertNoTenantInBody(body)

  const headers = new Headers(options.headers)
  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (!noAuth) {
    const access = getAccessToken()
    if (access) headers.set('Authorization', `Bearer ${access}`)
  }

  if (!global) {
    const tenantId = getCurrentTenantId()
    // No tenant selected yet on a tenant-scoped call: omit the header and let
    // the backend answer 400. In practice TenantProvider guarantees a tenant is
    // set before any tenant-scoped query runs.
    if (tenantId) headers.set('X-Tenant-ID', tenantId)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: hasBody ? JSON.stringify(body) : undefined,
      signal: options.signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError')
      throw cause
    throw ApiError.network()
  }

  if (response.status === 401 && !noAuth) {
    if (!isRetry) {
      const refreshed = await refreshOnce()
      if (refreshed) {
        return request<T>(method, path, body, options, true)
      }
    }
    // Either the refresh failed, or the retry still came back 401. Done.
    endSession()
    throw await toApiError(response)
  }

  if (!response.ok) {
    throw await toApiError(response)
  }

  return parseBody<T>(response)
}

export const apiClient = {
  get: <T = unknown>(path: string, options?: RequestOptions) =>
    request<T>('GET', path, undefined, options),
  post: <T = unknown>(path: string, body?: Json, options?: RequestOptions) =>
    request<T>('POST', path, body, options),
  patch: <T = unknown>(path: string, body?: Json, options?: RequestOptions) =>
    request<T>('PATCH', path, body, options),
  delete: <T = unknown>(path: string, options?: RequestOptions) =>
    request<T>('DELETE', path, undefined, options),
}

export type ApiClient = typeof apiClient
