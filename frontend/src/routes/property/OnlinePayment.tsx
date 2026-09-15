/**
 * P9 online resident payments — the resident's "Pay online" panel, the result
 * banner after returning from Cashfree checkout, and the owner's refund list.
 *
 * Nothing here decides an amount, a payer or an outcome. The panel shows what
 * the bill's `online_payment` block (server-computed) allows; clicking asks the
 * backend to start a checkout and hands the returned session to Cashfree. The
 * result banner polls OUR status endpoint — a successful redirect alone is
 * never shown as "paid".
 */

import { useMutation } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert, Button, Table } from '../../components'
import { apiClient } from '../../lib/api-client'
import { openCashfreeCheckout } from '../../lib/property/cashfree'
import { errorMessage } from '../../lib/property/errors'
import { formatDay, formatPeriod, money } from '../../lib/property/format'
import { useInvalidateProperty, usePropertyQuery } from '../../lib/property/hooks'
import type { BillDetail, OnlinePaymentAttempt, Paginated } from '../../lib/property/types'
import { Section } from './ui'

/** Poll for at most ~2 minutes; after that the banner says to check back. */
const POLL_MS = 2000
const MAX_POLLS = 60

export function PayOnlinePanel({ bill }: { bill: BillDetail }) {
  const block = bill.online_payment
  const [error, setError] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)

  const start = useMutation({
    mutationFn: () => apiClient.post<OnlinePaymentAttempt>(`/bills/${bill.id}/online-payment/`),
    onMutate: () => setError(null),
    onSuccess: async (attempt) => {
      if (!attempt.payment_session_id || !attempt.checkout_mode) {
        setError('Checkout could not be opened. Try again.')
        return
      }
      setOpening(true)
      try {
        await openCashfreeCheckout(attempt.payment_session_id, attempt.checkout_mode)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Checkout could not be opened. Try again.')
        setOpening(false)
      }
    },
    onError: (cause) => setError(errorMessage(cause, 'Couldn’t start the payment. Try again.')),
  })

  if (!block || block.reason === 'DISABLED' || block.reason === 'NOT_RESIDENT' || block.reason === 'NOTHING_DUE') return null
  if (block.reason === 'CURRENCY_NOT_SUPPORTED') return null
  if (block.reason === 'PHONE_REQUIRED') {
    return (
      <Alert variant="info" className="mt-6">
        To pay this bill online, add a 10-digit mobile number in{' '}
        <Link to="/settings" className="underline">
          Settings
        </Link>
        .
      </Alert>
    )
  }

  const inProgress = block.open_attempt?.display_state === 'processing'
  const busy = start.isPending || opening
  return (
    <section aria-labelledby="pay-online-heading" className="mt-6 rounded-lg border border-subtle bg-raised p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 id="pay-online-heading" className="text-h2 text-primary">
            Pay online
          </h2>
          <p className="mt-1 text-body text-secondary">
            {inProgress
              ? 'A checkout for this bill is already open. Continue to finish paying.'
              : 'Pay the full amount due with UPI, card or net banking through Cashfree.'}
          </p>
        </div>
        <Button onClick={() => start.mutate()} loading={busy} disabled={busy}>
          {inProgress ? 'Continue payment' : `Pay ${money(block.amount_cents, block.currency)} online`}
        </Button>
      </div>
      {error && (
        <Alert variant="danger" className="mt-4">
          {error}
        </Alert>
      )}
    </section>
  )
}

const RESULT_COPY: Record<OnlinePaymentAttempt['display_state'], { variant: 'info' | 'success' | 'warning' | 'danger'; title: string }> = {
  processing: { variant: 'info', title: 'Payment processing' },
  succeeded: { variant: 'success', title: 'Payment successful' },
  failed: { variant: 'danger', title: 'Payment failed' },
  expired: { variant: 'warning', title: 'Payment expired' },
  already_paid: { variant: 'info', title: 'Payment already completed' },
  needs_review: { variant: 'warning', title: 'Payment needs review' },
}

export function OnlinePaymentResult({ attemptId }: { attemptId: string }) {
  const [, setParams] = useSearchParams()
  const invalidate = useInvalidateProperty()
  const settledRef = useRef(false)
  const [polls, setPolls] = useState(0)
  const status = usePropertyQuery<OnlinePaymentAttempt>('online-payment', `/online-payments/${attemptId}/`, {}, {
    refetchInterval: (query) =>
      query.state.data?.display_state === 'processing' && query.state.dataUpdateCount < MAX_POLLS ? POLL_MS : false,
    retry: false,
  })
  const attempt = status.data

  useEffect(() => {
    if (status.dataUpdatedAt) setPolls((n) => n + 1)
  }, [status.dataUpdatedAt])

  useEffect(() => {
    if (!attempt || attempt.display_state === 'processing' || settledRef.current) return
    settledRef.current = true
    // The server has a final answer: refresh the bill, payments and receipts.
    void invalidate()
  }, [attempt, invalidate])

  const dismiss = () =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete('online_payment')
        return next
      },
      { replace: true },
    )

  if (status.error) {
    return (
      <Alert variant="warning" className="mb-4" action={<Button size="sm" variant="secondary" onClick={dismiss}>Dismiss</Button>}>
        {errorMessage(status.error, 'We couldn’t load this payment’s status.')}
      </Alert>
    )
  }
  if (!attempt) {
    return (
      <Alert variant="info" className="mb-4">
        Checking your payment…
      </Alert>
    )
  }
  const copy = RESULT_COPY[attempt.display_state]
  const stalled = attempt.display_state === 'processing' && polls >= MAX_POLLS
  return (
    <Alert
      variant={copy.variant}
      className="mb-4"
      action={
        attempt.display_state !== 'processing' ? (
          <Button size="sm" variant="secondary" onClick={dismiss}>
            Dismiss
          </Button>
        ) : undefined
      }
    >
      <span role="status" aria-live="polite">
        <strong className="font-medium">{copy.title}.</strong>{' '}
        {attempt.display_state === 'processing' &&
          'We’re confirming it with the payment provider — this updates automatically. Don’t pay again.'}
        {attempt.display_state === 'succeeded' && (
          <>
            {money(attempt.amount_cents, attempt.currency)} was received and your receipt is ready.{' '}
            {attempt.receipt_id && (
              <Link to={`/receipts/${attempt.receipt_id}`} className="underline">
                View receipt
              </Link>
            )}
          </>
        )}
        {attempt.display_state === 'failed' && `${attempt.failure_message || 'The payment didn’t go through.'} You can try again.`}
        {attempt.display_state === 'expired' && 'The checkout closed before payment. You can start a new payment.'}
        {attempt.display_state === 'already_paid' &&
          'This bill was already settled, so your online payment wasn’t applied. Your property owner will refund it.'}
        {attempt.display_state === 'needs_review' &&
          'We received your payment but couldn’t apply it automatically. Your property owner has been notified.'}
        {stalled && ' Still waiting — check back in a few minutes.'}
      </span>
    </Alert>
  )
}

/** Owner: online payments captured but not applied, with a refund action. */
export function OnlinePaymentsNeedingRefund() {
  const invalidate = useInvalidateProperty()
  const list = usePropertyQuery<Paginated<OnlinePaymentAttempt>>('online-payments', '/online-payments/', {
    status: 'UNAPPLIED,REFUND_PENDING',
  })
  const [error, setError] = useState<string | null>(null)
  const refund = useMutation({
    mutationFn: (id: string) => apiClient.post<OnlinePaymentAttempt>(`/online-payments/${id}/refund/`),
    onMutate: () => setError(null),
    onSuccess: () => invalidate(),
    onError: (cause) => setError(errorMessage(cause, 'The refund couldn’t be started.')),
  })
  const rows = list.data?.results ?? []
  if (rows.length === 0) return null
  return (
    <Section title="Online payments needing a refund">
      <p className="mb-3 max-w-[48rem] text-body text-secondary">
        These payments reached you through Cashfree after the bill was already settled or had changed, so they weren’t
        applied. Refund them to the resident.
      </p>
      {error && (
        <Alert variant="danger" className="mb-3">
          {error}
        </Alert>
      )}
      <Table
        caption="Online payments needing a refund"
        rows={rows}
        rowKey={(r) => r.id}
        columns={[
          { key: 'date', header: 'Received', render: (r) => formatDay(r.finalized_at ?? r.created_at) },
          { key: 'resident', header: 'Resident', render: (r) => `${r.resident_name ?? ''} · ${r.unit_identifier ?? ''}` },
          { key: 'bill', header: 'Bill', render: (r) => `${formatPeriod(r.period_start)}${r.bill_number ? ` · ${r.bill_number}` : ''}` },
          { key: 'amount', header: 'Amount', numeric: true, render: (r) => money(r.amount_cents, r.currency) },
          {
            key: 'action',
            header: '',
            render: (r) =>
              r.status === 'REFUND_PENDING' && r.refund_status === 'PENDING' ? (
                <span className="text-caption text-secondary">Refund pending</span>
              ) : (
                <Button size="sm" variant="secondary" loading={refund.isPending && refund.variables === r.id} onClick={() => refund.mutate(r.id)}>
                  Refund
                </Button>
              ),
          },
        ]}
      />
    </Section>
  )
}
