import { http, HttpResponse } from 'msw'

import type { TenantMembership } from '../lib/tenant'

/** MSW pattern that matches `${API_BASE_URL}${path}` regardless of origin. */
export const apiUrl = (path: string) => `*/api${path}`

export const TENANT_A: TenantMembership = {
  id: 'tenant-a',
  name: 'Alpha Corp',
  slug: 'alpha',
  created_at: '2026-01-01T00:00:00Z',
  is_active: true,
  role: 'OWNER',
}

export const TENANT_B: TenantMembership = {
  id: 'tenant-b',
  name: 'Beta LLC',
  slug: 'beta',
  created_at: '2026-02-01T00:00:00Z',
  is_active: true,
  role: 'MEMBER',
}

export const tenantsMeHandler = (tenants: TenantMembership[]) =>
  http.get(apiUrl('/tenants/me/'), () => HttpResponse.json(tenants))

export interface MemberRow {
  id: string
  email: string
  role: 'OWNER' | 'MEMBER'
  created_at: string
}

export const MEMBERS_A: MemberRow[] = [
  { id: 'm-a1', email: 'owner@alpha.test', role: 'OWNER', created_at: '2026-01-02T00:00:00Z' },
  { id: 'm-a2', email: 'ada@alpha.test', role: 'MEMBER', created_at: '2026-01-10T00:00:00Z' },
]

export const MEMBERS_B: MemberRow[] = [
  { id: 'm-b1', email: 'owner@beta.test', role: 'OWNER', created_at: '2026-02-02T00:00:00Z' },
]

/** `GET /api/memberships/` — a fixed list regardless of the tenant header. */
export const membershipsHandler = (members: MemberRow[]) =>
  http.get(apiUrl('/memberships/'), () => HttpResponse.json(members))

/**
 * `GET /api/memberships/` that answers per `X-Tenant-ID` — for asserting that a
 * tenant switch on the Members page re-fetches the new tenant's list.
 */
export const membershipsByTenantHandler = (
  byTenantId: Record<string, MemberRow[]>,
) =>
  http.get(apiUrl('/memberships/'), ({ request }) => {
    const tenantId = request.headers.get('X-Tenant-ID') ?? ''
    return HttpResponse.json(byTenantId[tenantId] ?? [])
  })

/**
 * `GET /api/users/me/` — the signed-in user's identity (§0.1), plus `is_staff`
 * (platform-admin spec §4.4). `is_staff` defaults to `false` when omitted, so
 * every existing test that passes no user keeps a non-staff identity.
 */
export const usersMeHandler = (
  user: { id: string; email: string; is_staff?: boolean } = {
    id: 'user-1',
    email: 'user@example.com',
  },
) =>
  http.get(apiUrl('/users/me/'), () =>
    HttpResponse.json({ is_staff: false, ...user }),
  )

/** `GET /api/users/me/` returning a platform-staff identity. */
export const usersMeStaffHandler = (
  user: { id: string; email: string } = {
    id: 'staff-1',
    email: 'operator@example.com',
  },
) => usersMeHandler({ ...user, is_staff: true })

/** `POST /api/auth/logout/` — best-effort refresh-token blacklist (§0.2). */
export const logoutHandler = () =>
  http.post(apiUrl('/auth/logout/'), () => new HttpResponse(null, { status: 200 }))

/**
 * A working set of auth-lifecycle handlers, for tests that need to reach an
 * authed state: login, refresh, `/users/me/`, logout.
 */
export const authHandlers = () => [
  http.post(apiUrl('/auth/login/'), () =>
    HttpResponse.json({ access: 'test-access', refresh: 'test-refresh' }),
  ),
  http.post(apiUrl('/auth/refresh/'), () =>
    HttpResponse.json({ access: 'test-access-2', refresh: 'test-refresh-2' }),
  ),
  usersMeHandler(),
  logoutHandler(),
]

export interface PlanRow {
  id: string
  name: string
  code: string
  price_cents: number
  currency: string
  interval: 'MONTHLY' | 'ANNUAL'
}

export const PLAN_PRO: PlanRow = {
  id: 'plan-pro',
  name: 'Pro',
  code: 'PRO',
  price_cents: 2900,
  currency: 'USD',
  interval: 'MONTHLY',
}

export const PLAN_TEAM: PlanRow = {
  id: 'plan-team',
  name: 'Team',
  code: 'TEAM',
  price_cents: 9900,
  currency: 'USD',
  interval: 'MONTHLY',
}

/** `GET /api/plans/` — global, no X-Tenant-ID required. */
export const plansHandler = (plans: PlanRow[] = [PLAN_PRO, PLAN_TEAM]) =>
  http.get(apiUrl('/plans/'), () => HttpResponse.json(plans))

export interface SubscriptionRow {
  id: string
  plan: PlanRow
  status: 'TRIALING' | 'ACTIVE' | 'PAST_DUE' | 'CANCELED'
  current_period_start: string
  current_period_end: string
  created_at: string
  updated_at: string
}

export const subscriptionFor = (
  plan: PlanRow,
  status: SubscriptionRow['status'] = 'ACTIVE',
): SubscriptionRow => ({
  id: 'sub-1',
  plan,
  status,
  current_period_start: '2026-03-01T00:00:00Z',
  current_period_end: '2026-03-31T00:00:00Z',
  created_at: '2026-03-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
})

/** `GET /api/subscriptions/current/` — 404 (no subscription) when `sub` is null. */
export const currentSubscriptionHandler = (sub: SubscriptionRow | null) =>
  http.get(apiUrl('/subscriptions/current/'), () =>
    sub
      ? HttpResponse.json(sub)
      : HttpResponse.json(
          { detail: 'This tenant has no subscription yet.' },
          { status: 404 },
        ),
  )

// --- D2 checkout (stage-d2-spec.md) ---

/** `POST /api/subscriptions/current/checkout/` — returns Checkout params. */
export const checkoutStartHandler = (
  body: Partial<{
    razorpay_subscription_id: string
    razorpay_key_id: string
    plan: PlanRow
  }> = {},
) =>
  http.post(apiUrl('/subscriptions/current/checkout/'), () =>
    HttpResponse.json({
      razorpay_subscription_id: 'sub_TESTCHECKOUT',
      razorpay_key_id: 'rzp_test_KEY',
      plan: PLAN_PRO,
      ...body,
    }),
  )

/** `POST /api/subscriptions/current/confirm-checkout/` — 200 processing, or a
 *  400 when `ok` is false (bad signature). */
export const checkoutConfirmHandler = (ok = true) =>
  http.post(apiUrl('/subscriptions/current/confirm-checkout/'), () =>
    ok
      ? HttpResponse.json({ status: 'processing' })
      : HttpResponse.json(
          { detail: 'Checkout could not be verified.' },
          { status: 400 },
        ),
  )

/**
 * `GET /api/subscriptions/current/` that answers per `X-Tenant-ID` — for
 * asserting that a tenant switch refetches the new tenant's subscription while
 * `/plans/` (global) is not refetched at all.
 */
export const currentSubscriptionByTenantHandler = (
  byTenantId: Record<string, SubscriptionRow | null>,
) =>
  http.get(apiUrl('/subscriptions/current/'), ({ request }) => {
    const tenantId = request.headers.get('X-Tenant-ID') ?? ''
    const sub = byTenantId[tenantId] ?? null
    return sub
      ? HttpResponse.json(sub)
      : HttpResponse.json(
          { detail: 'This tenant has no subscription yet.' },
          { status: 404 },
        )
  })

// --- Platform admin (docs/platform-admin-spec.md) ---

export interface PlatformTenantRow {
  id: string
  name: string
  slug: string
  created_at: string
  member_count: number
  subscription: { plan_name: string; status: SubscriptionRow['status'] } | null
}

export interface PlatformStatsBody {
  total_tenants: number
  status_breakdown: Record<string, number>
  plan_distribution: Array<{ plan_name: string; count: number }>
  signups_over_time: Array<{ month: string; count: number }>
}

// Names deliberately distinct from TENANT_A / TENANT_B — those appear in the
// navbar tenant switcher, and a page test that asserts on a tenant name in the
// platform table must not collide with the switcher's copy of it.
export const PLATFORM_TENANTS: PlatformTenantRow[] = [
  {
    id: 'pt-1',
    name: 'Northwind Trading',
    slug: 'northwind',
    created_at: '2026-01-05T00:00:00Z',
    member_count: 3,
    subscription: { plan_name: 'Pro', status: 'ACTIVE' },
  },
  {
    id: 'pt-2',
    name: 'Globex',
    slug: 'globex',
    created_at: '2026-02-11T00:00:00Z',
    member_count: 1,
    subscription: { plan_name: 'Team', status: 'TRIALING' },
  },
  {
    id: 'pt-3',
    name: 'Initech',
    slug: 'initech',
    created_at: '2026-02-20T00:00:00Z',
    member_count: 2,
    subscription: null,
  },
]

export const PLATFORM_STATS: PlatformStatsBody = {
  total_tenants: 3,
  status_breakdown: {
    ACTIVE: 1,
    TRIALING: 1,
    PAST_DUE: 0,
    CANCELED: 0,
    NONE: 1,
  },
  plan_distribution: [
    { plan_name: 'Pro', count: 1 },
    { plan_name: 'Team', count: 1 },
  ],
  signups_over_time: [
    { month: '2026-01', count: 1 },
    { month: '2026-02', count: 2 },
  ],
}

export const platformTenantsHandler = (
  tenants: PlatformTenantRow[] = PLATFORM_TENANTS,
) => http.get(apiUrl('/platform/tenants/'), () => HttpResponse.json(tenants))

export const platformStatsHandler = (
  stats: PlatformStatsBody = PLATFORM_STATS,
) => http.get(apiUrl('/platform/stats/'), () => HttpResponse.json(stats))
