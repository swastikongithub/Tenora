/**
 * /admin/webhooks — every normalized webhook event, sanitized (never
 * raw_payload — see PlatformWebhookEventSerializer). No retry-sweep button
 * in Phase 1: docs/operator-control-plane-spec.md places the fallback sweep
 * controls in Phase 2, explicitly labeled temporary/fallback there.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Skeleton, Table } from '../../components'
import type { Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { toSearchParams } from './query-params'

type EventType = 'ACTIVATED' | 'CHARGED' | 'CANCELLED' | 'PAYMENT_TROUBLE' | 'UNKNOWN'

interface WebhookEventRow {
  id: string
  external_event_id: string
  event_type: EventType
  external_subscription_id: string | null
  tenant: { id: string; name: string; slug: string } | null
  received_at: string
  processed: boolean
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const EVENT_TYPES: EventType[] = [
  'ACTIVATED',
  'CHARGED',
  'CANCELLED',
  'PAYMENT_TROUBLE',
  'UNKNOWN',
]

const columns: Array<Column<WebhookEventRow>> = [
  {
    key: 'tenant',
    header: 'Tenant',
    render: (e) => e.tenant?.name ?? <span className="text-secondary">Unmatched</span>,
  },
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
  {
    key: 'external_event_id',
    header: 'Delivery ID',
    render: (e) => <span className="font-mono text-caption">{e.external_event_id}</span>,
  },
]

export function WebhooksPage() {
  const [eventType, setEventType] = useState<'' | EventType>('')
  const [processed, setProcessed] = useState<'' | 'true' | 'false'>('')

  const params = {
    event_type: eventType || undefined,
    processed: processed || undefined,
  }
  const events = useQuery({
    queryKey: queryKeys.platformWebhookEvents(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<WebhookEventRow>>(
        `/platform/webhook-events/${toSearchParams(params)}`,
      ),
  })

  return (
    <div>
      <h2 className="text-h2 text-primary">Webhooks</h2>
      <p className="mt-1 text-body text-secondary">
        Every normalized gateway webhook event received. Fallback retry controls for a
        backlog arrive in a later phase.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="webhook-event-type-filter" className="text-label text-secondary">
            Event type
          </label>
          <select
            id="webhook-event-type-filter"
            value={eventType}
            onChange={(e) => setEventType(e.target.value as '' | EventType)}
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="webhook-processed-filter" className="text-label text-secondary">
            Processed
          </label>
          <select
            id="webhook-processed-filter"
            value={processed}
            onChange={(e) => setProcessed(e.target.value as '' | 'true' | 'false')}
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            <option value="true">Processed</option>
            <option value="false">Pending</option>
          </select>
        </div>
      </div>

      <div className="mt-6">
        {events.isPending ? (
          <Skeleton count={6} height={52} label="Loading webhook events" />
        ) : events.isError ? (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => events.refetch()}>
                Retry
              </Button>
            }
          >
            Couldn’t load webhook events.
          </Alert>
        ) : events.data && events.data.results.length > 0 ? (
          <Table
            caption="Webhook events"
            columns={columns}
            rows={events.data.results}
            rowKey={(e) => e.id}
            renderMobileCard={(e) => (
              <>
                <span className="block text-label text-primary">
                  {e.tenant?.name ?? 'Unmatched'}
                </span>
                <span className="text-caption text-secondary">{e.event_type}</span>
              </>
            )}
          />
        ) : (
          <p className="text-body text-secondary">No webhook events match these filters.</p>
        )}
      </div>
    </div>
  )
}
