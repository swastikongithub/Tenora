import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../../test/msw/server'
import { apiClient } from '../api-client'
import { ApiError } from '../api-error'
import { onSessionEnded } from '../auth/session'
import {
  clearTokens,
  getRefreshToken,
  setAccessToken,
  setTokens,
} from '../auth/token-store'
import { setCurrentTenantId } from '../tenant/current-tenant'

const api = (path: string) => `*/api${path}`

beforeEach(() => {
  clearTokens()
  setCurrentTenantId(null)
})

describe('Authorization header', () => {
  it('attaches Bearer <access> to a tenant-scoped request', async () => {
    setAccessToken('access-123')
    setCurrentTenantId('tenant-1')
    let seen: string | null = null
    server.use(
      http.get(api('/memberships/'), ({ request }) => {
        seen = request.headers.get('authorization')
        return HttpResponse.json([])
      }),
    )

    await apiClient.get('/memberships/')
    expect(seen).toBe('Bearer access-123')
  })

  it('attaches Bearer <access> to a global-but-authenticated path (/tenants/me/)', async () => {
    setAccessToken('access-123')
    let auth: string | null = null
    let tenant: string | null = null
    server.use(
      http.get(api('/tenants/me/'), ({ request }) => {
        auth = request.headers.get('authorization')
        tenant = request.headers.get('x-tenant-id')
        return HttpResponse.json([])
      }),
    )

    await apiClient.get('/tenants/me/')
    expect(auth).toBe('Bearer access-123')
    expect(tenant).toBeNull()
  })

  it('never attaches Authorization to login or register', async () => {
    setAccessToken('should-not-be-sent')
    const seen: Record<string, string | null> = {}
    server.use(
      http.post(api('/auth/login/'), ({ request }) => {
        seen.login = request.headers.get('authorization')
        return HttpResponse.json({ access: 'a', refresh: 'r' })
      }),
      http.post(api('/auth/register/'), ({ request }) => {
        seen.register = request.headers.get('authorization')
        return HttpResponse.json({ id: '1', email: 'a@b.c' }, { status: 201 })
      }),
    )

    await apiClient.post('/auth/login/', { email: 'a@b.c', password: 'pw' })
    await apiClient.post('/auth/register/', { email: 'a@b.c', password: 'pw' })
    expect(seen.login).toBeNull()
    expect(seen.register).toBeNull()
  })
})

describe('X-Tenant-ID header — exact GLOBAL_PATHS match', () => {
  it('attaches the current tenant id to a tenant-scoped path', async () => {
    setCurrentTenantId('tenant-abc')
    let seen: string | null = null
    server.use(
      http.get(api('/memberships/'), ({ request }) => {
        seen = request.headers.get('x-tenant-id')
        return HttpResponse.json([])
      }),
    )

    await apiClient.get('/memberships/')
    expect(seen).toBe('tenant-abc')
  })

  it('omits it from every GLOBAL_PATH', async () => {
    setAccessToken('a')
    setCurrentTenantId('tenant-abc')
    const seen: Record<string, string | null> = {}
    server.use(
      http.get(api('/tenants/me/'), ({ request }) => {
        seen.me = request.headers.get('x-tenant-id')
        return HttpResponse.json([])
      }),
      http.get(api('/plans/'), ({ request }) => {
        seen.plans = request.headers.get('x-tenant-id')
        return HttpResponse.json([])
      }),
    )

    await apiClient.get('/tenants/me/')
    await apiClient.get('/plans/')
    expect(seen.me).toBeNull()
    expect(seen.plans).toBeNull()
  })

  it('treats GLOBAL_PATHS as exact, not prefix: /plans/ is exempt, /plans/archived/ is not', async () => {
    setAccessToken('a')
    setCurrentTenantId('tenant-abc')
    const seen: Record<string, string | null> = {}
    server.use(
      http.get(api('/plans/'), ({ request }) => {
        seen.plans = request.headers.get('x-tenant-id')
        return HttpResponse.json([])
      }),
      http.get(api('/plans/archived/'), ({ request }) => {
        seen.archived = request.headers.get('x-tenant-id')
        return HttpResponse.json([])
      }),
    )

    await apiClient.get('/plans/')
    await apiClient.get('/plans/archived/')
    expect(seen.plans).toBeNull()
    expect(seen.archived).toBe('tenant-abc')
  })

  it('omits the header when no tenant is selected', async () => {
    setAccessToken('a')
    let seen: string | null = 'unset'
    server.use(
      http.get(api('/memberships/'), ({ request }) => {
        seen = request.headers.get('x-tenant-id')
        return HttpResponse.json([])
      }),
    )

    await apiClient.get('/memberships/')
    expect(seen).toBeNull()
  })

  it('matches GLOBAL_PATHS against the path only, ignoring a query string (Operator Control Plane Phase 1 detail lookups: ?id=...)', async () => {
    // docs/operator-control-plane-spec.md — platform detail endpoints are a
    // static path with the id in the query string (GLOBAL_PATHS is an
    // exact-match frozenset that can't represent a dynamic segment). This is
    // the first-ever query-string-bearing request in this app; without
    // stripping "?..." before the GLOBAL_PATHS/NO_AUTH_PATHS check, this
    // would incorrectly attach X-Tenant-ID to a global path.
    setAccessToken('a')
    setCurrentTenantId('tenant-abc')
    let seen: string | null = 'unset'
    server.use(
      http.get(api('/platform/plans/detail/'), ({ request }) => {
        seen = request.headers.get('x-tenant-id')
        return HttpResponse.json({ id: 'plan-1' })
      }),
    )

    await apiClient.get('/platform/plans/detail/?id=plan-1')
    expect(seen).toBeNull()
  })
})

describe('tenant id is never sent in a request body', () => {
  it('rejects a body carrying tenant_id / tenant / tenantId', async () => {
    setAccessToken('a')
    setCurrentTenantId('tenant-1')
    await expect(
      apiClient.post('/memberships/', { email: 'x@y.z', tenant_id: 'forged' }),
    ).rejects.toThrow(/tenant_id/)
    await expect(
      apiClient.post('/memberships/', { email: 'x@y.z', tenant: 'forged' }),
    ).rejects.toThrow(/tenant/)
  })

  it('sends a clean body verbatim with no tenant field injected', async () => {
    setAccessToken('a')
    setCurrentTenantId('tenant-1')
    let body: unknown
    server.use(
      http.post(api('/memberships/'), async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'm1' }, { status: 201 })
      }),
    )

    await apiClient.post('/memberships/', { email: 'x@y.z' })
    expect(body).toEqual({ email: 'x@y.z' })
    expect(body).not.toHaveProperty('tenant_id')
    expect(body).not.toHaveProperty('tenant')
  })
})

describe('401 handling — one refresh, one retry, no loop', () => {
  it('refreshes once and retries the original request once with the new token', async () => {
    setTokens('old-access', 'refresh-1')
    setCurrentTenantId('tenant-1')
    let membershipCalls = 0
    let refreshCalls = 0
    server.use(
      http.get(api('/memberships/'), ({ request }) => {
        membershipCalls += 1
        if (membershipCalls === 1)
          return new HttpResponse(null, { status: 401 })
        expect(request.headers.get('authorization')).toBe('Bearer new-access')
        return HttpResponse.json([{ id: 'm1' }])
      }),
      http.post(api('/auth/refresh/'), () => {
        refreshCalls += 1
        return HttpResponse.json({ access: 'new-access', refresh: 'refresh-2' })
      }),
    )

    const result = await apiClient.get('/memberships/')
    expect(result).toEqual([{ id: 'm1' }])
    expect(membershipCalls).toBe(2)
    expect(refreshCalls).toBe(1)
    expect(getRefreshToken()).toBe('refresh-2') // rotation persisted
  })

  it('ends the session on a second 401 and does not loop', async () => {
    setTokens('old-access', 'refresh-1')
    setCurrentTenantId('tenant-1')
    let membershipCalls = 0
    let refreshCalls = 0
    const ended = vi.fn()
    const unsub = onSessionEnded(ended)
    server.use(
      http.get(api('/memberships/'), () => {
        membershipCalls += 1
        return new HttpResponse(null, { status: 401 })
      }),
      http.post(api('/auth/refresh/'), () => {
        refreshCalls += 1
        return HttpResponse.json({ access: 'new-access', refresh: 'refresh-2' })
      }),
    )

    await expect(apiClient.get('/memberships/')).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(membershipCalls).toBe(2) // original + exactly one retry
    expect(refreshCalls).toBe(1) // exactly one refresh
    expect(ended).toHaveBeenCalledTimes(1)
    expect(getRefreshToken()).toBeNull()
    unsub()
  })

  it('ends the session without retrying when the refresh itself fails', async () => {
    setTokens('old-access', 'refresh-1')
    setCurrentTenantId('tenant-1')
    let membershipCalls = 0
    const ended = vi.fn()
    const unsub = onSessionEnded(ended)
    server.use(
      http.get(api('/memberships/'), () => {
        membershipCalls += 1
        return new HttpResponse(null, { status: 401 })
      }),
      http.post(
        api('/auth/refresh/'),
        () => new HttpResponse(null, { status: 401 }),
      ),
    )

    await expect(apiClient.get('/memberships/')).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(membershipCalls).toBe(1) // no retry — refresh never succeeded
    expect(ended).toHaveBeenCalledTimes(1)
    expect(getRefreshToken()).toBeNull()
    unsub()
  })

  it('does not attempt a refresh when login itself returns 401', async () => {
    let refreshCalls = 0
    server.use(
      http.post(api('/auth/login/'), () =>
        HttpResponse.json(
          { detail: 'No active account found with the given credentials' },
          { status: 401 },
        ),
      ),
      http.post(api('/auth/refresh/'), () => {
        refreshCalls += 1
        return HttpResponse.json({ access: 'x', refresh: 'y' })
      }),
    )

    await expect(
      apiClient.post('/auth/login/', { email: 'a@b.c', password: 'pw' }),
    ).rejects.toMatchObject({ status: 401 })
    expect(refreshCalls).toBe(0)
  })
})

describe('error normalization', () => {
  it('turns a DRF field-error body into ApiError.fieldErrors', async () => {
    setAccessToken('a')
    setCurrentTenantId('tenant-1')
    server.use(
      http.post(api('/memberships/'), () =>
        HttpResponse.json(
          { email: ['This user is already a member of this tenant.'] },
          { status: 400 },
        ),
      ),
    )

    const err = await apiClient
      .post('/memberships/', { email: 'x@y.z' })
      .catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(400)
    expect((err as ApiError).fieldErrors.email).toEqual([
      'This user is already a member of this tenant.',
    ])
  })

  it('turns a transport failure into a status-0 ApiError', async () => {
    setAccessToken('a')
    server.use(http.get(api('/plans/'), () => HttpResponse.error()))

    const err = await apiClient.get('/plans/').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(0)
  })

  it('returns parsed JSON on success and undefined on 204', async () => {
    setAccessToken('a')
    setCurrentTenantId('tenant-1')
    server.use(
      http.get(api('/memberships/'), () => HttpResponse.json([{ id: 'm1' }])),
      http.delete(
        api('/memberships/'),
        () => new HttpResponse(null, { status: 204 }),
      ),
    )

    expect(await apiClient.get('/memberships/')).toEqual([{ id: 'm1' }])
    expect(await apiClient.delete('/memberships/')).toBeUndefined()
  })
})
