/**
 * Property-billing data hooks. Every workspace-owned read is keyed under the
 * active tenant id (query-keys.ts `property(...)`), so switching workspace in
 * the switcher changes every key at once — dashboards, bills, payments and
 * receipts can never show the previous workspace's rows.
 *
 * Roles here decide what RENDERS only. The backend's capability checks and
 * resident-scoped querysets are the real boundary.
 */

import { useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query'
import { useCallback } from 'react'

import { apiClient } from '../api-client'
import { queryKeys } from '../query-keys'
import { useTenant } from '../tenant'

export function useWorkspaceRole() {
  const { currentTenant, currentTenantId } = useTenant()
  const role = currentTenant?.role ?? null
  return {
    tenantId: currentTenantId,
    tenantName: currentTenant?.name ?? '',
    role,
    isOwner: role === 'OWNER',
    isResident: role === 'MEMBER',
  }
}

export function toQueryString(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, value)
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** GET a tenant-scoped property endpoint under a tenant-keyed cache entry. */
export function usePropertyQuery<T>(
  resource: string,
  path: string,
  params: Record<string, string | undefined> = {},
  options: Partial<UseQueryOptions<T>> = {},
) {
  const { currentTenantId } = useTenant()
  return useQuery<T>({
    queryKey: queryKeys.property(currentTenantId ?? '∅', resource, { path, ...params }),
    queryFn: () => apiClient.get<T>(`${path}${toQueryString(params)}`),
    enabled: Boolean(currentTenantId) && (options.enabled ?? true),
    ...options,
  } as UseQueryOptions<T>)
}

/** Invalidate every property-billing query of the active workspace after a mutation. */
export function useInvalidateProperty() {
  const queryClient = useQueryClient()
  const { currentTenantId } = useTenant()
  return useCallback(() => {
    if (!currentTenantId) return Promise.resolve()
    return queryClient.invalidateQueries({ queryKey: queryKeys.propertyRoot(currentTenantId) })
  }, [queryClient, currentTenantId])
}
