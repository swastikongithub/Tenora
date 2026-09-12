/**
 * Frontend mirror of `apps/tenants/authentication.py` `GLOBAL_PATHS`.
 *
 * EXACT string match, never a prefix test — CLAUDE.md:
 *   "GLOBAL_PATHS is an exact-match frozenset, never prefix matching. A prefix
 *    would silently exempt every future sub-route from tenant resolution."
 *
 * The backend decides, per request path, whether `X-Tenant-ID` is required. The
 * client must make the identical decision or it will either ship a request
 * without the header (backend 400) or leak a tenant header onto a global route.
 * A path here that drifts from the Python set breaks that in silence, so keep
 * this list byte-identical to the backend one.
 */
export const GLOBAL_PATHS: ReadonlySet<string> = new Set([
  '/api/auth/login/',
  '/api/auth/refresh/',
  '/api/auth/register/',
  '/api/auth/logout/',
  '/api/auth/verify-email/',
  '/api/auth/resend-verification/',
  '/api/auth/google/',
  '/api/tenants/',
  '/api/tenants/me/',
  '/api/users/me/',
  '/api/plans/',
  // Platform-admin (docs/platform-admin-spec.md): deliberately cross-tenant,
  // so no X-Tenant-ID. Still authenticated (a valid Bearer token, gated by
  // IsPlatformStaff server-side) — hence NOT in NO_AUTH_PATHS.
  '/api/platform/tenants/',
  '/api/platform/stats/',
  // Operator Control Plane, Phase 1 (docs/operator-control-plane-spec.md) —
  // kept byte-identical to apps/tenants/authentication.py's GLOBAL_PATHS.
  // Detail lookups are `?id=` on a static path (see api-client.ts's
  // djangoPathOnly — the query string is stripped before this set is
  // checked, so the bare path below is the correct, complete entry).
  '/api/platform/health/',
  '/api/platform/plans/',
  '/api/platform/plans/detail/',
  '/api/platform/tenants/detail/',
  '/api/platform/webhook-events/',
  '/api/platform/webhook-events/detail/',
  '/api/platform/reconciliation-discrepancies/',
  '/api/platform/users/',
  '/api/platform/users/detail/',
])

/**
 * The subset of global paths that additionally take NO `Authorization` header —
 * there is no access token yet when these run. `/api/tenants/me/`, `/api/users/me/`,
 * `/api/auth/logout/` and `/api/plans/` are global (no tenant header) but still
 * authenticated, so they are deliberately NOT in this set — logout in particular
 * needs the Bearer token to identify who is logging out.
 */
export const NO_AUTH_PATHS: ReadonlySet<string> = new Set([
  '/api/auth/login/',
  '/api/auth/refresh/',
  '/api/auth/register/',
  '/api/auth/verify-email/',
  '/api/auth/resend-verification/',
  '/api/auth/google/',
])

/** True when the given absolute Django path must NOT carry `X-Tenant-ID`. */
export function isGlobalPath(djangoPath: string): boolean {
  return GLOBAL_PATHS.has(djangoPath)
}

/** True when the given absolute Django path must NOT carry `Authorization`. */
export function isNoAuthPath(djangoPath: string): boolean {
  return NO_AUTH_PATHS.has(djangoPath)
}
