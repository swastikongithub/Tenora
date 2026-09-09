/**
 * Resolves and holds the active tenant. Mounted only inside `ProtectedRoute`,
 * i.e. only when auth status is `authenticated`.
 *
 * Stage C2 spec §4.3:
 *   - The tenant list comes from `/api/tenants/me/` under a GLOBAL cache key
 *     (`['global', 'tenants', 'me']`) — it is not per-tenant data.
 *   - The active tenant id is written to `current-tenant.ts` (the value the API
 *     client sends as `X-Tenant-ID`) and mirrored to `localStorage` purely as a
 *     "resume where you left off" convenience. It is NEVER treated as
 *     authorization: the server re-resolves `Membership` from the JWT + header
 *     on every request regardless (UI spec §C.6.3).
 *   - Isolation of cached data across a switch is a property of the query keys
 *     (see query-keys.ts), not of this component clearing anything.
 */

import { useQuery } from '@tanstack/react-query'
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { apiClient } from '../api-client'
import { queryKeys } from '../query-keys'
import {
  getCurrentTenantId,
  LAST_TENANT_STORAGE_KEY,
  setCurrentTenantId,
} from './current-tenant'
import { TenantContext, type TenantContextValue } from './tenant-context'
import type { TenantMembership, TenantStatus } from './types'

function readStoredTenantId(): string | null {
  try {
    return localStorage.getItem(LAST_TENANT_STORAGE_KEY)
  } catch {
    return null
  }
}

function persistTenantId(tenantId: string): void {
  try {
    localStorage.setItem(LAST_TENANT_STORAGE_KEY, tenantId)
  } catch {
    /* storage unavailable — the selection just won't persist across reloads */
  }
}

export function TenantProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: queryKeys.tenantsMe(),
    queryFn: () => apiClient.get<TenantMembership[]>('/tenants/me/'),
  })

  const tenants = useMemo(() => query.data ?? [], [query.data])

  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Pick the active tenant once the list arrives, and re-pick if the current
  // selection is no longer in the list (e.g. the user was removed from it).
  useEffect(() => {
    const list = query.data
    if (!list) return
    setSelectedId((current) => {
      if (current && list.some((t) => t.id === current)) return current
      const stored = readStoredTenantId()
      // A stored id that isn't in the list is ignored, not an error
      // (spec §9: removed from your last-selected workspace between sessions).
      if (stored && list.some((t) => t.id === stored)) return stored
      return list[0]?.id ?? null
    })
  }, [query.data])

  // Keep the API client's `X-Tenant-ID` accessor in lockstep with the selection.
  // This is done DURING RENDER, not in an effect: `current-tenant.ts` is an
  // external (non-React) store, this write is idempotent, and a child component
  // that mounts on the same render as the selection (e.g. MembersPage's
  // tenant-scoped query) must see the header before its first fetch — a parent
  // effect runs after child effects, which is too late.
  if (getCurrentTenantId() !== selectedId) {
    setCurrentTenantId(selectedId)
  }

  // The localStorage hint is a resume-where-you-left-off convenience nobody
  // reads synchronously, so an effect is the right place for it.
  useEffect(() => {
    if (selectedId) persistTenantId(selectedId)
  }, [selectedId])

  const switchTenant = useCallback(
    (tenantId: string) => {
      setSelectedId((current) =>
        tenants.some((t) => t.id === tenantId) ? tenantId : current,
      )
    },
    [tenants],
  )

  const refetch = useCallback(() => {
    void query.refetch()
  }, [query])

  const status: TenantStatus = query.isLoading
    ? 'loading'
    : query.isError
      ? 'error'
      : tenants.length === 0
        ? 'empty'
        : 'ready'

  const value: TenantContextValue = {
    tenants,
    currentTenant: tenants.find((t) => t.id === selectedId) ?? null,
    currentTenantId: selectedId,
    status,
    switchTenant,
    refetch,
  }

  return (
    <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
  )
}
