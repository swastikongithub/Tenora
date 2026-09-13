/**
 * The explainable bill (plan §13, §16.6, §30): every amount on screen is a value
 * the API stored — rent line, electricity opening/closing readings, units, rate,
 * other charges, corrections, payments and receipts. Nothing is recomputed here.
 *
 * Used by the owner, the resident and the platform admin. Actions render only
 * for `mode === 'owner'`; the server refuses them for anyone else regardless.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert, Badge, Button, Modal } from '../../components'
import { apiClient } from '../../lib/api-client'
import {
  METHOD_LABEL,
  formatDay,
  formatDecimal,
  formatPeriod,
  formatRate,
  money,
} from '../../lib/property/format'
import type { BillDetail, LineItem } from '../../lib/property/types'
import { BillStatusBadge, Section } from './ui'

export type BillViewMode = 'owner' | 'resident' | 'platform'

export function ProofButton({ path, label }: { path: string; label: string }) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState<string | null>(null)
  const [type, setType] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let revoked = false
    let objectUrl: string | null = null
    setError(null)
    apiClient
      .getBlob(path)
      .then((blob) => {
        if (revoked) return
        objectUrl = URL.createObjectURL(blob)
        setType(blob.type)
        setUrl(objectUrl)
      })
      .catch(() => setError('Couldn’t load the proof image.'))
    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setUrl(null)
    }
  }, [open, path])

  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        {label}
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Meter reading proof" size="detail">
        {error && <Alert variant="danger">{error}</Alert>}
        {!error && !url && <p className="text-body text-secondary">Loading…</p>}
        {url && type === 'application/pdf' && (
          <a href={url} target="_blank" rel="noreferrer" className="text-label text-accent-500 underline">
            Open PDF proof
          </a>
        )}
        {url && type !== 'application/pdf' && (
          <img src={url} alt="Meter reading proof" className="max-h-[70vh] w-full rounded-md object-contain" />
        )}
      </Modal>
    </>
  )
}

function ElectricityDetail({ line, currency, proofPath }: { line: LineItem; currency: string; proofPath: (id: string) => string }) {
  return (
    <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-caption sm:grid-cols-3">
      <div>
        <dt className="text-secondary">Meter</dt>
        <dd className="font-mono text-primary">{line.meter_number || '—'}</dd>
      </div>
      <div>
        <dt className="text-secondary">Opening</dt>
        <dd className="font-mono text-primary">
          {formatDecimal(line.opening_reading_value)} · {formatDay(line.opening_reading_date)}
        </dd>
        {line.opening_has_proof && line.opening_reading_id && (
          <ProofButton path={proofPath(line.opening_reading_id)} label="View opening proof" />
        )}
      </div>
      <div>
        <dt className="text-secondary">Closing</dt>
        <dd className="font-mono text-primary">
          {formatDecimal(line.closing_reading_value)} · {formatDay(line.closing_reading_date)}
        </dd>
        {line.closing_has_proof && line.closing_reading_id && (
          <ProofButton path={proofPath(line.closing_reading_id)} label="View closing proof" />
        )}
      </div>
      <div>
        <dt className="text-secondary">Consumption</dt>
        <dd className="font-mono text-primary">{formatDecimal(line.units_consumed)} units</dd>
      </div>
      {line.multiplier && line.multiplier !== '1.0000' && (
        <div>
          <dt className="text-secondary">Multiplier</dt>
          <dd className="font-mono text-primary">×{formatDecimal(line.multiplier)}</dd>
        </div>
      )}
      <div>
        <dt className="text-secondary">Billed units</dt>
        <dd className="font-mono text-primary">{formatDecimal(line.quantity)}</dd>
      </div>
      <div>
        <dt className="text-secondary">Rate</dt>
        <dd className="font-mono text-primary">{formatRate(line.rate_per_unit_cents, currency)}</dd>
      </div>
    </dl>
  )
}

export function BillDetailView({
  bill,
  mode,
  proofPath,
  actions,
  receiptHref = (id) => `/receipts/${id}`,
  onRemoveLine,
}: {
  bill: BillDetail
  mode: BillViewMode
  proofPath: (readingId: string) => string
  actions?: React.ReactNode
  receiptHref?: (receiptId: string) => string
  onRemoveLine?: (line: LineItem) => void
}) {
  const c = bill.currency
  return (
    <article aria-label={`Bill ${bill.bill_number || 'draft'}`}>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-caption uppercase tracking-wide text-secondary">
            {bill.bill_number || 'Draft bill'}
            {bill.tenant_name ? ` · ${bill.tenant_name}` : ''}
          </p>
          <h1 className="text-display text-primary">{formatPeriod(bill.period_start)}</h1>
          <p className="mt-1 text-body text-secondary">
            {bill.property_name} · Unit {bill.unit_identifier} · {bill.resident_name}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <BillStatusBadge status={bill.display_status} overdueDays={bill.overdue_days} />
          <p className="font-mono text-display tabular-nums text-primary">{money(bill.total_cents, c)}</p>
          {actions}
        </div>
      </header>

      {bill.status === 'CANCELLED' && (
        <Alert variant="warning" className="mt-4">
          Cancelled{bill.cancellation_reason ? `: ${bill.cancellation_reason}` : ''}.
        </Alert>
      )}
      {bill.display_status === 'OVERDUE' && (
        <Alert variant="danger" className="mt-4">
          {money(bill.amount_due_cents, c)} is {bill.overdue_days} day{bill.overdue_days === 1 ? '' : 's'} overdue
          (due {formatDay(bill.due_date)}).
        </Alert>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Billing period', `${formatDay(bill.period_start)} – ${formatDay(bill.period_end)}`],
          ['Issued', bill.published_at ? formatDay(bill.published_at) : 'Not yet published'],
          ['Due date', formatDay(bill.due_date)],
          ['Amount due', money(bill.amount_due_cents, c)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border border-subtle bg-raised p-3">
            <dt className="text-caption text-secondary">{label}</dt>
            <dd className="mt-1 text-label text-primary">{value}</dd>
          </div>
        ))}
      </dl>

      <Section title="Charges">
        <ul className="divide-y divide-subtle rounded-md border border-subtle">
          {bill.line_items.map((line) => (
            <li key={line.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-label text-primary">{line.description}</p>
                  <p className="text-caption text-secondary">
                    {line.type.replace('_', ' ').toLowerCase()}
                    {line.correction_id ? ' · correction' : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-label tabular-nums text-primary">{money(line.amount_cents, c)}</span>
                  {mode === 'owner' && bill.status === 'DRAFT' && onRemoveLine && (
                    <Button size="sm" variant="ghost" onClick={() => onRemoveLine(line)} aria-label={`Remove ${line.description}`}>
                      Remove
                    </Button>
                  )}
                </div>
              </div>
              {line.type === 'ELECTRICITY' && <ElectricityDetail line={line} currency={c} proofPath={proofPath} />}
            </li>
          ))}
          {bill.line_items.length === 0 && <li className="p-4 text-body text-secondary">No charges.</li>}
        </ul>
        <dl className="mt-3 ml-auto flex max-w-sm flex-col gap-1 text-label">
          <div className="flex justify-between"><dt className="text-secondary">Subtotal</dt><dd className="font-mono tabular-nums">{money(bill.subtotal_cents, c)}</dd></div>
          <div className="flex justify-between"><dt className="text-secondary">Discounts & adjustments</dt><dd className="font-mono tabular-nums">{money(bill.adjustments_cents, c)}</dd></div>
          <div className="flex justify-between font-medium"><dt>Total</dt><dd className="font-mono tabular-nums">{money(bill.total_cents, c)}</dd></div>
          <div className="flex justify-between"><dt className="text-secondary">Paid</dt><dd className="font-mono tabular-nums">{money(bill.amount_paid_cents, c)}</dd></div>
          <div className="flex justify-between font-medium"><dt>Balance</dt><dd className="font-mono tabular-nums">{money(bill.amount_due_cents, c)}</dd></div>
        </dl>
      </Section>

      {bill.corrections.length > 0 && (
        <Section title="Corrections">
          <ul className="flex flex-col gap-2">
            {bill.corrections.map((corr) => (
              <li key={corr.id} className="rounded-md border border-subtle p-3 text-caption">
                <p className="text-label text-primary">
                  {corr.kind === 'READING_CORRECTION' ? 'Meter reading correction' : 'Amount adjustment'} ·{' '}
                  <span className="font-mono">{money(corr.amount_delta_cents, c)}</span>
                </p>
                <p className="text-secondary">Reason: {corr.reason}</p>
                <p className="text-secondary">
                  {corr.actor_email ? `${corr.actor_email} · ` : ''}
                  {formatDay(corr.created_at)}
                </p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Payments & receipts">
        {bill.payments.length === 0 ? (
          <p className="text-body text-secondary">No payments recorded yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {bill.payments.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-subtle p-3">
                <div>
                  <p className="text-label text-primary">
                    <span className="font-mono">{money(p.amount_cents, c)}</span> · {METHOD_LABEL[p.method] ?? p.method} ·{' '}
                    {formatDay(p.payment_date)}
                  </p>
                  <p className="text-caption text-secondary">
                    {p.reference ? `Ref ${p.reference}` : 'No reference'}
                    {p.status === 'VOIDED' ? ` · voided: ${p.void_reason}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {p.status === 'VOIDED' && <Badge variant="neutral">Voided</Badge>}
                  {p.receipt_id && mode !== 'platform' && (
                    <Link to={receiptHref(p.receipt_id)} className="text-label text-accent-500 underline">
                      {p.receipt_number}
                    </Link>
                  )}
                  {p.receipt_id && mode === 'platform' && (
                    <span className="font-mono text-label">{p.receipt_number}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </article>
  )
}
