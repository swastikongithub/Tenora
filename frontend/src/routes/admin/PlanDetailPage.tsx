/**
 * /admin/plans/:id — one plan, and every operator action that targets it:
 * edit, archive/restore, and gateway sync (Phase 3 of
 * docs/operator-control-plane-spec.md §D).
 *
 * Three rules this page renders, all of them enforced server-side and
 * mirrored here only as UX:
 *
 *   - Once a plan has an external plan id it is LOCKED: only its name and
 *     active state may change. The edit form disables the rest and says why.
 *   - Sync is offered once, and only while the plan is unsynced — the external
 *     id is immutable after that, so there is no "re-sync" and no way to
 *     replace it.
 *   - Nothing is deleted, ever. Archive is the only retirement, and it leaves
 *     every subscription, checkout and proration record that references this
 *     plan intact.
 *
 * Sync has a real external side effect, so it is confirm-before-mutate. Edit
 * is its own form-modal submit. Archive/restore is confirm-before-mutate too:
 * archiving pulls a plan out of the tenant-facing catalogue.
 */

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Alert, Badge, Button, DataList, Modal, Skeleton } from '../../components'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-error'
import type { FieldErrors } from '../../lib/api-error'
import { formatMoney } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { PlanFormModal } from './PlanFormModal'
import type { PlanFormValues } from './PlanFormModal'

interface PlatformPlan {
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

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 502) {
      return 'The payment gateway could not complete this sync. Check the service logs and try again.'
    }
    return cause.message
  }
  return 'Something went wrong. Please try again.'
}

export function PlanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

  const [editOpen, setEditOpen] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [syncOpen, setSyncOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [syncResult, setSyncResult] = useState<string | null>(null)

  const plan = useQuery({
    queryKey: queryKeys.platformPlanDetail(id ?? ''),
    queryFn: () => apiClient.get<PlatformPlan>(`/platform/plans/detail/?id=${id}`),
    enabled: Boolean(id),
  })

  function refreshPlanQueries() {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.platformPlanDetail(id ?? ''),
    })
    void queryClient.invalidateQueries({ queryKey: ['global', 'platform', 'plans'] })
  }

  async function savePlan(values: PlanFormValues) {
    setSubmitting(true)
    setActionError(null)
    setFieldErrors({})
    try {
      await apiClient.patch(`/platform/plans/detail/?id=${id}`, values)
      setSubmitting(false)
      setEditOpen(false)
      refreshPlanQueries()
    } catch (cause) {
      setSubmitting(false)
      if (cause instanceof ApiError && Object.keys(cause.fieldErrors).length > 0) {
        setFieldErrors(cause.fieldErrors)
      } else {
        setActionError(messageFor(cause))
      }
    }
  }

  async function setActive(nextActive: boolean) {
    setSubmitting(true)
    setActionError(null)
    try {
      await apiClient.patch(`/platform/plans/detail/?id=${id}`, {
        is_active: nextActive,
      })
      setSubmitting(false)
      setArchiveOpen(false)
      refreshPlanQueries()
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  async function syncPlan() {
    setSubmitting(true)
    setActionError(null)
    setSyncResult(null)
    try {
      const result = await apiClient.post<PlatformPlan & { created: boolean }>(
        `/platform/plans/sync/?id=${id}`,
      )
      setSubmitting(false)
      setSyncOpen(false)
      setSyncResult(
        result.created
          ? `Synced — gateway plan ${result.external_plan_id}.`
          : 'Already synced — no change was made at the gateway.',
      )
      refreshPlanQueries()
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  if (plan.isPending) {
    return <Skeleton count={5} height={24} label="Loading plan" />
  }

  if (plan.isError) {
    return (
      <Alert
        variant="danger"
        action={
          <Button size="sm" variant="secondary" onClick={() => plan.refetch()}>
            Retry
          </Button>
        }
      >
        Couldn’t load this plan.
      </Alert>
    )
  }

  const data = plan.data
  if (!data) return null
  const locked = data.external_plan_id !== null

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-h2 text-primary">{data.name}</h2>
        <Badge variant={data.is_active ? 'success' : 'neutral'}>
          {data.is_active ? 'Active' : 'Archived'}
        </Badge>
        <Badge variant={locked ? 'success' : 'warning'}>
          {locked ? 'Synced' : 'Not synced'}
        </Badge>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setActionError(null)
            setFieldErrors({})
            setEditOpen(true)
          }}
        >
          Edit plan
        </Button>
        {!locked && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setActionError(null)
              setSyncOpen(true)
            }}
          >
            Sync to gateway
          </Button>
        )}
        <Button
          size="sm"
          variant={data.is_active ? 'danger' : 'secondary'}
          onClick={() => {
            setActionError(null)
            setArchiveOpen(true)
          }}
        >
          {data.is_active ? 'Archive plan' : 'Restore plan'}
        </Button>
      </div>

      {actionError && !editOpen && !archiveOpen && !syncOpen && (
        <Alert variant="danger" className="mt-4">
          {actionError}
        </Alert>
      )}
      {syncResult && !actionError && (
        <p className="mt-4 text-caption text-secondary" role="status">
          {syncResult}
        </p>
      )}

      {locked && (
        <p className="mt-4 max-w-[42rem] text-caption text-secondary">
          This plan is provisioned at the payment gateway, so its price,
          currency, interval and code are locked. A price change is a new plan
          with this one archived — never an edit in place, because
          subscriptions, checkouts and proration records already reference
          these values.
        </p>
      )}

      <DataList
        className="mt-6 max-w-[42rem]"
        rows={[
          { term: 'Code', children: <span className="font-mono">{data.code}</span> },
          { term: 'Price', children: formatMoney(data.price_cents, data.currency) },
          { term: 'Currency', children: data.currency },
          { term: 'Interval', children: data.interval },
          { term: 'Subscribers', children: data.subscriber_count },
          {
            term: 'External plan ID',
            children: data.external_plan_id ? (
              <span className="font-mono">{data.external_plan_id}</span>
            ) : (
              <span className="text-secondary">Not synced to the payment gateway yet</span>
            ),
          },
        ]}
      />

      <PlanFormModal
        open={editOpen}
        mode="edit"
        initial={{
          name: data.name,
          code: data.code,
          price_cents: data.price_cents,
          currency: data.currency,
          interval: data.interval,
        }}
        locked={locked}
        submitting={submitting}
        error={actionError}
        fieldErrors={fieldErrors}
        onSubmit={savePlan}
        onClose={() => setEditOpen(false)}
      />

      <Modal
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        title={data.is_active ? 'Archive plan' : 'Restore plan'}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setArchiveOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              variant={data.is_active ? 'danger' : 'primary'}
              loading={submitting}
              onClick={() => setActive(!data.is_active)}
            >
              {data.is_active ? 'Archive' : 'Restore'}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {actionError && <Alert variant="danger">{actionError}</Alert>}
          <p className="text-body text-secondary">
            {data.is_active ? (
              <>
                <strong className="text-primary">{data.name}</strong> stops
                being offered to tenants. Nothing is deleted:{' '}
                {data.subscriber_count === 1
                  ? 'the 1 subscription already on it'
                  : `the ${data.subscriber_count} subscriptions already on it`}{' '}
                and every historical billing record are untouched.
              </>
            ) : (
              <>
                <strong className="text-primary">{data.name}</strong> is offered
                to tenants again.
              </>
            )}
          </p>
        </div>
      </Modal>

      <Modal
        open={syncOpen}
        onClose={() => setSyncOpen(false)}
        title="Sync to gateway"
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setSyncOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button loading={submitting} onClick={syncPlan}>
              Sync now
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {actionError && <Alert variant="danger">{actionError}</Alert>}
          <p className="text-body text-secondary">
            This creates the matching plan at the configured payment gateway and
            stores the id it returns. It has a real external side effect and
            cannot be undone from here — the external id is immutable once set.
          </p>
          <p className="text-caption text-secondary">
            After syncing, this plan’s price, currency, interval and code are
            locked.
          </p>
        </div>
      </Modal>
    </div>
  )
}
