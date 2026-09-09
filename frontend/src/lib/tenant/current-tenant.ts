/**
 * The active tenant id, as far as the API client is concerned: the value it
 * puts in the `X-Tenant-ID` header on tenant-scoped requests.
 *
 * This is ONLY "which header to send." It is NOT authorization — CLAUDE.md /
 * UI spec §C.6.3: the backend re-resolves `Membership` from the JWT + this
 * header on every request regardless of what the client believes. A forged or
 * stale value here gets a 403/404 from the server, not access.
 *
 * Stage C2's `TenantProvider` (built next session) is the writer: it calls
 * `setCurrentTenantId` on load and on every `switchTenant`. This module is a
 * plain holder so the non-React API client can read the value without a
 * dependency on React context. The structural cache-isolation guarantee lives
 * in the query keys (spec §4.3), not here.
 */

let currentTenantId: string | null = null

export function getCurrentTenantId(): string | null {
  return currentTenantId
}

export function setCurrentTenantId(tenantId: string | null): void {
  currentTenantId = tenantId
}

/**
 * localStorage key for the "resume where you left off" tenant hint. Written and
 * read by `TenantProvider`; cleared on identity change by `AuthProvider` — a
 * stale value here is what let a just-logged-in user re-select the *previous*
 * user's tenant after a no-reload logout/login.
 */
export const LAST_TENANT_STORAGE_KEY = 'billing.last_tenant_id'

/** Forget the persisted tenant hint. Called when the identity changes. */
export function clearStoredTenantId(): void {
  try {
    localStorage.removeItem(LAST_TENANT_STORAGE_KEY)
  } catch {
    /* storage unavailable — nothing to clear */
  }
}
