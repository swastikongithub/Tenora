/**
 * Resolves the signed-in user's email for the account menu — the same logic
 * that lived inline in `UserMenu` (Stage C3 §4.4), lifted into a hook so both
 * the avatar trigger (needs the initial) and the menu body (needs the full
 * email) read it without duplicating the query or the preference order.
 *
 *   1. `AuthProvider.userEmail` — set only by the login form this session, so a
 *      fresh login shows the email with no skeleton flash.
 *   2. `GET /api/users/me/`, keyed globally (`['global','user','me']`) so it
 *      survives a tenant switch. Same key as before → TanStack dedupes, no
 *      second request.
 *   3. On query failure (network, not auth) we fall back to null and callers
 *      render a neutral label rather than crash the shell (§8).
 */

import { useQuery } from '@tanstack/react-query'

import { apiClient } from '../../lib/api-client'
import { useAuth } from '../../lib/auth'
import { queryKeys } from '../../lib/query-keys'

interface CurrentUser {
  id: string
  email: string
  /** Platform-staff flag — gates the platform-admin dashboard (spec §4.4). */
  is_staff: boolean
  /**
   * Platform-superuser flag. With `is_staff`, this is the Root tier
   * (docs/operator-control-plane-spec.md §E) — the two together, never
   * `is_superuser` alone.
   */
  is_superuser: boolean
}

export interface CurrentUserState {
  /** The resolved email, or null while unresolved / on error. */
  email: string | null
  /** Still waiting on `/me/` and the login session gave us nothing. */
  resolving: boolean
  /**
   * Whether the signed-in user is platform staff. Defaults to `false` until
   * `/users/me/` resolves (and on error) — the safe default, since the real
   * boundary is `IsPlatformStaff` server-side, never this flag.
   */
  isStaff: boolean
  /**
   * Whether the signed-in user is a Root operator: `is_staff AND
   * is_superuser`, the same predicate IsPlatformRoot checks server-side.
   * Defaults to `false` until `/users/me/` resolves and on error — the safe
   * default, since the real boundary is IsPlatformRoot, never this flag.
   * Used only to decide whether Root-only controls RENDER; every one of them
   * is refused server-side for a non-Root caller regardless.
   */
  isRoot: boolean
  /**
   * Whether `is_staff` is still unknown because `/users/me/` hasn't settled.
   * Deliberately NOT `resolving`: that field has an `AuthProvider.userEmail`
   * fast path and can be `false` while `is_staff` (from the same still-pending
   * query) is genuinely unknown — gating a redirect on `resolving` would flash
   * a false "access denied" for a staff member who just logged in.
   */
  isStaffResolving: boolean
}

export function useCurrentUser(): CurrentUserState {
  const { userEmail } = useAuth()

  const { data, isPending, isError } = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: () => apiClient.get<CurrentUser>('/users/me/'),
  })

  const email = userEmail ?? data?.email ?? null
  const resolving = email === null && isPending && !isError

  return {
    email,
    resolving,
    isStaff: data?.is_staff ?? false,
    isRoot: Boolean(data?.is_staff && data?.is_superuser),
    isStaffResolving: isPending && !isError,
  }
}
