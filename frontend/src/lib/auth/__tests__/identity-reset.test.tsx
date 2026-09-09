/**
 * Identity-lifecycle reset (diagnosis: "stale X-Tenant-ID after no-reload
 * logout -> login").
 *
 * Bug: after logout then login / Google login WITHOUT a full page reload, the
 * previous user's React Query cache (`['global', 'tenants', 'me']`) and the
 * `billing.last_tenant_id` hint survived. `TenantProvider` then re-selected the
 * previous user's tenant, so the first tenant-scoped request shipped that
 * user's `X-Tenant-ID` and the backend correctly answered 403 (`not_a_member`).
 *
 * Fix: `AuthProvider` clears the query cache + tenant holder + stored tenant
 * hint on session end AND on every successful login.
 *
 * These tests drive the real AuthProvider + TenantProvider against the SINGLETON
 * queryClient (the one AuthProvider clears, and the one App.tsx provides), with
 * a tenant-scoped query mounted so the actual `X-Tenant-ID` sent is observable.
 */

import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import { TENANT_A, TENANT_B, apiUrl } from '../../../test/fixtures'
import { apiClient } from '../../api-client'
import { queryClient } from '../../query-client'
import { queryKeys } from '../../query-keys'
import {
  LAST_TENANT_STORAGE_KEY,
  getCurrentTenantId,
  setCurrentTenantId,
} from '../../tenant/current-tenant'
import { TenantProvider } from '../../tenant/TenantProvider'
import { useTenant } from '../../tenant/tenant-context'
import { AuthProvider } from '../AuthProvider'
import { useAuth } from '../auth-context'
import { endSession } from '../session'
import { clearTokens } from '../token-store'

beforeEach(() => {
  clearTokens()
  setCurrentTenantId(null)
  queryClient.clear()
})

afterEach(() => {
  queryClient.clear()
})

/** Reads one tenant-scoped endpoint and surfaces the `X-Tenant-ID` it reached
 *  the server with — the exact thing the bug got wrong. */
function SubscriptionEcho() {
  const { currentTenantId } = useTenant()
  const query = useQuery({
    queryKey: queryKeys.currentSubscription(currentTenantId ?? '∅'),
    queryFn: () =>
      apiClient.get<{ tenant_echo: string }>('/subscriptions/current/'),
    enabled: currentTenantId != null,
  })
  return (
    <output data-testid="sub-tenant">
      {query.data ? query.data.tenant_echo : 'pending'}
    </output>
  )
}

function Harness() {
  const { status, login, loginWithGoogle, logout } = useAuth()
  return (
    <div>
      <output data-testid="status">{status}</output>
      <button onClick={() => void login('a@user.test', 'pw').catch(() => {})}>
        login A
      </button>
      <button onClick={() => void loginWithGoogle('google-cred-B').catch(() => {})}>
        google login B
      </button>
      <button onClick={logout}>logout</button>
      {status === 'authenticated' && (
        <TenantProvider>
          <SubscriptionEcho />
        </TenantProvider>
      )}
    </div>
  )
}

function renderApp() {
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Harness />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

/** `/tenants/me/` answers by which user's access token is presented; the
 *  subscription endpoint echoes the tenant header it saw. */
function useIdentityHandlers() {
  server.use(
    http.post(apiUrl('/auth/login/'), () =>
      HttpResponse.json({ access: 'A-access', refresh: 'A-refresh' }),
    ),
    http.post(apiUrl('/auth/google/'), () =>
      HttpResponse.json({ access: 'B-access', refresh: 'B-refresh' }),
    ),
    http.post(apiUrl('/auth/logout/'), () => new HttpResponse(null, { status: 200 })),
    http.get(apiUrl('/tenants/me/'), ({ request }) => {
      const auth = request.headers.get('Authorization') ?? ''
      return HttpResponse.json(auth.includes('A-access') ? [TENANT_A] : [TENANT_B])
    }),
    http.get(apiUrl('/subscriptions/current/'), ({ request }) =>
      HttpResponse.json({
        tenant_echo: request.headers.get('X-Tenant-ID') ?? 'none',
      }),
    ),
  )
}

describe('AuthProvider — identity state reset', () => {
  it('a logout then Google login does not reuse the previous user’s tenant state', async () => {
    useIdentityHandlers()
    renderApp()
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )

    // --- User A signs in: tenant A resolves, its scoped request uses tenant A.
    await userEvent.click(screen.getByRole('button', { name: 'login A' }))
    await waitFor(() =>
      expect(screen.getByTestId('sub-tenant')).toHaveTextContent(TENANT_A.id),
    )
    await waitFor(() =>
      expect(localStorage.getItem(LAST_TENANT_STORAGE_KEY)).toBe(TENANT_A.id),
    )
    expect(queryClient.getQueryData(queryKeys.tenantsMe())).toEqual([TENANT_A])

    // --- User A logs out (no page reload): identity state is wiped.
    await userEvent.click(screen.getByRole('button', { name: 'logout' }))
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )
    expect(queryClient.getQueryData(queryKeys.tenantsMe())).toBeUndefined()
    expect(localStorage.getItem(LAST_TENANT_STORAGE_KEY)).toBeNull()
    expect(getCurrentTenantId()).toBeNull()

    // --- User B signs in with Google: must resolve to B's tenant, not A's.
    await userEvent.click(screen.getByRole('button', { name: 'google login B' }))
    await waitFor(() =>
      expect(screen.getByTestId('sub-tenant')).toHaveTextContent(TENANT_B.id),
    )
    // The first tenant-scoped request after B logs in used B's tenant.
    expect(screen.getByTestId('sub-tenant')).not.toHaveTextContent(TENANT_A.id)
    // The cached tenant list is B's only — A's is gone, not merely shadowed.
    expect(queryClient.getQueryData(queryKeys.tenantsMe())).toEqual([TENANT_B])
    // The persisted hint was cleared and then re-written for B, never left on A.
    expect(localStorage.getItem(LAST_TENANT_STORAGE_KEY)).toBe(TENANT_B.id)
    expect(getCurrentTenantId()).toBe(TENANT_B.id)
  })

  it('a session end (e.g. from the API client) clears cache, tenant holder, and the stored hint', async () => {
    useIdentityHandlers()
    renderApp()
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )

    await userEvent.click(screen.getByRole('button', { name: 'login A' }))
    await waitFor(() =>
      expect(screen.getByTestId('sub-tenant')).toHaveTextContent(TENANT_A.id),
    )
    await waitFor(() =>
      expect(localStorage.getItem(LAST_TENANT_STORAGE_KEY)).toBe(TENANT_A.id),
    )
    expect(queryClient.getQueryData(queryKeys.tenantsMe())).toEqual([TENANT_A])

    // The API client ends the session from inside a failed request; test it via
    // the same signal it fires.
    await act(async () => {
      endSession()
    })

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )
    expect(queryClient.getQueryData(queryKeys.tenantsMe())).toBeUndefined()
    expect(localStorage.getItem(LAST_TENANT_STORAGE_KEY)).toBeNull()
    expect(getCurrentTenantId()).toBeNull()
  })
})
