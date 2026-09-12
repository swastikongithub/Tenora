/**
 * /admin/billing-events — docs/operator-control-plane-spec.md §B: "Billing
 * Events," NOT a Payment/Invoice ledger. The repository has no Payment or
 * Invoice model and no captured amount field — this page is a read-model
 * treatment of the normalized webhook events that ARE payment-shaped
 * (CHARGED / PAYMENT_TROUBLE), sourced from the same sanitized
 * GET /api/platform/webhook-events/ endpoint the Webhooks page uses. No
 * amount/currency column exists because none is captured locally; the page
 * says so rather than omitting the gap silently.
 *
 * The backend's `event_type` filter accepts exactly one value (see
 * apps/platform/views.py) — there is no server-side "one of several types"
 * filter to build on. "All billing events" (the default) fetches the
 * unfiltered list and keeps only CHARGED/PAYMENT_TROUBLE rows from that
 * page client-side; picking a specific type below uses the server-side
 * filter exactly as specified. A light, disclosed simplification, not a new
 * backend capability.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Skeleton, Table } from '../../components'
import type { BadgeVariant, Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { toSearchParams } from './query-params'

type BillingEventType = 'CHARGED' | 'PAYMENT_TROUBLE'

interface WebhookEventRow {
  id: string
  external_event_id: string
  event_type: 'ACTIVATED' | 'CHARGED' | 'CANCELLED' | 'PAYMENT_TROUBLE' | 'UNKNOWN'
  external_subscription_id: string | null
  tenant: { id: string; name: string; slug: string } | null
  period_start: string | null
  period_end: string | null
  received_at: string
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const BILLING_EVENT_TYPES: BillingEventType[] = ['CHARGED', 'PAYMENT_TROUBLE']

const EVENT_LABEL: Record<BillingEventType, string> = {
  CHARGED: 'Charged',
  PAYMENT_TROUBLE: 'Payment trouble',
}

const EVENT_VARIANT: Record<BillingEventType, BadgeVariant> = {
  CHARGED: 'success',
  PAYMENT_TROUBLE: 'danger',
}

const columns: Array<Column<WebhookEventRow>> = [
  {
    key: 'tenant',
    header: 'Tenant',
    render: (e) => e.tenant?.name ?? <span className="text-secondary">Unmatched</span>,
  },
  {
    key: 'event_type',
    header: 'Event',
    render: (e) => (
      <Badge variant={EVENT_VARIANT[e.event_type as BillingEventType]}>
        {EVENT_LABEL[e.event_type as BillingEventType]}
      </Badge>
    ),
  },
  {
    key: 'period',
    header: 'Billing period',
    render: (e) =>
      e.period_start && e.period_end
        ? `${formatDate(e.period_start)} – ${formatDate(e.period_end)}`
        : '—',
  },
  { key: 'received_at', header: 'Received', render: (e) => formatDate(e.received_at) },
  {
    key: 'external_subscription_id',
    header: 'Gateway subscription',
    render: (e) => (
      <span className="font-mono text-caption">{e.external_subscription_id ?? '—'}</span>
    ),
  },
]

export function BillingEventsPage() {
  const [eventType, setEventType] = useState<'' | BillingEventType>('')

  const params = { event_type: eventType || undefined }
  const events = useQuery({
    queryKey: queryKeys.platformWebhookEvents({ ...params, billingEvents: 'true' }),
    queryFn: () =>
      apiClient.get<PaginatedResponse<WebhookEventRow>>(
        `/platform/webhook-events/${toSearchParams(params)}`,
      ),
  })

  const rows = eventType
    ? (events.data?.results ?? [])
    : (events.data?.results ?? []).filter((e) =>
        BILLING_EVENT_TYPES.includes(e.event_type as BillingEventType),
      )

  return (
    <div>
      <h2 className="text-h2 text-primary">Billing Events</h2>
      <p className="mt-1 text-body text-secondary">
        Charge and payment-trouble activity, from normalized gateway webhook events.
      </p>
      <Alert variant="info" className="mt-4">
        Amounts aren’t captured locally — use the gateway subscription id below to look
        the transaction up in your payment gateway’s dashboard.
      </Alert>

      <div className="mt-4 flex flex-col gap-1.5" style={{ maxWidth: '16rem' }}>
        <label htmlFor="billing-event-type-filter" className="text-label text-secondary">
          Event type
        </label>
        <select
          id="billing-event-type-filter"
          value={eventType}
          onChange={(e) => setEventType(e.target.value as '' | BillingEventType)}
          className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
        >
          <option value="">All billing events</option>
          {BILLING_EVENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {EVENT_LABEL[t]}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-6">
        {events.isPending ? (
          <Skeleton count={5} height={52} label="Loading billing events" />
        ) : events.isError ? (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => events.refetch()}>
                Retry
              </Button>
            }
          >
            Couldn’t load billing events.
          </Alert>
        ) : rows.length > 0 ? (
          <Table
            caption="Billing events"
            columns={columns}
            rows={rows}
            rowKey={(e) => e.id}
            renderMobileCard={(e) => (
              <>
                <span className="block text-label text-primary">
                  {e.tenant?.name ?? 'Unmatched'}
                </span>
                <Badge variant={EVENT_VARIANT[e.event_type as BillingEventType]}>
                  {EVENT_LABEL[e.event_type as BillingEventType]}
                </Badge>
              </>
            )}
          />
        ) : (
          <p className="text-body text-secondary">No billing events yet.</p>
        )}
      </div>
    </div>
  )
}
