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

/**
 * Every paginated platform-admin list response shares this envelope
 * (docs/operator-control-plane-spec.md §C — Phase 1 introduces pagination).
 */
export function paginated<T>(results: T[]): {
  count: number
  next: string | null
  previous: string | null
  results: T[]
} {
  return { count: results.length, next: null, previous: null, results }
}

export const platformTenantsHandler = (
  tenants: PlatformTenantRow[] = PLATFORM_TENANTS,
) =>
  http.get(apiUrl('/platform/tenants/'), () =>
    HttpResponse.json(paginated(tenants)),
  )

export const platformStatsHandler = (
  stats: PlatformStatsBody = PLATFORM_STATS,
) => http.get(apiUrl('/platform/stats/'), () => HttpResponse.json(stats))

// --- Operator Control Plane, Phase 1 (docs/operator-control-plane-spec.md) ---

export interface PlatformHealthBody {
  total_tenants: number
  unprocessed_webhook_events: number
  discrepancies_last_24h: number
  last_webhook_received_at: string | null
  last_usage_snapshot_at: string | null
  last_discrepancy_detected_at: string | null
  payment_gateway: string
}

export const PLATFORM_HEALTH: PlatformHealthBody = {
  total_tenants: 3,
  unprocessed_webhook_events: 1,
  discrepancies_last_24h: 0,
  last_webhook_received_at: '2026-03-01T00:00:00Z',
  last_usage_snapshot_at: '2026-03-01T03:00:00Z',
  last_discrepancy_detected_at: null,
  payment_gateway: 'mock',
}

export const platformHealthHandler = (health: PlatformHealthBody = PLATFORM_HEALTH) =>
  http.get(apiUrl('/platform/health/'), () => HttpResponse.json(health))

export interface PlatformPlanRow {
  id: string
  name: string
  code: string
  price_cents: number
  currency: string
  interval: 'MONTHLY' | 'ANNUAL'
  is_active: boolean
  external_plan_id: string | null
  subscriber_count: number
}

export const PLATFORM_PLANS: PlatformPlanRow[] = [
  {
    id: 'plan-pro',
    name: 'Pro',
    code: 'PRO',
    price_cents: 2900,
    currency: 'USD',
    interval: 'MONTHLY',
    is_active: true,
    external_plan_id: 'ext_plan_pro',
    subscriber_count: 2,
  },
  {
    id: 'plan-legacy',
    name: 'Legacy',
    code: 'LEGACY',
    price_cents: 1900,
    currency: 'USD',
    interval: 'MONTHLY',
    is_active: false,
    external_plan_id: null,
    subscriber_count: 0,
  },
]

export const platformPlansHandler = (plans: PlatformPlanRow[] = PLATFORM_PLANS) =>
  http.get(apiUrl('/platform/plans/'), () => HttpResponse.json(paginated(plans)))

export const platformPlanDetailHandler = (plan: PlatformPlanRow = PLATFORM_PLANS[0]) =>
  http.get(apiUrl('/platform/plans/detail/'), () => HttpResponse.json(plan))

export interface PlatformTenantDetailBody {
  id: string
  name: string
  slug: string
  created_at: string
  is_active: boolean
  memberships: Array<{ id: string; email: string; role: string; created_at: string }>
  subscription: {
    id: string
    plan: { id: string; name: string; code: string; price_cents: number; currency: string }
    status: string
    current_period_start: string
    current_period_end: string
  } | null
  recent_webhook_events: PlatformWebhookEventRow[]
}

export const PLATFORM_TENANT_DETAIL: PlatformTenantDetailBody = {
  id: 'pt-1',
  name: 'Northwind Trading',
  slug: 'northwind',
  created_at: '2026-01-05T00:00:00Z',
  is_active: true,
  memberships: [
    { id: 'm-1', email: 'owner@northwind.test', role: 'OWNER', created_at: '2026-01-05T00:00:00Z' },
  ],
  subscription: {
    id: 'sub-1',
    plan: { id: 'plan-pro', name: 'Pro', code: 'PRO', price_cents: 2900, currency: 'USD' },
    status: 'ACTIVE',
    current_period_start: '2026-03-01T00:00:00Z',
    current_period_end: '2026-03-31T00:00:00Z',
  },
  recent_webhook_events: [],
}

export const platformTenantDetailHandler = (
  tenant: PlatformTenantDetailBody = PLATFORM_TENANT_DETAIL,
) => http.get(apiUrl('/platform/tenants/detail/'), () => HttpResponse.json(tenant))

export interface PlatformWebhookEventRow {
  id: string
  external_event_id: string
  event_type: 'ACTIVATED' | 'CHARGED' | 'CANCELLED' | 'PAYMENT_TROUBLE' | 'UNKNOWN'
  external_subscription_id: string | null
  tenant: { id: string; name: string; slug: string } | null
  period_start: string | null
  period_end: string | null
  event_created_at: string | null
  received_at: string
  processed: boolean
}

export const PLATFORM_WEBHOOK_EVENTS: PlatformWebhookEventRow[] = [
  {
    id: 'evt-1',
    external_event_id: 'evt_charged_1',
    event_type: 'CHARGED',
    external_subscription_id: 'sub_ext_1',
    tenant: { id: 'pt-1', name: 'Northwind Trading', slug: 'northwind' },
    period_start: '2026-03-01T00:00:00Z',
    period_end: '2026-03-31T00:00:00Z',
    event_created_at: '2026-03-01T00:00:00Z',
    received_at: '2026-03-01T00:05:00Z',
    processed: true,
  },
]

export const platformWebhookEventsHandler = (
  events: PlatformWebhookEventRow[] = PLATFORM_WEBHOOK_EVENTS,
) =>
  http.get(apiUrl('/platform/webhook-events/'), () =>
    HttpResponse.json(paginated(events)),
  )

export const platformWebhookEventDetailHandler = (
  event: PlatformWebhookEventRow = PLATFORM_WEBHOOK_EVENTS[0],
) => http.get(apiUrl('/platform/webhook-events/detail/'), () => HttpResponse.json(event))

export interface PlatformDiscrepancyRow {
  id: string
  tenant: { id: string; name: string; slug: string }
  subscription_id: string
  external_subscription_id: string
  category: 'STATUS_MISMATCH' | 'LOCAL_CANCELED_PROVIDER_ACTIVE' | 'PROVIDER_NOT_FOUND'
  local_status: string
  provider_status: string
  detail: string
  detected_at: string
}

export const PLATFORM_DISCREPANCIES: PlatformDiscrepancyRow[] = [
  {
    id: 'disc-1',
    tenant: { id: 'pt-1', name: 'Northwind Trading', slug: 'northwind' },
    subscription_id: 'sub-1',
    external_subscription_id: 'sub_ext_1',
    category: 'STATUS_MISMATCH',
    local_status: 'ACTIVE',
    provider_status: 'PAST_DUE',
    detail: 'local ACTIVE vs provider PAST_DUE',
    detected_at: '2026-03-02T00:00:00Z',
  },
]

export const platformDiscrepanciesHandler = (
  discrepancies: PlatformDiscrepancyRow[] = PLATFORM_DISCREPANCIES,
) =>
  http.get(apiUrl('/platform/reconciliation-discrepancies/'), () =>
    HttpResponse.json(paginated(discrepancies)),
  )

export interface PlatformUserRow {
  id: string
  email: string
  is_staff: boolean
  is_superuser: boolean
  is_active: boolean
  email_verified: boolean
  date_joined: string
}

export const PLATFORM_USERS: PlatformUserRow[] = [
  {
    id: 'staff-1',
    email: 'operator@example.com',
    is_staff: true,
    is_superuser: false,
    is_active: true,
    email_verified: true,
    date_joined: '2026-01-01T00:00:00Z',
  },
]

export const platformUsersHandler = (users: PlatformUserRow[] = PLATFORM_USERS) =>
  http.get(apiUrl('/platform/users/'), () => HttpResponse.json(paginated(users)))

export const platformUserDetailHandler = (
  user: PlatformUserRow & { memberships?: unknown[] } = {
    ...PLATFORM_USERS[0],
    memberships: [],
  },
) => http.get(apiUrl('/platform/users/detail/'), () => HttpResponse.json(user))

// --- Operator Control Plane, Phase 2 (docs/operator-control-plane-spec.md) ---

/** `PATCH /api/platform/subscriptions/detail/?id=` — echoes back an updated
 * subscription row (the shape TenantDetailPage's `subscription` re-reads). */
export const platformSubscriptionPatchHandler = (
  subscription: PlatformTenantDetailBody['subscription'] = PLATFORM_TENANT_DETAIL.subscription,
) =>
  http.patch(apiUrl('/platform/subscriptions/detail/'), () =>
    HttpResponse.json(subscription),
  )

export const platformSubscriptionPatchErrorHandler = (
  field: 'plan_id' | 'status',
  message: string,
) =>
  http.patch(apiUrl('/platform/subscriptions/detail/'), () =>
    HttpResponse.json({ [field]: [message] }, { status: 400 }),
  )

export interface SweepResultBody {
  total: number
  [key: string]: number
}

export const platformProcessPendingHandler = (
  result: SweepResultBody = { total: 3, processed: 2, deferred: 1, failed: 0 },
) =>
  http.post(apiUrl('/platform/webhook-events/process-pending/'), () =>
    HttpResponse.json(result),
  )

export const platformReconciliationRunHandler = (
  result: SweepResultBody = {
    total: 2,
    matched: 2,
    discrepancies: 0,
    unavailable: 0,
    skipped: 0,
    errors: 0,
  },
) => http.post(apiUrl('/platform/reconciliation/run/'), () => HttpResponse.json(result))

export const platformUsageRunHandler = (
  result: SweepResultBody = { total: 2, created: 2, existing: 0, skipped: 0 },
) => http.post(apiUrl('/platform/usage/run/'), () => HttpResponse.json(result))

export interface PlatformAuditEventRow {
  id: string
  actor: { id: string; email: string } | null
  action: string
  target_type: string
  target_id: string
  summary: string
  metadata: Record<string, unknown>
  is_critical: boolean
  created_at: string
}

export const PLATFORM_AUDIT_EVENTS: PlatformAuditEventRow[] = [
  {
    id: 'audit-1',
    actor: { id: 'staff-1', email: 'operator@example.com' },
    action: 'subscription.transitioned',
    target_type: 'Subscription',
    target_id: 'sub-1',
    summary: 'Transitioned subscription for tenant northwind from ACTIVE to PAST_DUE',
    metadata: { from_status: 'ACTIVE', to_status: 'PAST_DUE' },
    is_critical: true,
    created_at: '2026-03-05T00:00:00Z',
  },
  {
    id: 'audit-2',
    actor: { id: 'staff-1', email: 'operator@example.com' },
    action: 'webhook.sweep_triggered',
    target_type: 'WebhookEvent',
    target_id: '*',
    summary: 'Webhook retry sweep: 3 checked, 2 processed, 1 deferred, 0 failed',
    metadata: { total: 3, processed: 2, deferred: 1, failed: 0 },
    is_critical: false,
    created_at: '2026-03-04T00:00:00Z',
  },
]

export const platformAuditLogHandler = (
  events: PlatformAuditEventRow[] = PLATFORM_AUDIT_EVENTS,
) => http.get(apiUrl('/platform/audit-log/'), () => HttpResponse.json(paginated(events)))


// --- Operator Control Plane, Phase 3 (docs/operator-control-plane-spec.md) ---

/** `POST /api/platform/plans/` — echoes back the created plan row. */
export const platformPlanCreateHandler = (
  plan: PlatformPlanRow = {
    id: 'plan-new',
    name: 'Scale',
    code: 'SCALE',
    price_cents: 19900,
    currency: 'USD',
    interval: 'MONTHLY',
    is_active: true,
    external_plan_id: null,
    subscriber_count: 0,
  },
) =>
  http.post(apiUrl('/platform/plans/'), () =>
    HttpResponse.json(plan, { status: 201 }),
  )

/** `POST /api/platform/plans/` rejecting one field, the DRF shape. */
export const platformPlanCreateErrorHandler = (
  field: string,
  message: string,
  status = 400,
) =>
  http.post(apiUrl('/platform/plans/'), () =>
    HttpResponse.json({ [field]: [message] }, { status }),
  )

/** `PATCH /api/platform/plans/detail/?id=` — echoes back the updated row. */
export const platformPlanPatchHandler = (
  plan: PlatformPlanRow = PLATFORM_PLANS[0],
) => http.patch(apiUrl('/platform/plans/detail/'), () => HttpResponse.json(plan))

export const platformPlanPatchErrorHandler = (field: string, message: string) =>
  http.patch(apiUrl('/platform/plans/detail/'), () =>
    HttpResponse.json({ [field]: [message] }, { status: 400 }),
  )

/** `POST /api/platform/plans/sync/?id=` — the plan row plus `created`. */
export const platformPlanSyncHandler = (
  plan: PlatformPlanRow = {
    ...PLATFORM_PLANS[1],
    external_plan_id: 'ext_plan_legacy',
  },
  created = true,
) =>
  http.post(apiUrl('/platform/plans/sync/'), () =>
    HttpResponse.json({ ...plan, created }),
  )

/** `POST /api/platform/plans/sync/?id=` failing at the gateway (502). */
export const platformPlanSyncErrorHandler = (status = 502) =>
  http.post(apiUrl('/platform/plans/sync/'), () =>
    HttpResponse.json(
      {
        detail:
          'The payment gateway rejected or could not complete this sync. ' +
          'Check the service logs.',
      },
      { status },
    ),
  )


// --- Operator Control Plane, Phase 4 (Root tier) ---

/** `GET /api/users/me/` returning a Root identity: staff AND superuser. */
export const usersMeRootHandler = (
  user: { id: string; email: string } = {
    id: 'root-1',
    email: 'root@example.com',
  },
) =>
  http.get(apiUrl('/users/me/'), () =>
    HttpResponse.json({ ...user, is_staff: true, is_superuser: true }),
  )

/** `PATCH /api/platform/users/detail/?id=` — echoes back the updated user. */
export const platformUserRolePatchHandler = (
  user: PlatformUserRow = { ...PLATFORM_USERS[0], is_superuser: true },
) => http.patch(apiUrl('/platform/users/detail/'), () => HttpResponse.json(user))

export const platformUserRolePatchErrorHandler = (
  detail = 'This change would leave no active root operator. Promote another root account first.',
  status = 400,
) =>
  http.patch(apiUrl('/platform/users/detail/'), () =>
    HttpResponse.json({ detail }, { status }),
  )

/**
 * A provider payload shaped like a real one — it carries customer contact and
 * card metadata, which is the whole reason the raw read is Root-gated.
 */
export const RAW_WEBHOOK_PAYLOAD = {
  event: 'subscription.charged',
  payload: {
    payment: {
      entity: {
        id: 'pay_1',
        email: 'customer@example.com',
        card: { last4: '4242' },
      },
    },
  },
}

/** `GET /api/platform/webhook-events/raw/?id=` — Root-only diagnostic read. */
export const platformWebhookRawHandler = (
  event: PlatformWebhookEventRow = PLATFORM_WEBHOOK_EVENTS[0],
  rawPayload: unknown = RAW_WEBHOOK_PAYLOAD,
) =>
  http.get(apiUrl('/platform/webhook-events/raw/'), () =>
    HttpResponse.json({ ...event, raw_payload: rawPayload }),
  )

export const platformWebhookRawErrorHandler = (status = 403) =>
  http.get(apiUrl('/platform/webhook-events/raw/'), () =>
    HttpResponse.json(
      { detail: 'This action is restricted to root operators.' },
      { status },
    ),
  )
