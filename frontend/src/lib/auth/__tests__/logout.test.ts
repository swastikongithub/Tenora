import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../../../test/msw/server'
import { apiUrl } from '../../../test/fixtures'
import { clearTokens, setTokens } from '../token-store'
import { logoutOnce } from '../logout'

beforeEach(() => clearTokens())

describe('logoutOnce — §4.6 best-effort server-side logout', () => {
  it('POSTs the refresh token, with the bearer access token, to /api/auth/logout/', async () => {
    let seen: { auth: string | null; body: unknown } | null = null
    server.use(
      http.post(apiUrl('/auth/logout/'), async ({ request }) => {
        seen = {
          auth: request.headers.get('Authorization'),
          body: await request.json(),
        }
        return new HttpResponse(null, { status: 200 })
      }),
    )

    setTokens('access-xyz', 'refresh-abc')
    logoutOnce()

    await vi.waitFor(() => expect(seen).not.toBeNull())
    expect(seen!.body).toEqual({ refresh: 'refresh-abc' })
    expect(seen!.auth).toBe('Bearer access-xyz')
  })

  it('is a no-op when there is no refresh token', async () => {
    let called = false
    server.use(
      http.post(apiUrl('/auth/logout/'), () => {
        called = true
        return new HttpResponse(null, { status: 200 })
      }),
    )

    clearTokens()
    logoutOnce()

    await new Promise((r) => setTimeout(r, 20))
    expect(called).toBe(false)
  })

  it('swallows a network failure — logout must not block on it', async () => {
    server.use(http.post(apiUrl('/auth/logout/'), () => HttpResponse.error()))

    setTokens('a', 'r')
    expect(() => logoutOnce()).not.toThrow()
    await new Promise((r) => setTimeout(r, 20))
  })
})
