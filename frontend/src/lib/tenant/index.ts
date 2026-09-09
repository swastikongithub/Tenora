// Public surface of the tenant layer.

export { TenantProvider } from './TenantProvider'
export { useTenant } from './tenant-context'
export type { TenantContextValue } from './tenant-context'
export type { TenantMembership, TenantRole, TenantStatus } from './types'
export { getCurrentTenantId, setCurrentTenantId } from './current-tenant'
