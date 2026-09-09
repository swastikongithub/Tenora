/**
 * Auth state for the React tree: are we logged in, and the login / logout
 * actions. Token storage and refresh mechanics live in sibling modules
 * (token-store, refresh, session) so the non-React API client can use them too;
 * this file is only the React seam.
 *
 * Stage C2 spec §4.2 / §4.5:
 *   - On load, if a refresh token exists, try to refresh BEFORE any
 *     authenticated UI renders. `status` stays `'loading'` until that resolves,
 *     so `ProtectedRoute` (next session) never flashes the login page on a
 *     valid reload.
 *
 * Stage C3 §4.6: `logout()` now also fires `POST /api/auth/logout/`
 * (best-effort, via `logoutOnce`) to blacklist the refresh token server-side.
 * Local state still clears unconditionally — a failed or offline logout must
 * not block the user from logging out here.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

import { apiClient } from '../api-client'
import { queryClient } from '../query-client'
import {
  clearStoredTenantId,
  setCurrentTenantId,
} from '../tenant/current-tenant'
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
} from './auth-context'
import { logoutOnce } from './logout'
import { refreshOnce } from './refresh'
import { endSession, onSessionEnded } from './session'
import { clearTokens, getRefreshToken, setTokens } from './token-store'

interface LoginResponse {
  access: string
  refresh: string
}

/**
 * Drop every trace of the previous identity's client-held state before the next
 * identity is established. Without this, a logout -> login (or Google login)
 * within the same page load — no full reload — leaves the prior user's
 * React Query cache (including the `['global', 'tenants', 'me']` list) and the
 * `billing.last_tenant_id` hint in place. `TenantProvider` then re-selects the
 * prior user's tenant, and the first tenant-scoped request ships that stale
 * `X-Tenant-ID` — which the backend correctly rejects with a 403
 * (`not_a_member`). Runs on session end AND on every successful login so a
 * future auth-flow change can't reintroduce the reuse.
 */
function clearIdentityState(): void {
  queryClient.clear()
  setCurrentTenantId(null)
  clearStoredTenantId()
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  // Known only within the session that logged in — the login form gives us the
  // email. After a silent-refresh reload there is no way to recover it: no
  // endpoint returns the current user and the JWT carries only `user_id`.
  // A `GET /api/users/me/` would fix this (and the logout gap); a backend
  // change, out of scope for Stage C2 — see README.
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const bootstrapped = useRef(false)

  useEffect(() => {
    // Guard against StrictMode's double effect invocation. `refreshOnce()`
    // already coalesces concurrent callers, so the guard is only here to avoid
    // a redundant call — NOT to make the result conditional. The ref is reset
    // in cleanup so StrictMode's second mount re-runs bootstrap: without that,
    // the first run's `cancelled` closure is already true by the time its
    // await resolves, and the second run bails on the guard — leaving `status`
    // stuck on 'loading' forever on any authenticated reload (dev only, but a
    // real hang). C3 §4.4 needs a reloaded session to reach 'authenticated'.
    if (bootstrapped.current) return
    bootstrapped.current = true

    let cancelled = false

    async function bootstrap() {
      if (!getRefreshToken()) {
        if (!cancelled) setStatus('unauthenticated')
        return
      }
      const ok = await refreshOnce()
      if (cancelled) return
      if (ok) {
        setStatus('authenticated')
      } else {
        clearTokens()
        setStatus('unauthenticated')
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
      bootstrapped.current = false
    }
  }, [])

  useEffect(() => {
    // The API client ended the session from inside a failed request.
    return onSessionEnded(() => {
      clearIdentityState()
      setUserEmail(null)
      setStatus('unauthenticated')
    })
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { access, refresh } = await apiClient.post<LoginResponse>(
      '/auth/login/',
      { email, password },
    )
    // Discard any prior identity's cache / tenant hint before this session's
    // first authenticated render — see clearIdentityState.
    clearIdentityState()
    setTokens(access, refresh)
    setUserEmail(email)
    setStatus('authenticated')
  }, [])

  const loginWithGoogle = useCallback(async (credential: string) => {
    const { access, refresh } = await apiClient.post<LoginResponse>(
      '/auth/google/',
      { credential },
    )
    clearIdentityState()
    setTokens(access, refresh)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(() => {
    // Best-effort server-side blacklist FIRST, while the tokens still exist
    // (§4.6) — logoutOnce reads them synchronously and fires without awaiting.
    logoutOnce()
    // endSession clears tokens and fires the listener above, which drops the
    // tenant context and flips status to unauthenticated — unconditionally, so
    // an offline or already-expired logout still logs the user out here.
    endSession()
  }, [])

  const value: AuthContextValue = {
    status,
    isAuthenticated: status === 'authenticated',
    userEmail,
    login,
    loginWithGoogle,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
