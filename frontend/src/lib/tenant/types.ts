export type TenantRole = 'OWNER' | 'MEMBER'

/**
 * One row of `GET /api/tenants/me/` — a tenant plus the current user's role in
 * it. The backend flattens `role` onto the serialized `Tenant`
 * (`apps/tenants/views.py` `MyTenantsView`).
 */
export interface TenantMembership {
  id: string
  name: string
  slug: string
  created_at: string
  is_active: boolean
  role: TenantRole
}

export type TenantStatus = 'loading' | 'ready' | 'empty' | 'error'
