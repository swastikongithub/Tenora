/**
 * The auth context object and its hook. Kept separate from the provider
 * component (AuthProvider.tsx) so each file exports one kind of thing — a
 * requirement of the `react-refresh/only-export-components` lint rule, and a
 * clean seam regardless.
 */

import { createContext, useContext } from 'react'

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface AuthContextValue {
  status: AuthStatus
  isAuthenticated: boolean
  /**
   * The logged-in user's email, or `null` when it isn't known — it is known
   * only in the session that logged in (the login form provides it), not after
   * a silent-refresh reload. There is no endpoint to recover it. Treat as a
   * display convenience, never as identity for a decision.
   */
  userEmail: string | null
  /**
   * Exchange credentials for a token pair. Rejects with an `ApiError` on a bad
   * login (401) — the caller renders one generic message and does NOT
   * distinguish unknown-email from wrong-password (Stage C2 spec §7).
   */
  login: (email: string, password: string) => Promise<void>
  /**
   * Exchange a Google ID token (the `credential` from Google's button
   * callback) for a token pair — google-signin-spec.md §4.3. Mirrors
   * `login()`'s shape exactly so a caller treats a successful Google
   * sign-in identically to a successful password one. `userEmail` stays
   * `null` afterward, same as a silent-refresh reload — `useCurrentUser()`
   * already falls back to `GET /api/users/me/` for that case.
   */
  loginWithGoogle: (credential: string) => Promise<void>
  /** Clear tokens and tenant context locally. Never fails. */
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error('useAuth must be used within an <AuthProvider>')
  }
  return value
}
