/**
 * Every server-state cache key in the app is built here. This is the structural
 * half of the tenant-isolation guarantee (Stage C2 spec §4.3):
 *
 *   - Tenant-scoped keys carry the tenant id as an explicit segment —
 *     `['tenant', tenantId, 'members']`, never a bare `['members']` that holds
 *     whatever tenant was fetched last. This mirrors the backend's
 *     `TenantScopedManager.for_tenant(tenant)` taking `tenant` as an explicit
 *     argument rather than reading it from ambient state.
 *
 *   - When the active tenant changes, the key changes, so the previous
 *     tenant's cached data becomes a different, inactive cache entry. There is
 *     no code path by which it can render under the new tenant — isolation is a
 *     property of the key shape, not of remembering to call an invalidate.
 *
 *   - Global data (`/api/tenants/me/`, `/api/plans/`) is namespaced `['global',
 *     …]`. It is NOT tenant-scoped and must NOT be dropped on a tenant switch.
 *
 * Adding a tenant-scoped query in a later stage means adding a key here that
 * takes `tenantId` — the shape makes the wrong thing hard to write.
 */

export const queryKeys = {
  /** The signed-in user's own identity ({id, email}). Global — not per-tenant. */
  currentUser: () => ['global', 'user', 'me'] as const,

  /** Tenants the current user belongs to, with role. Global — not per-tenant. */
  tenantsMe: () => ['global', 'tenants', 'me'] as const,

  /** Global plan catalogue. Not tenant-scoped. */
  plans: () => ['global', 'plans'] as const,

  /** Members of one tenant. C4 builds the page; the key is defined now. */
  members: (tenantId: string) => ['tenant', tenantId, 'members'] as const,

  /** The one subscription for one tenant. C5 builds the page. */
  currentSubscription: (tenantId: string) =>
    ['tenant', tenantId, 'subscription', 'current'] as const,

  /**
   * Platform-admin data (docs/platform-admin-spec.md) — every tenant / the
   * system-wide aggregates. Namespaced `['global', …]`: this is explicitly
   * NOT tenant-scoped (that is the whole point), so a tenant switch must not
   * drop it, exactly like `plans()` / `tenantsMe()`.
   */
  platformTenants: (params: Record<string, string | undefined> = {}) =>
    ['global', 'platform', 'tenants', params] as const,
  platformStats: () => ['global', 'platform', 'stats'] as const,

  /**
   * Operator Control Plane, Phase 1 (docs/operator-control-plane-spec.md) —
   * every one of these is cross-tenant ('global'), never per-tenant, same as
   * the two above. Filter/pagination params are part of the key itself so a
   * filter change is a cache-key change (an automatic refetch), not
   * something a component has to invalidate by hand.
   */
  platformHealth: () => ['global', 'platform', 'health'] as const,
  platformPlans: (params: Record<string, string | undefined> = {}) =>
    ['global', 'platform', 'plans', params] as const,
  platformPlanDetail: (id: string) =>
    ['global', 'platform', 'plans', 'detail', id] as const,
  platformTenantDetail: (id: string) =>
    ['global', 'platform', 'tenants', 'detail', id] as const,
  platformWebhookEvents: (params: Record<string, string | undefined> = {}) =>
    ['global', 'platform', 'webhook-events', params] as const,
  platformWebhookEventDetail: (id: string) =>
    ['global', 'platform', 'webhook-events', 'detail', id] as const,
  platformReconciliationDiscrepancies: (
    params: Record<string, string | undefined> = {},
  ) => ['global', 'platform', 'reconciliation-discrepancies', params] as const,
  platformUsers: (params: Record<string, string | undefined> = {}) =>
    ['global', 'platform', 'users', params] as const,
  platformUserDetail: (id: string) =>
    ['global', 'platform', 'users', 'detail', id] as const,

  /**
   * Operator Control Plane, Phase 2 (docs/operator-control-plane-spec.md) —
   * the audit-log read surface. Same 'global' namespacing as every other
   * platform key; filters are part of the key for the same auto-refetch
   * reason as above.
   */
  platformAuditLog: (params: Record<string, string | undefined> = {}) =>
    ['global', 'platform', 'audit-log', params] as const,
} as const

/** The prefix every tenant-scoped key starts with — used by tests and tooling. */
export const TENANT_KEY_ROOT = 'tenant' as const
/** The prefix every global key starts with. */
export const GLOBAL_KEY_ROOT = 'global' as const
