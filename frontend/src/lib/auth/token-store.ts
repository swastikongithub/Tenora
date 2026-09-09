/**
 * Where the JWT pair lives. Stage C2 spec §4.2 locks this for the stage:
 *
 *   Access token  -> in memory only (this module's closure). Never written to
 *                    localStorage or sessionStorage: a persisted access token is
 *                    a standing bearer credential that any XSS payload can read
 *                    and exfiltrate for its full 30-minute lifetime.
 *
 *   Refresh token -> sessionStorage. This is a real tradeoff, not a
 *                    best-practice: sessionStorage is readable by ANY script on
 *                    the page, so against XSS it is no better than memory. What
 *                    it buys is that it clears when the tab closes (unlike
 *                    localStorage, which would keep a 7-day refresh token on
 *                    disk across browser restarts). A proper fix — an
 *                    HttpOnly, SameSite refresh cookie — needs a backend change
 *                    that is out of scope for this stage.
 */

const REFRESH_TOKEN_KEY = 'billing.refresh_token'

let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string): void {
  accessToken = token
}

export function clearAccessToken(): void {
  accessToken = null
}

export function getRefreshToken(): string | null {
  try {
    return sessionStorage.getItem(REFRESH_TOKEN_KEY)
  } catch {
    // sessionStorage can throw in locked-down privacy modes.
    return null
  }
}

export function setRefreshToken(token: string): void {
  try {
    sessionStorage.setItem(REFRESH_TOKEN_KEY, token)
  } catch {
    // Non-fatal: the session simply won't survive a reload.
  }
}

export function clearRefreshToken(): void {
  try {
    sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

/** Store a fresh pair (login, or a rotated refresh response). */
export function setTokens(access: string, refresh: string): void {
  setAccessToken(access)
  setRefreshToken(refresh)
}

/** Drop everything. Used by logout and by the ended-session path. */
export function clearTokens(): void {
  clearAccessToken()
  clearRefreshToken()
}
