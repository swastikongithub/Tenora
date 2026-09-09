/**
 * Subscription & Plans — UI spec §C.4 Page 4. Where the billing state machine
 * becomes visible: a tenant may have no subscription at all, or one in
 * TRIALING / ACTIVE / PAST_DUE / CANCELED.
 *
 * Two queries of deliberately different kinds, and this is the first page to mix
 * them (C2 §4.3):
 *   - `queryKeys.plans()` is GLOBAL — `/api/plans/` is in GLOBAL_PATHS, ships no
 *     X-Tenant-ID, and must NOT be dropped or refetched on a tenant switch.
 *   - `queryKeys.currentSubscription(tenantId)` is TENANT-SCOPED — switching
 *     tenant changes the key, so the previous tenant's subscription can never
 *     render under the new one.
 *
 * A 404 from `/subscriptions/current/` is NOT an error: it is the backend saying
 * this tenant has no subscription yet, which is a legitimate empty state. Only a
 * non-404 failure gets the retry treatment.
 *
 * CANCELED is terminal (master spec §B.5). No reactivate control exists here —
 * not a disabled one, none at all, because no such transition exists to attempt.
 * Plan selection is also closed off once CANCELED: the backend rejects it
 * (`SubscriptionService.change_plan` raises IllegalStateTransition), and this
 * page simply stops offering it.
 *
 * Cancellation (docs/cancellation-spec.md) is the one destructive action here:
 * an OWNER-only "Cancel subscription" control in a danger-zone footer on the
 * panel, behind a type-to-confirm modal. It sends `PATCH {status: "CANCELED"}` —
 * the only place this page sends a `status` field; a plan *change* still sends
 * `plan_id` only. `IsTenantOwner` on the backend is the real boundary.
 *
 * Subscribing (D2, stage-d2-spec.md) no longer creates a local row. Selecting a
 * plan when there's no subscription: POST /subscriptions/current/checkout/ →
 * Razorpay Checkout opens → on success, POST /confirm-checkout/ and show an
 * honest "processing" state. Local activation waits for D3's webhook. The
 * "processing" state is ephemeral (lost on reload) — a persistent, self-clearing
 * version is a D3 concern, once webhook-driven activation exists to clear it.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Alert, Badge, Button, Card, EmptyState, Skeleton } from '../components'
import type { BadgeVariant } from '../components'
import { apiClient } from '../lib/api-client'
import { ApiError } from '../lib/api-error'
import { formatDate, formatMoney } from '../lib/format'
import { queryKeys } from '../lib/query-keys'
import { useTenant } from '../lib/tenant'
import { CancelSubscriptionModal } from './CancelSubscriptionModal'
import { ChangePlanConfirmModal } from './ChangePlanConfirmModal'
import { PlanGrid } from './PlanGrid'
import {
  useRazorpayCheckout,
  type CheckoutSuccessPayload,
} from './useRazorpayCheckout'

export interface Plan {
  id: string
  name: string
  code: string
  price_cents: number
  currency: string
  interval: 'MONTHLY' | 'ANNUAL'
}

export type SubscriptionStatus =
  | 'TRIALING'
  | 'ACTIVE'
  | 'PAST_DUE'
  | 'CANCELED'

export interface Subscription {
  id: string
  plan: Plan
  status: SubscriptionStatus
  current_period_start: string
  current_period_end: string
  created_at: string
  updated_at: string
}

interface CheckoutStartResponse {
  razorpay_subscription_id: string
  razorpay_key_id: string
  plan: Plan
}

/** Ephemeral state of a just-started checkout (not persisted — see file header). */
type CheckoutState =
  | { kind: 'processing' }
  | { kind: 'canceled' }
  | { kind: 'failed'; message: string }
  | null

/** §C.4: ACTIVE success · TRIALING warning · PAST_DUE danger · CANCELED neutral. */
const STATUS_VARIANT: Record<SubscriptionStatus, BadgeVariant> = {
  ACTIVE: 'success',
  TRIALING: 'warning',
  PAST_DUE: 'danger',
  CANCELED: 'neutral',
}

const STATUS_LABEL: Record<SubscriptionStatus, string> = {
  ACTIVE: 'Active',
  TRIALING: 'Trialing',
  PAST_DUE: 'Past due',
  CANCELED: 'Canceled',
}

export function SubscriptionPage() {
  const { currentTenant, currentTenantId } = useTenant()
  // Client-side gating of plan selection is UX only — the server's
  // IsTenantOwner is the real boundary and rejects a MEMBER's POST/PATCH
  // regardless of what renders here.
  const isOwner = currentTenant?.role === 'OWNER'

  const queryClient = useQueryClient()
  const subscriptionKey = queryKeys.currentSubscription(currentTenantId ?? '∅')

  const [target, setTarget] = useState<Plan | null>(null)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [checkoutState, setCheckoutState] = useState<CheckoutState>(null)
  const { openCheckout } = useRazorpayCheckout()

  const {
    data: subscription,
    isPending: subPending,
    isError: subIsError,
    error: subError,
    refetch: refetchSubscription,
  } = useQuery({
    queryKey: subscriptionKey,
    queryFn: () => apiClient.get<Subscription>('/subscriptions/current/'),
    enabled: currentTenantId != null,
  })

  const {
    data: plans,
    isPending: plansPending,
    isError: plansIsError,
    refetch: refetchPlans,
  } = useQuery({
    queryKey: queryKeys.plans(),
    queryFn: () => apiClient.get<Plan[]>('/plans/'),
  })

  // A 404 means "no subscription yet" — an empty state, not a failure. Status
  // lives on ApiError.status; ApiError.code is an unrelated DRF string code and
  // must never be used for this.
  const noSubscription =
    subIsError && subError instanceof ApiError && subError.status === 404
  const subFailed = subIsError && !noSubscription

  const canceled = subscription?.status === 'CANCELED'
  // CANCELED closes plan selection: the §0 backend guard rejects a plan change
  // on a terminal subscription, and hiding the control keeps the UI honest
  // about it rather than offering an action the server will refuse.
  const canManage = Boolean(isOwner && currentTenantId) && !canceled
  // The cancel action: OWNER only, only when there is a non-canceled
  // subscription to cancel. Client-side hiding is UX — IsTenantOwner and the
  // LEGAL_TRANSITIONS guard on the backend are the real boundaries.
  const canCancel = Boolean(isOwner && currentTenantId && subscription) && !canceled

  async function changePlan(plan: Plan) {
    setSubmitting(true)
    setActionError(null)
    try {
      // Body is `plan_id` only — never tenant_id (the api-client's
      // assertNoTenantInBody guard throws on it), and never status.
      await apiClient.patch<Subscription>('/subscriptions/current/', {
        plan_id: plan.id,
      })
      setSubmitting(false)
      setTarget(null)
      void queryClient.invalidateQueries({ queryKey: subscriptionKey })
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  async function startCheckout(plan: Plan) {
    setSubmitting(true)
    setActionError(null)
    setCheckoutState(null)
    try {
      const { razorpay_subscription_id, razorpay_key_id } =
        await apiClient.post<CheckoutStartResponse>(
          '/subscriptions/current/checkout/',
          { plan_id: plan.id },
        )
      setSubmitting(false)
      openCheckout({
        keyId: razorpay_key_id,
        subscriptionId: razorpay_subscription_id,
        planName: plan.name,
        workspaceName: currentTenant?.name ?? 'this workspace',
        onConfirmed: (payload) => void confirmCheckout(payload),
        onDismissed: () => setCheckoutState({ kind: 'canceled' }),
        onFailed: (message) => setCheckoutState({ kind: 'failed', message }),
      })
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  async function confirmCheckout(payload: CheckoutSuccessPayload) {
    try {
      // The backend only verifies the handshake — it does NOT activate
      // anything. "processing", never "active".
      await apiClient.post('/subscriptions/current/confirm-checkout/', payload)
      setCheckoutState({ kind: 'processing' })
    } catch {
      // The success callback didn't verify server-side. We don't claim a
      // payment we can't confirm — D3's webhook stays the authoritative path
      // regardless of what shows here.
      setCheckoutState({
        kind: 'failed',
        message:
          'We couldn’t verify the checkout. If you completed a payment it will still be applied once confirmed; otherwise please try again.',
      })
    }
  }

  async function cancelSubscription() {
    setSubmitting(true)
    setActionError(null)
    try {
      // Body is `status` only — never tenant_id (assertNoTenantInBody guards
      // it), never plan_id. This is the one PATCH on this page that sends a
      // status field.
      await apiClient.patch<Subscription>('/subscriptions/current/', {
        status: 'CANCELED',
      })
      setSubmitting(false)
      setCancelOpen(false)
      void queryClient.invalidateQueries({ queryKey: subscriptionKey })
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  function handleSelect(plan: Plan) {
    setActionError(null)
    setCheckoutState(null)
    if (noSubscription) {
      // No local row is created here — this opens Razorpay Checkout. The real
      // subscription is created later, by D3's webhook (stage-d2-spec.md §1).
      void startCheckout(plan)
      return
    }
    if (subscription && plan.id === subscription.plan.id) return
    setTarget(plan)
  }

  return (
    <section className="mx-auto max-w-3xl">
      <h1 className="text-display text-primary">Subscription</h1>
      <p className="mt-1 text-body text-secondary">
        This workspace’s plan and billing state.
      </p>

      {!currentTenantId ? (
        <div className="mt-6">
          <Alert variant="info">
            <Link
              to="/workspace"
              className="font-medium text-accent-500 underline-offset-2 hover:underline"
            >
              Choose a workspace
            </Link>{' '}
            to see its subscription.
          </Alert>
        </div>
      ) : (
        <>
          <div className="mt-6">
            {subPending ? (
              <Skeleton count={1} height={148} label="Loading subscription" />
            ) : subFailed ? (
              <Alert
                variant="danger"
                action={
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => refetchSubscription()}
                  >
                    Retry
                  </Button>
                }
              >
                Couldn’t load this workspace’s subscription.
              </Alert>
            ) : noSubscription && checkoutState?.kind === 'processing' ? (
              <Card>
                <EmptyState
                  headline="Payment received — activating your subscription"
                  description="This won’t update automatically yet. Once your payment is confirmed, refresh to see the active subscription."
                />
                <div className="mt-4">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => refetchSubscription()}
                  >
                    Refresh
                  </Button>
                </div>
              </Card>
            ) : noSubscription ? (
              <Card>
                <EmptyState
                  headline="No active subscription"
                  description={
                    isOwner
                      ? 'Choose a plan below to start billing for this workspace.'
                      : 'An owner of this workspace can start one.'
                  }
                />
              </Card>
            ) : subscription ? (
              <Card
                title={subscription.plan.name}
                actions={
                  <Badge variant={STATUS_VARIANT[subscription.status]}>
                    {STATUS_LABEL[subscription.status]}
                  </Badge>
                }
              >
                <dl className="flex flex-col gap-3 sm:flex-row sm:gap-10">
                  <div>
                    <dt className="text-caption text-secondary">Plan</dt>
                    <dd className="mt-1 font-mono text-body text-primary">
                      {subscription.plan.code}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-caption text-secondary">Price</dt>
                    <dd className="num mt-1 text-body text-primary">
                      {formatMoney(
                        subscription.plan.price_cents,
                        subscription.plan.currency,
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-caption text-secondary">
                      Current period
                    </dt>
                    <dd className="mt-1 text-body text-primary">
                      {formatDate(subscription.current_period_start)} —{' '}
                      {formatDate(subscription.current_period_end)}
                    </dd>
                  </div>
                </dl>

                {canceled && (
                  <p className="mt-4 text-caption text-secondary">
                    This subscription is canceled. Canceled subscriptions are
                    final — starting again isn’t available.
                  </p>
                )}

                {canCancel && (
                  <div className="mt-6 border-t border-subtle pt-4">
                    <p className="text-caption text-secondary">
                      Canceling is permanent — the subscription can’t be
                      reactivated or replaced afterward.
                    </p>
                    <div className="mt-3">
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => {
                          setActionError(null)
                          setCancelOpen(true)
                        }}
                      >
                        Cancel subscription
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            ) : null}
          </div>

          {checkoutState?.kind !== 'processing' && (
          <div className="mt-10">
            <h2 className="text-h2 text-primary">Plans</h2>
            <p className="mt-1 text-body text-secondary">
              {canManage
                ? 'Select a plan to apply it to this workspace.'
                : 'Available plans for this workspace.'}
            </p>

            {actionError && (
              <div className="mt-4">
                <Alert variant="danger">{actionError}</Alert>
              </div>
            )}

            {checkoutState?.kind === 'canceled' && (
              <div className="mt-4">
                <Alert variant="info">
                  Checkout was closed before payment — nothing changed. Select a
                  plan to try again.
                </Alert>
              </div>
            )}
            {checkoutState?.kind === 'failed' && (
              <div className="mt-4">
                <Alert variant="danger">{checkoutState.message}</Alert>
              </div>
            )}

            <div className="mt-4">
              {plansPending ? (
                <Skeleton count={3} height={132} label="Loading plans" />
              ) : plansIsError ? (
                <Alert
                  variant="danger"
                  action={
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => refetchPlans()}
                    >
                      Retry
                    </Button>
                  }
                >
                  Couldn’t load the available plans.
                </Alert>
              ) : plans.length === 0 ? (
                <Alert variant="warning">
                  No plans available. Billing can’t be set up until a plan is
                  configured.
                </Alert>
              ) : (
                <PlanGrid
                  plans={plans}
                  currentPlanId={subscription?.plan.id}
                  onSelect={canManage ? handleSelect : undefined}
                  busy={submitting}
                />
              )}
            </div>
          </div>
          )}
        </>
      )}

      <ChangePlanConfirmModal
        target={target}
        current={subscription?.plan ?? null}
        submitting={submitting}
        error={actionError}
        onConfirm={() => target && void changePlan(target)}
        onClose={() => {
          setTarget(null)
          setActionError(null)
        }}
      />

      <CancelSubscriptionModal
        open={cancelOpen}
        workspaceName={currentTenant?.name ?? ''}
        submitting={submitting}
        error={actionError}
        onConfirm={() => void cancelSubscription()}
        onClose={() => {
          setCancelOpen(false)
          setActionError(null)
        }}
      />
    </section>
  )
}

/**
 * Error ladder, same order as `AddMemberModal`: a field error first (the backend
 * keys every plan-change rejection — unknown plan, inactive plan, and the §0
 * terminal-subscription guard — to `plan_id`; a cancellation rejected by the
 * LEGAL_TRANSITIONS guard, e.g. an already-CANCELED subscription hit via a stale
 * render, comes back keyed to `status`), then the status-specific cases, then
 * the server's own message, then a generic fallback.
 */
function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.fieldErrors.plan_id?.length) return cause.fieldErrors.plan_id[0]
    if (cause.fieldErrors.status?.length) return cause.fieldErrors.status[0]
    if (cause.status === 403) {
      return 'You don’t have permission to change this workspace’s subscription.'
    }
    if (cause.status === 0) {
      return 'Couldn’t reach the server. Check your connection and try again.'
    }
    if (cause.message) return cause.message
  }
  return 'The server had a problem updating the subscription. Try again.'
}
