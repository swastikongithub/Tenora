/**
 * Token refresh — the one request that cannot go through the API client
 * (the client calls this on a 401, so routing it back through the client
 * would recurse).
 *
 * SimpleJWT is configured with `ROTATE_REFRESH_TOKENS: True` and
 * `BLACKLIST_AFTER_ROTATION: True` (config/settings.py), so every successful
 * refresh returns a NEW refresh token and blacklists the old one. The new one
 * must replace the stored value or the next refresh fails.
 */

import { API_BASE_URL } from '../config'
import {
  clearTokens,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from './token-store'

interface RefreshResponse {
  access: string
  refresh?: string
}

/**
 * Attempt one refresh. Resolves `true` when a new access token was stored,
 * `false` otherwise. A definitive rejection by the server (non-2xx) also clears
 * the stored tokens — the refresh token is spent or invalid, keeping it would
 * only cause the same failure on the next load (spec §4.2: "Failure -> clear
 * it, treat as logged out").
 */
async function performRefresh(): Promise<boolean> {
  const refresh = getRefreshToken()
  if (!refresh) return false

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
  } catch {
    // Transport failure — don't discard the token over a flaky network; a
    // later attempt (next reload, next 401) can still succeed.
    return false
  }

  if (!response.ok) {
    clearTokens()
    return false
  }

  let data: RefreshResponse
  try {
    data = (await response.json()) as RefreshResponse
  } catch {
    clearTokens()
    return false
  }

  if (!data.access) {
    clearTokens()
    return false
  }

  setAccessToken(data.access)
  if (data.refresh) setRefreshToken(data.refresh) // rotation
  return true
}

let inFlight: Promise<boolean> | null = null

/**
 * Coalesced refresh: concurrent callers (a burst of requests all getting 401 at
 * once) share a single network round trip instead of each spending the refresh
 * token in turn — which, with rotation on, would blacklist it mid-flight and
 * log the user out.
 */
export function refreshOnce(): Promise<boolean> {
  if (!inFlight) {
    inFlight = performRefresh().finally(() => {
      inFlight = null
    })
  }
  return inFlight
}
