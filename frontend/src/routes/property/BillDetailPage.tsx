/**
 * /bills/:id — owner and resident. The backend decides visibility: a resident
 * asking for another resident's bill id gets a 404, rendered as "not found".
 */

import { useMutation } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { Alert, Button, Input, Modal } from '../../components'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-error'
import { METHOD_LABEL, money, toMinorUnits } from '../../lib/property/format'
import { useInvalidateProperty, usePropertyQuery, useWorkspaceRole } from '../../lib/property/hooks'
import type { BillDetail, LineItem } from '../../lib/property/types'
import { BillDetailView } from './BillDetailView'
import { OnlinePaymentResult, PayOnlinePanel } from './OnlinePayment'
import { DownloadPdfButton, QueryState, Select, TextArea } from './ui'
import { errorMessage, fieldError } from '../../lib/property/errors'

function newKey() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function ReasonModal({
  open,
  title,
  confirmLabel,
  description,
  onClose,
  onConfirm,
  danger = true,
}: {
  open: boolean
  title: string
  confirmLabel: string
  description: string
  onClose: () => void
  onConfirm: (reason: string) => Promise<unknown>
  danger?: boolean
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (open) {
      setReason('')
      setError(null)
      setBusy(false)
    }
  }, [open])
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!reason.trim()) {
      setError('A reason is required.')
      return
    }
    setBusy(true)
    try {
      await onConfirm(reason.trim())
      onClose()
    } catch (cause) {
      setError(errorMessage(cause))
      setBusy(false)
    }
  }
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="reason-form" variant={danger ? 'danger' : 'primary'} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <form id="reason-form" onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <p className="text-body text-secondary">{description}</p>
        {error && <Alert variant="danger">{error}</Alert>}
        <TextArea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
      </form>
    </Modal>
  )
}

function AddLineModal({ bill, open, onClose, onDone }: { bill: BillDetail; open: boolean; onClose: () => void; onDone: () => void }) {
  const [type, setType] = useState('MAINTENANCE')
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const mutation = useMutation({
    mutationFn: (body: object) => apiClient.post(`/bills/${bill.id}/line-items/`, body),
    onSuccess: () => {
      onDone()
      onClose()
    },
  })
  useEffect(() => {
    if (open) {
      setType('MAINTENANCE')
      setDescription('')
      setAmount('')
      mutation.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  const minor = toMinorUnits(amount)
  function submit(e: FormEvent) {
    e.preventDefault()
    if (minor === null || !description.trim()) return
    mutation.mutate({ type, description: description.trim(), amount_cents: minor })
  }
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add a charge"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="add-line-form" loading={mutation.isPending} disabled={minor === null || !description.trim()}>
            Add
          </Button>
        </>
      }
    >
      <form id="add-line-form" onSubmit={submit} className="flex flex-col gap-3" noValidate>
        {mutation.error && <Alert variant="danger">{errorMessage(mutation.error)}</Alert>}
        <Select label="Type" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="MAINTENANCE">Maintenance</option>
          <option value="OTHER_CHARGE">Other charge (parking, water, repairs…)</option>
          <option value="LATE_FEE">Late fee</option>
          <option value="DISCOUNT">Discount</option>
          <option value="ADJUSTMENT">Adjustment (use a minus sign for a credit)</option>
        </Select>
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} required />
        <Input
          label={`Amount (${bill.currency})`}
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={amount !== '' && minor === null}
          helperText={amount !== '' && minor === null ? 'Enter an amount like 500 or 500.50.' : 'Discounts are subtracted automatically.'}
        />
      </form>
    </Modal>
  )
}

function RecordPaymentModal({ bill, open, onClose, onDone }: { bill: BillDetail; open: boolean; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState('')
  const [method, setMethod] = useState('UPI')
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  // One key per opened form: a double-submit or retried request records once.
  const [key, setKey] = useState(newKey)
  const mutation = useMutation({
    mutationFn: (body: object) => apiClient.post(`/payments/`, body),
    onSuccess: () => {
      onDone()
      onClose()
    },
  })
  useEffect(() => {
    if (open) {
      setAmount((bill.amount_due_cents / 100).toFixed(2))
      setDate(new Date().toISOString().slice(0, 10))
      setMethod('UPI')
      setReference('')
      setNotes('')
      setKey(newKey())
      mutation.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  const minor = toMinorUnits(amount)
  function submit(e: FormEvent) {
    e.preventDefault()
    if (minor === null || minor <= 0) return
    mutation.mutate({
      bill_id: bill.id,
      amount_cents: minor,
      payment_date: date,
      method,
      reference,
      notes,
      idempotency_key: key,
    })
  }
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Record payment"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="payment-form" loading={mutation.isPending} disabled={minor === null || minor <= 0}>
            Record payment
          </Button>
        </>
      }
    >
      <form id="payment-form" onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <p className="text-body text-secondary">
          Balance due: <span className="font-mono">{money(bill.amount_due_cents, bill.currency)}</span>. A receipt is issued
          automatically.
        </p>
        {mutation.error && !fieldError(mutation.error, 'amount_cents') && !fieldError(mutation.error, 'reference') && (
          <Alert variant="danger">{errorMessage(mutation.error)}</Alert>
        )}
        <Input
          label={`Amount (${bill.currency})`}
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={Boolean(fieldError(mutation.error, 'amount_cents')) || (amount !== '' && minor === null)}
          helperText={fieldError(mutation.error, 'amount_cents') ?? 'Partial payments are allowed; overpayments are not.'}
        />
        <Input label="Payment date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <Select label="Method" value={method} onChange={(e) => setMethod(e.target.value)}>
          {Object.entries(METHOD_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Input
          label="Reference (UTR, cheque no.)"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          error={Boolean(fieldError(mutation.error, 'reference'))}
          helperText={fieldError(mutation.error, 'reference') ?? 'Optional. A reference can be recorded only once.'}
        />
        <TextArea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </form>
    </Modal>
  )
}

function CorrectionModal({ bill, open, onClose, onDone }: { bill: BillDetail; open: boolean; onClose: () => void; onDone: () => void }) {
  const electricity = useMemo(() => bill.line_items.filter((l) => l.type === 'ELECTRICITY'), [bill])
  const [kind, setKind] = useState<'AMOUNT_ADJUSTMENT' | 'READING_CORRECTION'>('AMOUNT_ADJUSTMENT')
  const [amount, setAmount] = useState('')
  const [lineId, setLineId] = useState('')
  const [closing, setClosing] = useState('')
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: (body: object) => apiClient.post(`/bills/${bill.id}/corrections/`, body),
    onSuccess: () => {
      onDone()
      onClose()
    },
  })
  useEffect(() => {
    if (open) {
      setKind('AMOUNT_ADJUSTMENT')
      setAmount('')
      setLineId(electricity[0]?.id ?? '')
      setClosing('')
      setReason('')
      mutation.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  const minor = toMinorUnits(amount)
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!reason.trim()) return
    if (kind === 'AMOUNT_ADJUSTMENT') {
      if (minor === null) return
      mutation.mutate({ kind, amount_cents: minor, reason })
    } else {
      mutation.mutate({ kind, line_item_id: lineId, corrected_closing_value: closing, reason })
    }
  }
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Correct published bill"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="correction-form" loading={mutation.isPending} disabled={!reason.trim()}>
            Apply correction
          </Button>
        </>
      }
    >
      <form id="correction-form" onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <p className="text-body text-secondary">
          Published bills are never edited in place. A correction adds a visible adjustment line and keeps the original
          values, your reason, and who made it.
        </p>
        {mutation.error && <Alert variant="danger">{errorMessage(mutation.error)}</Alert>}
        <Select label="Correction type" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="AMOUNT_ADJUSTMENT">Amount adjustment</option>
          {electricity.length > 0 && <option value="READING_CORRECTION">Meter reading correction</option>}
        </Select>
        {kind === 'AMOUNT_ADJUSTMENT' ? (
          <Input
            label={`Adjustment (${bill.currency}) — negative to reduce`}
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            error={amount !== '' && minor === null}
          />
        ) : (
          <>
            <Select label="Electricity line" value={lineId} onChange={(e) => setLineId(e.target.value)}>
              {electricity.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.meter_number} — closing {l.closing_reading_value}
                </option>
              ))}
            </Select>
            <Input label="Corrected closing reading" inputMode="decimal" value={closing} onChange={(e) => setClosing(e.target.value)} />
          </>
        )}
        <TextArea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
      </form>
    </Modal>
  )
}

export function BillDetailPage() {
  const { id = '' } = useParams()
  const { isOwner } = useWorkspaceRole()
  const invalidate = useInvalidateProperty()
  const query = usePropertyQuery<BillDetail>('bill', `/bills/${id}/`)
  const [searchParams] = useSearchParams()
  const returningAttempt = searchParams.get('online_payment')
  const [modal, setModal] = useState<null | 'line' | 'payment' | 'correction' | 'cancel' | 'publish-error'>(null)
  const [voidTarget, setVoidTarget] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const publish = useMutation({
    mutationFn: () => apiClient.post(`/bills/${id}/publish/`),
    onSuccess: () => invalidate(),
    onError: (e) => setActionError(errorMessage(e)),
  })
  const removeLine = useMutation({
    mutationFn: (line: LineItem) => apiClient.delete(`/bills/${id}/line-items/${line.id}/`),
    onSuccess: () => invalidate(),
    onError: (e) => setActionError(errorMessage(e)),
  })

  if (query.isLoading || query.error) {
    if (query.error instanceof ApiError && query.error.status === 404) {
      return (
        <Alert variant="warning">
          This bill doesn’t exist in this workspace. <Link to={isOwner ? '/billing/bills' : '/my-bills'} className="underline">Back to bills</Link>
        </Alert>
      )
    }
    return <QueryState isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} label="this bill" />
  }
  const bill = query.data
  if (!bill) return null

  const open = bill.status === 'PUBLISHED' || bill.status === 'PARTIALLY_PAID'
  const issued = open || bill.status === 'PAID'
  const ownerActions = isOwner ? (
    <div className="flex flex-wrap justify-end gap-2">
      {bill.status === 'DRAFT' && (
        <>
          <Button size="sm" variant="secondary" onClick={() => setModal('line')}>
            Add charge
          </Button>
          <Button size="sm" loading={publish.isPending} onClick={() => publish.mutate()}>
            Publish
          </Button>
        </>
      )}
      {open && (
        <Button size="sm" onClick={() => setModal('payment')}>
          Record payment
        </Button>
      )}
      {issued && (
        <Button size="sm" variant="secondary" onClick={() => setModal('correction')}>
          Correct
        </Button>
      )}
      {bill.status !== 'CANCELLED' && bill.amount_paid_cents === 0 && (
        <Button size="sm" variant="ghost" onClick={() => setModal('cancel')}>
          Cancel bill
        </Button>
      )}
    </div>
  ) : null

  return (
    <div className="max-w-[960px]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2 text-label">
        <Link to={isOwner ? '/billing/bills' : '/billing-history'} className="text-secondary hover:text-primary">
          ← Bills
        </Link>
        {bill.published_at && bill.bill_number && (
          <DownloadPdfButton path={`/bills/${bill.id}/pdf/`} filename={`${bill.bill_number}.pdf`} />
        )}
      </div>
      {actionError && (
        <Alert variant="danger" className="mb-4">
          {actionError}
        </Alert>
      )}
      {returningAttempt && <OnlinePaymentResult attemptId={returningAttempt} />}
      <BillDetailView
        bill={bill}
        mode={isOwner ? 'owner' : 'resident'}
        proofPath={(readingId) => `/meter-readings/${readingId}/proof/`}
        actions={ownerActions}
        onRemoveLine={(line) => removeLine.mutate(line)}
      />
      {!isOwner && <PayOnlinePanel bill={bill} />}

      {isOwner && bill.payments.some((p) => p.status === 'COMPLETED' && p.method !== 'ONLINE') && (
        <div className="mt-4 flex flex-wrap gap-2">
          {bill.payments
            // Online payments are reversed by a provider refund, never voided (P9).
            .filter((p) => p.status === 'COMPLETED' && p.method !== 'ONLINE')
            .map((p) => (
              <Button key={p.id} size="sm" variant="ghost" onClick={() => setVoidTarget(p.id)}>
                Void {money(p.amount_cents, p.currency)} payment
              </Button>
            ))}
        </div>
      )}

      {isOwner && (
        <>
          <AddLineModal bill={bill} open={modal === 'line'} onClose={() => setModal(null)} onDone={() => invalidate()} />
          <RecordPaymentModal bill={bill} open={modal === 'payment'} onClose={() => setModal(null)} onDone={() => invalidate()} />
          <CorrectionModal bill={bill} open={modal === 'correction'} onClose={() => setModal(null)} onDone={() => invalidate()} />
          <ReasonModal
            open={modal === 'cancel'}
            title="Cancel this bill?"
            confirmLabel="Cancel bill"
            description="The bill stays on record as cancelled. A cancelled month can be regenerated from the billing cycle."
            onClose={() => setModal(null)}
            onConfirm={async (reason) => {
              await apiClient.post(`/bills/${bill.id}/cancel/`, { reason })
              await invalidate()
            }}
          />
          <ReasonModal
            open={voidTarget !== null}
            title="Void this payment?"
            confirmLabel="Void payment"
            description="The amount is removed from the bill's paid total. The payment and its receipt stay on record, marked void."
            onClose={() => setVoidTarget(null)}
            onConfirm={async (reason) => {
              await apiClient.post(`/payments/${voidTarget}/void/`, { reason })
              await invalidate()
            }}
          />
        </>
      )}
    </div>
  )
}
