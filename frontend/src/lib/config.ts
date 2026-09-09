/**
 * Frontend runtime config. The one place an environment value is read.
 */

/**
 * Every request the API client makes is `API_BASE_URL + path`. In dev this is
 * `/api` and Vite proxies it to Django (vite.config.ts `server.proxy`), so the
 * browser makes same-origin requests and no CORS config is needed on the
 * backend — Stage C2 spec §4.7. A deployed build can override it via
 * `VITE_API_BASE_URL` (e.g. an absolute origin) without a code change.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

/**
 * The path portion of `API_BASE_URL`, with any trailing slash removed, used to
 * reconstruct the absolute Django path of a request for the `GLOBAL_PATHS`
 * exact-match test. `/api` -> `/api`; `https://host/api/` -> `/api`.
 */
export function apiBasePath(): string {
  let path = API_BASE_URL
  try {
    // window.location is always present in the app and in the jsdom test env.
    path = new URL(API_BASE_URL, window.location.origin).pathname
  } catch {
    // API_BASE_URL was already a bare path — use it as-is.
  }
  return path.replace(/\/$/, '')
}

/**
 * google-signin-spec.md — the Google Cloud OAuth Client ID the "Sign in with
 * Google" button initializes with. Empty string (not undefined) when unset,
 * so GoogleSignInButton's own guard (`if (!GOOGLE_OAUTH_CLIENT_ID) return`)
 * is a simple truthiness check.
 */
export const GOOGLE_OAUTH_CLIENT_ID: string =
  import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID ?? ''
