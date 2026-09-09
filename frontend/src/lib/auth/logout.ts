/**
 * Best-effort server-side logout (Stage C3 §4.6).
 *
 * Fires `POST /api/auth/logout/` with the current refresh token so SimpleJWT
 * blacklists it — closing the C2 gap where a captured refresh token stayed
 * valid for its full 7-day life after the user logged out.
 *
 * Deliberately NOT routed through `api-client.ts`, same reasoning as
 * `refresh.ts`: the client reacts to a 401 with refresh-and-retry and then
 * `endSession()`, which is nonsense for a request whose whole job is to end the
 * session. A bare `fetch` also lets us read both tokens synchronously here,
 * before the caller's `endSession()` clears them, with no ordering assumptions.
 *
 * Fire-and-forget: the caller clears local state and redirects regardless of
 * whether this resolves, rejects, or the network is down (§8 edge case).
 */

import { API_BASE_URL } from '../config'
import { getAccessToken, getRefreshToken } from './token-store'

export function logoutOnce(): void {
  const refresh = getRefreshToken()
  if (!refresh) return

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  const access = getAccessToken()
  if (access) headers.Authorization = `Bearer ${access}`

  void fetch(`${API_BASE_URL}/auth/logout/`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ refresh }),
    // Let the request finish even if a navigation/tab-close follows immediately.
    keepalive: true,
  }).catch(() => {
    // Offline, or the token was already dead — logout still proceeds locally.
  })
}
