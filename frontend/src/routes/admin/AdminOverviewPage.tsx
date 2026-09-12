/**
 * /admin (index) — docs/operator-control-plane-spec.md §D: "the existing
 * platform-admin page's content, evolved in place — moved, not copied."
 *
 * This is the retired PlatformAdminPage.tsx's content (KPI row, status/plan
 * charts, signups chart, tenant list), rendered as the index child of
 * AdminLayout (which now owns the staff gate, the "Platform Admin" heading,
 * and the section tab strip — none of that is duplicated here). Two
 * additions: the tenant list now reads the paginated envelope Phase 1 adds
 * to GET /api/platform/tenants/ (`.results`, not a bare array), and a small
 * system-health row from the new GET /api/platform/health/.
 *
 * Same per-query failure isolation as before: three independent queries,
 * each with its own loading/error branch, no combined gate.
 */

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { Alert, Badge, Button, Card, Skeleton, Table } from '../../components'
import type { BadgeVariant, Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { PlatformBarChart } from '../PlatformBarChart'
import type { BarDatum } from '../PlatformBarChart'
import type { SubscriptionStatus } from '../SubscriptionPage'

type StatusKey = SubscriptionStatus | 'NONE'

interface PlatformTenant {
  id: string
  name: string
  slug: string
  created_at: string
  member_count: number
  subscription: { plan_name: string; status: SubscriptionStatus } | null
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

interface PlatformStats {
  total_tenants: number
  status_breakdown: Record<StatusKey, number>
  plan_distribution: Array<{ plan_name: string; count: number }>
  signups_over_time: Array<{ month: string; count: number }>
}

interface PlatformHealth {
  total_tenants: number
  unprocessed_webhook_events: number
  discrepancies_last_24h: number
  last_webhook_received_at: string | null
  last_usage_snapshot_at: string | null
  last_discrepancy_detected_at: string | null
  payment_gateway: string
}

// Copied from SubscriptionPage.tsx (source of truth), not imported — same
// reason OverviewPage.tsx / the retired PlatformAdminPage.tsx already did:
// those maps are module-private and that file must not be modified. The
// extra 'NONE' key is this page's own — a tenant with no subscription at all.
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

const STATUS_ORDER: StatusKey[] = ['ACTIVE', 'TRIALING', 'PAST_DUE', 'CANCELED', 'NONE']

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
        <span className="block font-mono text-caption text-secondary">{t.slug}</span>
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
    render: (t) => <span className="whitespace-nowrap">{formatDate(t.created_at)}</span>,
  },
]

export function AdminOverviewPage() {
  const stats = useQuery({
    queryKey: queryKeys.platformStats(),
    queryFn: () => apiClient.get<PlatformStats>('/platform/stats/'),
  })

  const tenants = useQuery({
    queryKey: queryKeys.platformTenants(),
    queryFn: () =>
      apiClient.get<PaginatedResponse<PlatformTenant>>('/platform/tenants/'),
  })

  const health = useQuery({
    queryKey: queryKeys.platformHealth(),
    queryFn: () => apiClient.get<PlatformHealth>('/platform/health/'),
  })

  const statsData = stats.data

  const statusData: BarDatum[] = statsData
    ? STATUS_ORDER.map((key) => ({
        label: STATUS_LABEL[key],
        value: statsData.status_breakdown[key] ?? 0,
      }))
    : []

  const planData: BarDatum[] = statsData
    ? statsData.plan_distribution.map((p) => ({ label: p.plan_name, value: p.count }))
    : []

  const signupData: BarDatum[] = statsData
    ? statsData.signups_over_time.map((s) => ({
        label: formatMonth(s.month),
        value: s.count,
      }))
    : []

  return (
    <>
      {/* System health */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {health.isPending ? (
          <div className="col-span-full">
            <Skeleton count={1} height={56} label="Loading system health" />
          </div>
        ) : health.isError ? (
          <div className="col-span-full">
            <Alert
              variant="danger"
              action={
                <Button size="sm" variant="secondary" onClick={() => health.refetch()}>
                  Retry
                </Button>
              }
            >
              Couldn’t load system health.
            </Alert>
          </div>
        ) : health.data ? (
          <>
            <Card>
              <h2 className="text-caption text-secondary">Unprocessed webhooks</h2>
              <p className="num mt-1 text-h2 text-primary">
                {health.data.unprocessed_webhook_events}
              </p>
            </Card>
            <Card>
              <h2 className="text-caption text-secondary">Discrepancies (24h)</h2>
              <p className="num mt-1 text-h2 text-primary">
                {health.data.discrepancies_last_24h}
              </p>
            </Card>
            <Card>
              <h2 className="text-caption text-secondary">Last usage snapshot</h2>
              <p className="mt-1 text-body text-primary">
                {health.data.last_usage_snapshot_at
                  ? formatDate(health.data.last_usage_snapshot_at)
                  : '—'}
              </p>
            </Card>
            <Card>
              <h2 className="text-caption text-secondary">Payment gateway</h2>
              <p className="mt-1 text-body text-primary">{health.data.payment_gateway}</p>
            </Card>
          </>
        ) : null}
      </div>

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
              <p className="num mt-1 text-h2 text-primary">{statsData.total_tenants}</p>
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
        <div className="flex items-center justify-between">
          <h2 className="text-h2 text-primary">All tenants</h2>
          <Link to="/admin/tenants" className="text-label text-accent-600 hover:underline">
            View all
          </Link>
        </div>
        <div className="mt-4">
          {tenants.isPending ? (
            <Skeleton count={6} height={52} label="Loading tenants" />
          ) : tenants.isError ? (
            <Alert
              variant="danger"
              action={
                <Button size="sm" variant="secondary" onClick={() => tenants.refetch()}>
                  Retry
                </Button>
              }
            >
              Couldn’t load the tenant list.
            </Alert>
          ) : !tenants.data || tenants.data.results.length === 0 ? (
            <Card>
              <p className="text-body text-secondary">No tenants in the system yet.</p>
            </Card>
          ) : (
            <Table
              caption="All tenants"
              columns={tenantColumns}
              rows={tenants.data.results}
              rowKey={(t) => t.id}
              renderMobileCard={(t) => (
                <>
                  <span className="block truncate text-label text-primary">{t.name}</span>
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
                      {t.member_count} {t.member_count === 1 ? 'member' : 'members'}
                    </span>
                  </span>
                </>
              )}
            />
          )}
        </div>
      </div>
    </>
  )
}
