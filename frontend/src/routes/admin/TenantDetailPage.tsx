/**
 * /admin/tenants/:id — one tenant's operator view: tenant info, memberships,
 * subscription, and its most recent normalized webhook events (sanitized —
 * never raw_payload). Read-only (no override controls — those are Phase 2+).
 */

import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, DataList, Skeleton, Table } from '../../components'
import type { BadgeVariant, Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate, formatMoney } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import type { SubscriptionStatus } from '../SubscriptionPage'

interface Membership {
  id: string
  email: string
  role: 'OWNER' | 'MEMBER'
  created_at: string
}

interface Subscription {
  id: string
  plan: { id: string; name: string; code: string; price_cents: number; currency: string }
  status: SubscriptionStatus
  current_period_start: string
  current_period_end: string
}

interface WebhookEventRow {
  id: string
  external_event_id: string
  event_type: 'ACTIVATED' | 'CHARGED' | 'CANCELLED' | 'PAYMENT_TROUBLE' | 'UNKNOWN'
  external_subscription_id: string | null
  received_at: string
  processed: boolean
}

interface TenantDetail {
  id: string
  name: string
  slug: string
  created_at: string
  is_active: boolean
  memberships: Membership[]
  subscription: Subscription | null
  recent_webhook_events: WebhookEventRow[]
}

const STATUS_VARIANT: Record<SubscriptionStatus, BadgeVariant> = {
  ACTIVE: 'success',
  TRIALING: 'warning',
  PAST_DUE: 'danger',
  CANCELED: 'neutral',
}

const membershipColumns: Array<Column<Membership>> = [
  { key: 'email', header: 'Email' },
  { key: 'role', header: 'Role', render: (m) => <Badge variant="neutral">{m.role}</Badge> },
  { key: 'created_at', header: 'Joined', render: (m) => formatDate(m.created_at) },
]

const eventColumns: Array<Column<WebhookEventRow>> = [
  { key: 'event_type', header: 'Event' },
  {
    key: 'processed',
    header: 'Processed',
    render: (e) => (
      <Badge variant={e.processed ? 'success' : 'warning'}>
        {e.processed ? 'Yes' : 'Pending'}
      </Badge>
    ),
  },
  { key: 'received_at', header: 'Received', render: (e) => formatDate(e.received_at) },
]

export function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()

  const tenant = useQuery({
    queryKey: queryKeys.platformTenantDetail(id ?? ''),
    queryFn: () => apiClient.get<TenantDetail>(`/platform/tenants/detail/?id=${id}`),
    enabled: Boolean(id),
  })

  if (tenant.isPending) {
    return <Skeleton count={6} height={24} label="Loading tenant" />
  }

  if (tenant.isError) {
    return (
      <Alert
        variant="danger"
        action={
          <Button size="sm" variant="secondary" onClick={() => tenant.refetch()}>
            Retry
          </Button>
        }
      >
        Couldn’t load this tenant.
      </Alert>
    )
  }

  const data = tenant.data
  if (!data) return null

  return (
    <div>
      <h2 className="text-h2 text-primary">{data.name}</h2>
      <p className="mt-1 font-mono text-caption text-secondary">{data.slug}</p>

      <DataList
        className="mt-6 max-w-[42rem]"
        rows={[
          { term: 'Created', children: formatDate(data.created_at) },
          {
            term: 'Plan',
            children: data.subscription ? data.subscription.plan.name : '—',
          },
          {
            term: 'Subscription status',
            children: data.subscription ? (
              <Badge variant={STATUS_VARIANT[data.subscription.status]}>
                {data.subscription.status}
              </Badge>
            ) : (
              <span className="text-secondary">No subscription</span>
            ),
          },
          {
            term: 'Price',
            children: data.subscription
              ? formatMoney(
                  data.subscription.plan.price_cents,
                  data.subscription.plan.currency,
                )
              : '—',
          },
        ]}
      />

      <div className="mt-10">
        <h3 className="text-h2 text-primary">Members</h3>
        <div className="mt-4">
          {data.memberships.length === 0 ? (
            <p className="text-body text-secondary">No members.</p>
          ) : (
            <Table
              caption="Members"
              columns={membershipColumns}
              rows={data.memberships}
              rowKey={(m) => m.id}
              renderMobileCard={(m) => (
                <>
                  <span className="block text-label text-primary">{m.email}</span>
                  <span className="text-caption text-secondary">{m.role}</span>
                </>
              )}
            />
          )}
        </div>
      </div>

      <div className="mt-10">
        <h3 className="text-h2 text-primary">Recent webhook events</h3>
        <div className="mt-4">
          {data.recent_webhook_events.length === 0 ? (
            <p className="text-body text-secondary">No webhook activity yet.</p>
          ) : (
            <Table
              caption="Recent webhook events"
              columns={eventColumns}
              rows={data.recent_webhook_events}
              rowKey={(e) => e.id}
              renderMobileCard={(e) => (
                <span className="block text-label text-primary">{e.event_type}</span>
              )}
            />
          )}
        </div>
      </div>
    </div>
  )
}
