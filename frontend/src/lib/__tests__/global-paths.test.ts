import { describe, expect, it } from 'vitest'

import {
  GLOBAL_PATHS,
  NO_AUTH_PATHS,
  isGlobalPath,
  isNoAuthPath,
} from '../global-paths'

describe('GLOBAL_PATHS — frontend mirror of the backend set', () => {
  it('is byte-identical to apps/tenants/authentication.py GLOBAL_PATHS', () => {
    expect([...GLOBAL_PATHS].sort()).toEqual([
      '/api/auth/google/',
      '/api/auth/login/',
      '/api/auth/logout/',
      '/api/auth/refresh/',
      '/api/auth/register/',
      '/api/auth/resend-verification/',
      '/api/auth/verify-email/',
      '/api/plans/',
      '/api/platform/audit-log/',
      '/api/platform/health/',
      '/api/platform/plans/',
      '/api/platform/plans/detail/',
      '/api/platform/reconciliation-discrepancies/',
      '/api/platform/reconciliation/run/',
      '/api/platform/stats/',
      '/api/platform/subscriptions/detail/',
      '/api/platform/tenants/',
      '/api/platform/tenants/detail/',
      '/api/platform/usage/run/',
      '/api/platform/users/',
      '/api/platform/users/detail/',
      '/api/platform/webhook-events/',
      '/api/platform/webhook-events/detail/',
      '/api/platform/webhook-events/process-pending/',
      '/api/tenants/',
      '/api/tenants/me/',
      '/api/users/me/',
    ])
  })

  it('matches exactly — never by prefix', () => {
    expect(isGlobalPath('/api/plans/')).toBe(true)
    expect(isGlobalPath('/api/tenants/')).toBe(true)
    expect(isGlobalPath('/api/tenants/me/')).toBe(true)
    expect(isGlobalPath('/api/platform/tenants/')).toBe(true)
    expect(isGlobalPath('/api/platform/stats/')).toBe(true)
    // Operator Control Plane Phase 1 (docs/operator-control-plane-spec.md) —
    // detail endpoints are a static `.../detail/` path, not `<uuid:pk>`.
    expect(isGlobalPath('/api/platform/plans/detail/')).toBe(true)
    expect(isGlobalPath('/api/platform/webhook-events/detail/')).toBe(true)
    // Operator Control Plane Phase 2 (docs/operator-control-plane-spec.md) —
    // the first mutations, same static-path convention.
    expect(isGlobalPath('/api/platform/subscriptions/detail/')).toBe(true)
    expect(isGlobalPath('/api/platform/webhook-events/process-pending/')).toBe(true)
    expect(isGlobalPath('/api/platform/reconciliation/run/')).toBe(true)
    expect(isGlobalPath('/api/platform/usage/run/')).toBe(true)
    expect(isGlobalPath('/api/platform/audit-log/')).toBe(true)

    // A prefix test would wrongly exempt these — the exact reason the backend
    // set is exact-match (CLAUDE.md).
    expect(isGlobalPath('/api/plans/archived/')).toBe(false)
    expect(isGlobalPath('/api/tenants/me/settings/')).toBe(false)
    expect(isGlobalPath('/api/tenants/me')).toBe(false) // trailing slash matters
    expect(isGlobalPath('/api/memberships/')).toBe(false)
    expect(isGlobalPath('/api/subscriptions/current/')).toBe(false)
    // A dynamic id segment, never accepted — only the literal `.../detail/`
    // static path is exempt.
    expect(isGlobalPath('/api/platform/plans/some-uuid/')).toBe(false)
  })
})

describe('NO_AUTH_PATHS', () => {
  it('is a strict subset of GLOBAL_PATHS', () => {
    for (const path of NO_AUTH_PATHS) {
      expect(GLOBAL_PATHS.has(path)).toBe(true)
    }
    expect(NO_AUTH_PATHS.size).toBeLessThan(GLOBAL_PATHS.size)
  })

  it('excludes the globals that are still authenticated', () => {
    expect(isNoAuthPath('/api/auth/login/')).toBe(true)
    expect(isNoAuthPath('/api/auth/refresh/')).toBe(true)
    expect(isNoAuthPath('/api/auth/register/')).toBe(true)
    expect(isNoAuthPath('/api/auth/verify-email/')).toBe(true)
    expect(isNoAuthPath('/api/auth/resend-verification/')).toBe(true)
    expect(isNoAuthPath('/api/auth/google/')).toBe(true)
    expect(isNoAuthPath('/api/auth/logout/')).toBe(false) // needs the Bearer token
    expect(isNoAuthPath('/api/users/me/')).toBe(false)
    expect(isNoAuthPath('/api/tenants/me/')).toBe(false)
    expect(isNoAuthPath('/api/plans/')).toBe(false)
    expect(isNoAuthPath('/api/tenants/')).toBe(false)
    expect(isNoAuthPath('/api/platform/tenants/')).toBe(false) // staff Bearer token
    expect(isNoAuthPath('/api/platform/stats/')).toBe(false)
  })
})
