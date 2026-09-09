import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setTokens,
} from '../token-store'

beforeEach(() => clearTokens())

describe('token store', () => {
  it('keeps the access token in memory only — never in web storage', () => {
    setAccessToken('access-secret-value')
    expect(getAccessToken()).toBe('access-secret-value')

    for (const store of [sessionStorage, localStorage]) {
      for (let i = 0; i < store.length; i += 1) {
        const key = store.key(i) as string
        expect(store.getItem(key)).not.toContain('access-secret-value')
      }
    }
  })

  it('persists the refresh token in sessionStorage, not localStorage', () => {
    setTokens('access', 'refresh-secret-value')
    expect(getRefreshToken()).toBe('refresh-secret-value')
    expect(sessionStorage.getItem('billing.refresh_token')).toBe(
      'refresh-secret-value',
    )
    expect(localStorage.getItem('billing.refresh_token')).toBeNull()
  })

  it('clearTokens wipes both the in-memory access token and the stored refresh token', () => {
    setTokens('access', 'refresh')
    clearTokens()
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(sessionStorage.getItem('billing.refresh_token')).toBeNull()
  })
})
