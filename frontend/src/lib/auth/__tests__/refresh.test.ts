import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import { refreshOnce } from '../refresh'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from '../token-store'

const api = (path: string) => `*/api${path}`

beforeEach(() => clearTokens())

describe('refreshOnce', () => {
  it('stores the new access token and the rotated refresh token', async () => {
    setTokens('old-access', 'old-refresh')
    server.use(
      http.post(api('/auth/refresh/'), async ({ request }) => {
        expect(await request.json()).toEqual({ refresh: 'old-refresh' })
        return HttpResponse.json({
          access: 'fresh-access',
          refresh: 'fresh-refresh',
        })
      }),
    )

    expect(await refreshOnce()).toBe(true)
    expect(getAccessToken()).toBe('fresh-access')
    expect(getRefreshToken()).toBe('fresh-refresh')
  })

  it('coalesces concurrent callers into a single network round trip', async () => {
    setTokens('old-access', 'old-refresh')
    let calls = 0
    server.use(
      http.post(api('/auth/refresh/'), () => {
        calls += 1
        return HttpResponse.json({
          access: 'fresh-access',
          refresh: 'fresh-refresh',
        })
      }),
    )

    const results = await Promise.all([
      refreshOnce(),
      refreshOnce(),
      refreshOnce(),
    ])
    expect(results).toEqual([true, true, true])
    expect(calls).toBe(1)
  })

  it('clears tokens and resolves false when the server rejects the refresh', async () => {
    setTokens('old-access', 'old-refresh')
    server.use(
      http.post(
        api('/auth/refresh/'),
        () => new HttpResponse(null, { status: 401 }),
      ),
    )

    expect(await refreshOnce()).toBe(false)
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it('does not touch the network when there is no refresh token', async () => {
    let calls = 0
    server.use(
      http.post(api('/auth/refresh/'), () => {
        calls += 1
        return HttpResponse.json({ access: 'x' })
      }),
    )

    expect(await refreshOnce()).toBe(false)
    expect(calls).toBe(0)
  })
})
