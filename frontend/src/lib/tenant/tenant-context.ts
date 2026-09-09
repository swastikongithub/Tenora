/**
 * The tenant context object and its hook, kept separate from the provider
 * component (TenantProvider.tsx) — same split as the auth layer, for the
 * `react-refresh/only-export-components` lint rule.
 */

import { createContext, useContext } from 'react'

import type { TenantMembership, TenantStatus } from './types'

export interface TenantContextValue {
  /** Every tenant the user belongs to (from `/api/tenants/me/`). */
  tenants: TenantMembership[]
  /** The active tenant, or `null` while loading / when the user has none. */
  currentTenant: TenantMembership | null
  /** The active tenant id — the value sent as `X-Tenant-ID`. */
  currentTenantId: string | null
  status: TenantStatus
  /**
   * Make `tenantId` the active tenant. No-op if it isn't one of `tenants`
   * (a stale id from storage, say). Isolation of cached data across the switch
   * is handled by the query keys (spec §4.3), not by this call.
   */
  switchTenant: (tenantId: string) => void
  /** Retry the `/api/tenants/me/` fetch after an error. */
  refetch: () => void
}

export const TenantContext = createContext<TenantContextValue | null>(null)

export function useTenant(): TenantContextValue {
  const value = useContext(TenantContext)
  if (!value) {
    throw new Error('useTenant must be used within a <TenantProvider>')
  }
  return value
}
