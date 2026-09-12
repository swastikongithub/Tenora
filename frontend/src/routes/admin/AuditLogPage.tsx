/**
 * /admin/audit-log — docs/operator-control-plane-spec.md §D. Phase 2
 * completes this page: GET /api/platform/audit-log/ now exists, backed by
 * the AuditEvent rows every critical/observational mutation on this
 * surface writes. Paginated, filterable (actor/action/target_type/
 * is_critical), newest first. Read-only — nothing here writes anything.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Input, Skeleton, Table } from '../../components'
import type { Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { toSearchParams } from './query-params'

interface AuditEventRow {
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

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// The action vocabulary Phase 2 actually writes — a plain <select>, not a
// free-text field, so a filter can't be typo'd into silently matching
// nothing. Extend this list as later phases add new critical/observational
// actions (docs/operator-control-plane-spec.md §B).
const ACTIONS = [
  "subscription.transitioned",
  "subscription.plan_changed",
  "webhook.sweep_triggered",
  "reconciliation.sweep_triggered",
  "usage.sweep_triggered",
]

const TARGET_TYPES = ["Subscription", "WebhookEvent", "Tenant"]

/**
 * A null actor has two different meanings, and an unlabelled dash for both
 * would hide one of them. `AuditEvent.actor` is SET_NULL, so a row can outlive
 * the account that made it — and since Phase 6, a scheduled sweep writes rows
 * with no actor at all because no human was involved (inventing a synthetic
 * "system" account to fill the column would put a fake user in the audit
 * trail). The target type is what separates the two.
 */
function actorLabel(event: AuditEventRow): string {
  if (event.actor) return event.actor.email
  return event.target_type === 'ScheduledTask' ? 'Scheduled' : '—'
}

const columns: Array<Column<AuditEventRow>> = [
  {
    key: 'created_at',
    header: 'When',
    render: (e) => <span className="whitespace-nowrap">{formatDate(e.created_at)}</span>,
  },
  {
    key: 'is_critical',
    header: 'Severity',
    render: (e) => (
      <Badge variant={e.is_critical ? 'danger' : 'neutral'}>
        {e.is_critical ? 'Critical' : 'Observational'}
      </Badge>
    ),
  },
  { key: 'actor', header: 'Actor', render: (e) => actorLabel(e) },
  { key: 'action', header: 'Action', render: (e) => <span className="font-mono text-caption">{e.action}</span> },
  {
    key: 'target',
    header: 'Target',
    render: (e) => (
      <span className="font-mono text-caption">
        {e.target_type}:{e.target_id}
      </span>
    ),
  },
  { key: 'summary', header: 'Summary' },
]

export function AuditLogPage() {
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')
  const [targetType, setTargetType] = useState('')
  const [criticalOnly, setCriticalOnly] = useState<'' | 'true' | 'false'>('')
  const [page, setPage] = useState(1)

  const params = {
    actor: actor || undefined,
    action: action || undefined,
    target_type: targetType || undefined,
    is_critical: criticalOnly || undefined,
    page: page > 1 ? String(page) : undefined,
  }

  const events = useQuery({
    queryKey: queryKeys.platformAuditLog(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<AuditEventRow>>(
        `/platform/audit-log/${toSearchParams(params)}`,
      ),
  })

  // Any filter change resets to page 1 — a stale page number combined with
  // a narrower filter could otherwise land past the new last page.
  function updateFilter(setter: (value: string) => void) {
    return (value: string) => {
      setPage(1)
      setter(value)
    }
  }

  return (
    <div>
      <h2 className="text-h2 text-primary">Audit Log</h2>
      <p className="mt-1 text-body text-secondary">
        Every recorded operator action, newest first. Critical mutations are
        written atomically with the action they describe; observational
        entries (fallback sweep triggers) are best-effort.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <Input
          label="Actor id"
          placeholder="User UUID"
          value={actor}
          onChange={(e) => updateFilter(setActor)(e.target.value)}
          className="w-56"
        />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="audit-action-filter" className="text-label text-secondary">
            Action
          </label>
          <select
            id="audit-action-filter"
            value={action}
            onChange={(e) => updateFilter(setAction)(e.target.value)}
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="audit-target-type-filter" className="text-label text-secondary">
            Target type
          </label>
          <select
            id="audit-target-type-filter"
            value={targetType}
            onChange={(e) => updateFilter(setTargetType)(e.target.value)}
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            {TARGET_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="audit-critical-filter" className="text-label text-secondary">
            Severity
          </label>
          <select
            id="audit-critical-filter"
            value={criticalOnly}
            onChange={(e) =>
              updateFilter(setCriticalOnly as (v: string) => void)(e.target.value)
            }
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            <option value="true">Critical only</option>
            <option value="false">Observational only</option>
          </select>
        </div>
      </div>

      <div className="mt-6">
        {events.isPending ? (
          <Skeleton count={6} height={52} label="Loading audit log" />
        ) : events.isError ? (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => events.refetch()}>
                Retry
              </Button>
            }
          >
            Couldn’t load the audit log.
          </Alert>
        ) : events.data && events.data.results.length > 0 ? (
          <Table
            caption="Audit log"
            columns={columns}
            rows={events.data.results}
            rowKey={(e) => e.id}
            renderMobileCard={(e) => (
              <>
                <span className="block text-label text-primary">{e.summary}</span>
                <span className="mt-1 flex items-center gap-2 text-caption text-secondary">
                  <Badge variant={e.is_critical ? 'danger' : 'neutral'}>
                    {e.is_critical ? 'Critical' : 'Observational'}
                  </Badge>
                  <span>{actorLabel(e)}</span>
                </span>
              </>
            )}
          />
        ) : (
          <p className="text-body text-secondary">No audit events match these filters.</p>
        )}
      </div>

      {events.data && events.data.results.length > 0 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="text-caption text-secondary">
            Page {page} · {events.data.count} total
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={!events.data.previous}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!events.data.next}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
