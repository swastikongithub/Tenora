/**
 * /admin/tenants/:id — one tenant's operator view: tenant info, memberships,
 * subscription, and its most recent normalized webhook events (sanitized —
 * never raw_payload). Phase 2 adds the subscription override controls
 * (docs/operator-control-plane-spec.md §E): plan change and status
 * transition, both confirm-before-mutate, both calling PATCH
 * /api/platform/subscriptions/detail/?id= — the same
 * SubscriptionService.change_plan / .transition_status the tenant-facing
 * app uses. Nothing here decides which transitions are legal; the backend
 * does, and an illegal one comes back as a plain error the modal shows.
 *
 * Phase 5 adds the Root-only suspend/reactivate control. It is deliberately
 * kept apart from the subscription overrides above it, visually and in the
 * copy: suspending a workspace is an ACCESS decision that changes no billing
 * state, and an operator must never reach for one believing it does the other.
 */

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Alert, Badge, Button, DataList, Modal, Skeleton, Table } from '../../components'
import type { BadgeVariant, Column } from '../../components'
import { useCurrentUser } from '../../components/layout/use-current-user'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-error'
import { formatDate, formatMoney } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import type { SubscriptionStatus } from '../SubscriptionPage'
import { SubscriptionOverrideModal } from './SubscriptionOverrideModal'

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

interface PlatformPlan {
  id: string
  name: string
  code: string
  is_active: boolean
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const STATUS_VARIANT: Record<SubscriptionStatus, BadgeVariant> = {
  ACTIVE: 'success',
  TRIALING: 'warning',
  PAST_DUE: 'danger',
  CANCELED: 'neutral',
}

const ALL_STATUSES: SubscriptionStatus[] = ['TRIALING', 'ACTIVE', 'PAST_DUE', 'CANCELED']

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

function messageFor(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : 'Something went wrong. Please try again.'
}

interface PendingOverride {
  kind: 'plan' | 'status'
  toValue: string
  toLabel: string
}

export function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const { isRoot } = useCurrentUser()

  const [suspendOpen, setSuspendOpen] = useState(false)
  const [planChoice, setPlanChoice] = useState('')
  const [statusChoice, setStatusChoice] = useState<'' | SubscriptionStatus>('')
  const [pending, setPending] = useState<PendingOverride | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const tenant = useQuery({
    queryKey: queryKeys.platformTenantDetail(id ?? ''),
    queryFn: () => apiClient.get<TenantDetail>(`/platform/tenants/detail/?id=${id}`),
    enabled: Boolean(id),
  })

  // Only fetched once a subscription exists — the plan-change control has
  // nothing to offer otherwise.
  const plans = useQuery({
    queryKey: queryKeys.platformPlans({ is_active: 'true' }),
    queryFn: () =>
      apiClient.get<PaginatedResponse<PlatformPlan>>('/platform/plans/?is_active=true'),
    enabled: Boolean(tenant.data?.subscription),
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
  const subscription = data.subscription

  async function confirmOverride() {
    if (!pending || !subscription) return
    setSubmitting(true)
    setActionError(null)
    try {
      await apiClient.patch(
        `/platform/subscriptions/detail/?id=${subscription.id}`,
        pending.kind === 'plan'
          ? { plan_id: pending.toValue }
          : { status: pending.toValue },
      )
      setSubmitting(false)
      setPending(null)
      setPlanChoice('')
      setStatusChoice('')
      // Refetch — the subscription/tenant queries this page (and the
      // tenant list) depend on, so the new state shows up immediately
      // rather than waiting for a stale cache to expire.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.platformTenantDetail(id ?? ''),
      })
      void queryClient.invalidateQueries({
        queryKey: ['global', 'platform', 'tenants'],
      })
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  async function setTenantActive(nextActive: boolean) {
    setSubmitting(true)
    setActionError(null)
    try {
      await apiClient.patch(`/platform/tenants/detail/?id=${id}`, {
        is_active: nextActive,
      })
      setSubmitting(false)
      setSuspendOpen(false)
      void queryClient.invalidateQueries({
        queryKey: queryKeys.platformTenantDetail(id ?? ''),
      })
      void queryClient.invalidateQueries({
        queryKey: ['global', 'platform', 'tenants'],
      })
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  const availablePlans = (plans.data?.results ?? []).filter(
    (p) => p.id !== subscription?.plan.id,
  )
  const availableStatuses = ALL_STATUSES.filter((s) => s !== subscription?.status)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-h2 text-primary">{data.name}</h2>
        <Badge variant={data.is_active ? 'success' : 'danger'}>
          {data.is_active ? 'Active' : 'Suspended'}
        </Badge>
      </div>
      <p className="mt-1 font-mono text-caption text-secondary">{data.slug}</p>

      {!data.is_active && (
        <Alert variant="warning" className="mt-4 max-w-[42rem]">
          This workspace is suspended. Its members are refused at sign-in to
          this tenant; billing is untouched and the subscription is unchanged.
        </Alert>
      )}

      <DataList
        className="mt-6 max-w-[42rem]"
        rows={[
          { term: 'Created', children: formatDate(data.created_at) },
          {
            term: 'Plan',
            children: subscription ? subscription.plan.name : '—',
          },
          {
            term: 'Subscription status',
            children: subscription ? (
              <Badge variant={STATUS_VARIANT[subscription.status]}>
                {subscription.status}
              </Badge>
            ) : (
              <span className="text-secondary">No subscription</span>
            ),
          },
          {
            term: 'Price',
            children: subscription
              ? formatMoney(subscription.plan.price_cents, subscription.plan.currency)
              : '—',
          },
        ]}
      />

      {subscription && (
        <div className="mt-6 max-w-[42rem] rounded-md border border-subtle bg-raised p-4">
          <p className="text-label font-medium text-primary">Operator overrides</p>
          <p className="mt-1 text-caption text-secondary">
            Calls the same subscription service the tenant-facing app uses —
            an illegal transition is rejected, never silently applied. Errors
            render inside the confirm dialog, the same as every other
            mutating control on this surface.
          </p>

          <div className="mt-4 flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="plan-override-select" className="text-label text-secondary">
                Change plan
              </label>
              <select
                id="plan-override-select"
                value={planChoice}
                onChange={(e) => setPlanChoice(e.target.value)}
                className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
              >
                <option value="">Select a plan…</option>
                {availablePlans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <Button
              size="sm"
              variant="secondary"
              disabled={!planChoice}
              onClick={() => {
                const target = availablePlans.find((p) => p.id === planChoice)
                if (!target) return
                setActionError(null)
                setPending({ kind: 'plan', toValue: target.id, toLabel: target.name })
              }}
            >
              Apply
            </Button>
          </div>

          <div className="mt-4 flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="status-override-select" className="text-label text-secondary">
                Transition status
              </label>
              <select
                id="status-override-select"
                value={statusChoice}
                onChange={(e) => setStatusChoice(e.target.value as '' | SubscriptionStatus)}
                className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
              >
                <option value="">Select a status…</option>
                {availableStatuses.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <Button
              size="sm"
              variant="secondary"
              disabled={!statusChoice}
              onClick={() => {
                if (!statusChoice) return
                setActionError(null)
                setPending({ kind: 'status', toValue: statusChoice, toLabel: statusChoice })
              }}
            >
              Apply
            </Button>
          </div>
        </div>
      )}

      {isRoot && (
        <div className="mt-6 max-w-[42rem] rounded-md border border-subtle bg-raised p-4">
          <p className="text-label font-medium text-primary">Workspace access</p>
          <p className="mt-1 text-caption text-secondary">
            Root-only. Suspending blocks every member of this tenant at the
            authentication boundary. It changes no subscription, calls no
            payment gateway, and stops no billing — that is a separate
            decision.
          </p>
          <div className="mt-4">
            <Button
              size="sm"
              variant={data.is_active ? 'danger' : 'secondary'}
              onClick={() => {
                setActionError(null)
                setSuspendOpen(true)
              }}
            >
              {data.is_active ? 'Suspend workspace' : 'Reactivate workspace'}
            </Button>
          </div>
        </div>
      )}

      <Modal
        open={suspendOpen}
        onClose={() => setSuspendOpen(false)}
        title={data.is_active ? 'Suspend workspace' : 'Reactivate workspace'}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setSuspendOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              variant={data.is_active ? 'danger' : 'primary'}
              loading={submitting}
              onClick={() => setTenantActive(!data.is_active)}
            >
              {data.is_active ? 'Suspend' : 'Reactivate'}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {actionError && <Alert variant="danger">{actionError}</Alert>}
          <p className="text-body text-secondary">
            {data.is_active ? (
              <>
                Every member of{' '}
                <strong className="text-primary">{data.name}</strong> —{' '}
                {data.memberships.length === 1
                  ? '1 account'
                  : `${data.memberships.length} accounts`}{' '}
                — will be refused access to this workspace until it is
                reactivated. They can still sign in and see their other
                workspaces.
              </>
            ) : (
              <>
                <strong className="text-primary">{data.name}</strong> becomes
                reachable again for its members immediately.
              </>
            )}
          </p>
          <p className="text-caption text-secondary">
            No subscription, invoice or gateway state changes either way.
          </p>
        </div>
      </Modal>

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

      {subscription && (
        <SubscriptionOverrideModal
          open={pending !== null}
          kind={pending?.kind ?? 'status'}
          tenantName={data.name}
          fromLabel={pending?.kind === 'plan' ? subscription.plan.name : subscription.status}
          toLabel={pending?.toLabel ?? ''}
          submitting={submitting}
          error={actionError}
          onConfirm={() => void confirmOverride()}
          onClose={() => {
            setPending(null)
            setActionError(null)
          }}
        />
      )}
    </div>
  )
}
