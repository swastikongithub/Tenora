import { describe, expect, it } from 'vitest'

import { GLOBAL_KEY_ROOT, TENANT_KEY_ROOT, queryKeys } from '../query-keys'

describe('query keys — the §4.3 structural isolation mechanism', () => {
  it('namespaces tenant-scoped keys with the tenant id as an explicit segment', () => {
    expect(queryKeys.members('t-1')).toEqual([
      TENANT_KEY_ROOT,
      't-1',
      'members',
    ])
    expect(queryKeys.currentSubscription('t-1')).toEqual([
      TENANT_KEY_ROOT,
      't-1',
      'subscription',
      'current',
    ])
  })

  it('gives a different key per tenant, so one tenant cannot read another cache entry', () => {
    expect(queryKeys.members('t-1')).not.toEqual(queryKeys.members('t-2'))
  })

  it('keeps global data OUT of the tenant namespace', () => {
    expect(queryKeys.currentUser()[0]).toBe(GLOBAL_KEY_ROOT)
    expect(queryKeys.tenantsMe()[0]).toBe(GLOBAL_KEY_ROOT)
    expect(queryKeys.plans()[0]).toBe(GLOBAL_KEY_ROOT)
    expect(queryKeys.platformTenants()[0]).toBe(GLOBAL_KEY_ROOT)
    expect(queryKeys.platformStats()[0]).toBe(GLOBAL_KEY_ROOT)
    expect(queryKeys.tenantsMe()).not.toContain(TENANT_KEY_ROOT)
    expect(queryKeys.currentUser()).not.toContain(TENANT_KEY_ROOT)
    expect(queryKeys.platformTenants()).not.toContain(TENANT_KEY_ROOT)
  })
})
