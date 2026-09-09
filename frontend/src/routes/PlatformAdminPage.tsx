/**
 * Platform Admin — docs/platform-admin-spec.md.
 *
 * The one screen in this app that shows cross-tenant data. It is read-only and
 * reachable only by platform staff. The gate below is UX ONLY — the real
 * boundary is `IsPlatformStaff` on `/api/platform/*` server-side, which returns
 * 403 to any non-staff caller regardless of what renders here (same discipline
 * as every other client-side permission check in this project).
 *
 * Two independent queries (tenants list + aggregate stats), each with its own
 * loading / error branch — no combined gate, matching the per-query failure
 * isolation the C6 Overview page established. Both keys are `['global', …]`
 * (query-keys.ts): this data is not tenant-scoped, so a tenant switch in the
 * navbar switcher must not drop it.
 */

import { Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Card, Skeleton, Table } from '../components'
import type { BadgeVariant, Column } from '../components'
import { apiClient } from '../lib/api-client'
import { formatDate } from '../lib/format'
import { queryKeys } from '../lib/query-keys'
import { useCurrentUser } from '../components/layout/use-current-user'
import { PlatformBarChart } from './PlatformBarChart'
import type { BarDatum } from './PlatformBarChart'
import type { SubscriptionStatus } from './SubscriptionPage'

type StatusKey = SubscriptionStatus | 'NONE'

interface PlatformTenant {
  id: string
  name: string
  slug: string
  created_at: string
  member_count: number
  subscription: { plan_name: string; status: SubscriptionStatus } | null
}

interface PlatformStats {
  total_tenants: number
  status_breakdown: Record<StatusKey, number>
  plan_distribution: Array<{ plan_name: string; count: number }>
  signups_over_time: Array<{ month: string; count: number }>
}

// Copied from SubscriptionPage.tsx (source of truth), not imported —
// spec §11 / the same reason OverviewPage.tsx copies them: those maps are
// module-private and that file must not be modified. The extra 'NONE' key is
// this page's own — a tenant with no subscription at all.
const STATUS_VARIANT: Record<StatusKey, BadgeVariant> = {
  ACTIVE: 'success',
  TRIALING: 'warning',
  PAST_DUE: 'danger',
  CANCELED: 'neutral',
  NONE: 'neutral',
}

const STATUS_LABEL: Record<StatusKey, string> = {
  ACTIVE: 'Active',
  TRIALING: 'Trialing',
  PAST_DUE: 'Past due',
  CANCELED: 'Canceled',
  NONE: 'No subscription',
}

const STATUS_ORDER: StatusKey[] = [
  'ACTIVE',
  'TRIALING',
  'PAST_DUE',
  'CANCELED',
  'NONE',
]

/** "2026-01" → "Jan 2026"; leaves anything unparseable untouched. */
function formatMonth(ym: string): string {
  const parsed = new Date(`${ym}-01T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return ym
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

const tenantColumns: Array<Column<PlatformTenant>> = [
  {
    key: 'name',
    header: 'Tenant',
    render: (t) => (
      <div className="min-w-0">
        <span className="block max-w-[16rem] truncate text-primary" title={t.name}>
          {t.name}
        </span>
        <span className="block font-mono text-caption text-secondary">
          {t.slug}
        </span>
      </div>
    ),
  },
  {
    key: 'member_count',
    header: 'Members',
    numeric: true,
    render: (t) => t.member_count,
  },
  {
    key: 'plan',
    header: 'Plan',
    render: (t) => t.subscription?.plan_name ?? '—',
  },
  {
    key: 'status',
    header: 'Status',
    render: (t) =>
      t.subscription ? (
        <Badge variant={STATUS_VARIANT[t.subscription.status]}>
          {STATUS_LABEL[t.subscription.status]}
        </Badge>
      ) : (
        <Badge variant="neutral">{STATUS_LABEL.NONE}</Badge>
      ),
  },
  {
    key: 'created_at',
    header: 'Created',
    render: (t) => (
      <span className="whitespace-nowrap">{formatDate(t.created_at)}</span>
    ),
  },
]

export function PlatformAdminPage() {
  const { isStaff, isStaffResolving } = useCurrentUser()

  const stats = useQuery({
    queryKey: queryKeys.platformStats(),
    queryFn: () => apiClient.get<PlatformStats>('/platform/stats/'),
    enabled: isStaff,
  })

  const tenants = useQuery({
    queryKey: queryKeys.platformTenants(),
    queryFn: () => apiClient.get<PlatformTenant[]>('/platform/tenants/'),
    enabled: isStaff,
  })

  // Gate. `isStaffResolving` (not `resolving`) so a staff member who just
  // logged in doesn't flash "access denied" while /users/me/ is still in
  // flight — see use-current-user.ts.
  if (isStaffResolving) {
    return (
      <div
        className="grid min-h-[40vh] place-items-center text-secondary"
        role="status"
        aria-live="polite"
      >
        <span className="text-body">Loading&hellip;</span>
      </div>
    )
  }

  if (!isStaff) {
    return <Navigate to="/overview" replace />
  }

  // Hoisted so the `stats.data` narrowing survives into the `.map` closures
  // below (TS drops property narrowing inside nested callbacks).
  const statsData = stats.data

  const statusData: BarDatum[] = statsData
    ? STATUS_ORDER.map((key) => ({
        label: STATUS_LABEL[key],
        value: statsData.status_breakdown[key] ?? 0,
      }))
    : []

  const planData: BarDatum[] = statsData
    ? statsData.plan_distribution.map((p) => ({
        label: p.plan_name,
        value: p.count,
      }))
    : []

  const signupData: BarDatum[] = statsData
    ? statsData.signups_over_time.map((s) => ({
        label: formatMonth(s.month),
        value: s.count,
      }))
    : []

  return (
    <section className="mx-auto max-w-5xl">
      <h1 className="text-display text-primary">Platform Admin</h1>
      <p className="mt-1 text-body text-secondary">
        Every tenant and subscription across the system. Read-only.
      </p>

      {/* KPI row */}
      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
        {stats.isPending ? (
          <div className="col-span-full">
            <Skeleton count={1} height={72} label="Loading platform stats" />
          </div>
        ) : stats.isError ? (
          <div className="col-span-full">
            <Alert
              variant="danger"
              action={
                <Button size="sm" variant="secondary" onClick={() => stats.refetch()}>
                  Retry
                </Button>
              }
            >
              Couldn’t load platform statistics.
            </Alert>
          </div>
        ) : statsData ? (
          <>
            <Card>
              <h2 className="text-caption text-secondary">Total tenants</h2>
              <p className="num mt-1 text-h2 text-primary">
                {statsData.total_tenants}
              </p>
            </Card>
            {statusData.map((d) => (
              <Card key={d.label}>
                <h2 className="text-caption text-secondary">{d.label}</h2>
                <p className="num mt-1 text-h2 text-primary">{d.value}</p>
              </Card>
            ))}
          </>
        ) : null}
      </div>

      {/* Charts */}
      <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Status & plan distribution">
          {stats.isPending ? (
            <Skeleton count={4} height={24} label="Loading distribution charts" />
          ) : stats.isError ? (
            <p className="text-body text-secondary">Unavailable.</p>
          ) : (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <PlatformBarChart
                title="By subscription status"
                data={statusData}
                emptyLabel="No tenants yet."
              />
              <PlatformBarChart
                title="By plan"
                data={planData}
                emptyLabel="No subscriptions yet."
              />
            </div>
          )}
        </Card>

        <Card title="Signups over time">
          {stats.isPending ? (
            <Skeleton count={4} height={24} label="Loading signups chart" />
          ) : stats.isError ? (
            <p className="text-body text-secondary">Unavailable.</p>
          ) : (
            <PlatformBarChart
              title="Tenants created per month"
              data={signupData}
              emptyLabel="No signups yet."
            />
          )}
        </Card>
      </div>

      {/* Tenant list */}
      <div className="mt-10">
        <h2 className="text-h2 text-primary">All tenants</h2>
        <div className="mt-4">
          {tenants.isPending ? (
            <Skeleton count={6} height={52} label="Loading tenants" />
          ) : tenants.isError ? (
            <Alert
              variant="danger"
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => tenants.refetch()}
                >
                  Retry
                </Button>
              }
            >
              Couldn’t load the tenant list.
            </Alert>
          ) : !tenants.data || tenants.data.length === 0 ? (
            <Card>
              <p className="text-body text-secondary">
                No tenants in the system yet.
              </p>
            </Card>
          ) : (
            <Table
              caption="All tenants"
              columns={tenantColumns}
              rows={tenants.data}
              rowKey={(t) => t.id}
              renderMobileCard={(t) => (
                <>
                  <span className="block truncate text-label text-primary">
                    {t.name}
                  </span>
                  <span className="block font-mono text-caption text-secondary">
                    {t.slug}
                  </span>
                  <span className="mt-2 flex flex-wrap items-center gap-2 text-caption text-secondary">
                    {t.subscription ? (
                      <Badge variant={STATUS_VARIANT[t.subscription.status]}>
                        {STATUS_LABEL[t.subscription.status]}
                      </Badge>
                    ) : (
                      <Badge variant="neutral">{STATUS_LABEL.NONE}</Badge>
                    )}
                    <span>{t.subscription?.plan_name ?? 'No plan'}</span>
                    <span>·</span>
                    <span>
                      {t.member_count}{' '}
                      {t.member_count === 1 ? 'member' : 'members'}
                    </span>
                  </span>
                </>
              )}
            />
          )}
        </div>
      </div>
    </section>
  )
}
