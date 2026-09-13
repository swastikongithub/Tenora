/**
 * Payments and receipts — role-aware. An owner sees every payment recorded in
 * the workspace; a resident sees only their own (the API filters on the
 * authenticated resident; nothing here narrows client-side).
 */

import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { Alert, Badge, Button, EmptyState, Input, Table } from '../../components'
import { ApiError } from '../../lib/api-error'
import { METHOD_LABEL, formatDay, formatPeriod, money } from '../../lib/property/format'
import { usePropertyQuery, useWorkspaceRole } from '../../lib/property/hooks'
import type { Paginated, Payment, Receipt } from '../../lib/property/types'
import { PageHeader, QueryState, Section, SubNav } from './ui'

export function PaymentsPage() {
  const { isOwner, tenantName } = useWorkspaceRole()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const search = params.get('search') ?? ''
  const payments = usePropertyQuery<Paginated<Payment>>('payments', '/payments/', { search: search || undefined })
  return (
    <div>
      <PageHeader eyebrow={tenantName} title="Payments" description="Money received against residents’ bills. Each payment has its own receipt." />
      <SubNav label="Payment sections" items={[{ to: '/payments', label: 'Payments', end: true }, { to: '/receipts', label: 'Receipts' }]} />
      {isOwner && (
        <div className="mb-4 max-w-sm">
          <Input label="Search resident, reference or bill" value={search} onChange={(e) => setParams(e.target.value ? { search: e.target.value } : {}, { replace: true })} />
        </div>
      )}
      <QueryState isLoading={payments.isLoading} error={payments.error} onRetry={() => payments.refetch()} label="payments" />
      {payments.data?.results.length === 0 && (
        <EmptyState headline="No payments yet" description={isOwner ? 'Record a payment from a published bill.' : 'Payments recorded by your property owner appear here.'} />
      )}
      {payments.data && payments.data.results.length > 0 && (
        <Table
          caption="Payments"
          rows={payments.data.results}
          rowKey={(p) => p.id}
          onRowClick={(p) => navigate(`/bills/${p.bill_id}`)}
          columns={[
            { key: 'date', header: 'Date', render: (p) => formatDay(p.payment_date) },
            { key: 'resident', header: 'Resident', render: (p) => `${p.resident_name} · ${p.unit_identifier}` },
            { key: 'period', header: 'Bill', render: (p) => `${formatPeriod(p.period_start)}${p.bill_number ? ` · ${p.bill_number}` : ''}` },
            { key: 'method', header: 'Method', render: (p) => METHOD_LABEL[p.method] ?? p.method },
            { key: 'amount', header: 'Amount', numeric: true, render: (p) => money(p.amount_cents, p.currency) },
            { key: 'status', header: 'Status', render: (p) => <Badge variant={p.status === 'COMPLETED' ? 'success' : 'neutral'}>{p.status === 'COMPLETED' ? 'Completed' : 'Voided'}</Badge> },
            { key: 'receipt', header: 'Receipt', render: (p) => p.receipt_number ?? '—' },
          ]}
        />
      )}
    </div>
  )
}

export function ReceiptsPage() {
  const { isOwner, tenantName } = useWorkspaceRole()
  const navigate = useNavigate()
  const receipts = usePropertyQuery<Paginated<Receipt>>('receipts', '/receipts/')
  return (
    <div>
      <PageHeader eyebrow={tenantName} title="Receipts" description="Proof of every recorded payment. Receipt numbers never change once issued." />
      {isOwner && <SubNav label="Payment sections" items={[{ to: '/payments', label: 'Payments', end: true }, { to: '/receipts', label: 'Receipts' }]} />}
      <QueryState isLoading={receipts.isLoading} error={receipts.error} onRetry={() => receipts.refetch()} label="receipts" />
      {receipts.data?.results.length === 0 && <EmptyState headline="No receipts yet" description="A receipt is issued automatically for each recorded payment." />}
      {receipts.data && receipts.data.results.length > 0 && (
        <Table
          caption="Receipts"
          rows={receipts.data.results}
          rowKey={(r) => r.id}
          onRowClick={(r) => navigate(`/receipts/${r.id}`)}
          columns={[
            { key: 'number', header: 'Receipt', render: (r) => <span className="font-mono">{r.receipt_number}</span> },
            { key: 'issued', header: 'Issued', render: (r) => formatDay(r.issued_at) },
            { key: 'resident', header: 'Resident', render: (r) => `${r.resident_name} · ${r.unit_identifier}` },
            { key: 'period', header: 'Bill period', render: (r) => formatPeriod(r.period_start) },
            { key: 'amount', header: 'Amount', numeric: true, render: (r) => money(r.amount_cents, r.currency) },
            { key: 'status', header: 'Status', render: (r) => (r.payment_status === 'VOIDED' ? <Badge variant="neutral">Void</Badge> : <Badge variant="success">Valid</Badge>) },
          ]}
        />
      )}
    </div>
  )
}

export function ReceiptPage() {
  const { id = '' } = useParams()
  const receipt = usePropertyQuery<Receipt>('receipt', `/receipts/${id}/`)
  if (receipt.error instanceof ApiError && receipt.error.status === 404) {
    return <Alert variant="warning">This receipt doesn’t exist in this workspace.</Alert>
  }
  if (!receipt.data) return <QueryState isLoading={receipt.isLoading} error={receipt.error} onRetry={() => receipt.refetch()} label="this receipt" />
  const r = receipt.data
  return (
    <div className="max-w-[640px]">
      <p className="mb-4 flex justify-between text-label print:hidden">
        <Link to="/receipts" className="text-secondary hover:text-primary">← Receipts</Link>
        <Button size="sm" variant="secondary" onClick={() => window.print()}>Print</Button>
      </p>
      <article className="rounded-lg border border-subtle bg-raised p-6" aria-label={`Receipt ${r.receipt_number}`}>
        <header className="flex flex-wrap justify-between gap-4">
          <div>
            <p className="text-caption uppercase tracking-wide text-secondary">Receipt</p>
            <h1 className="font-mono text-display text-primary">{r.receipt_number}</h1>
            <p className="text-caption text-secondary">Issued {formatDay(r.issued_at)}</p>
          </div>
          {r.issuer && (
            <div className="text-right text-caption text-secondary">
              <p className="text-label text-primary">{r.issuer.name}</p>
              {r.issuer.address && <p>{r.issuer.address}</p>}
              {r.issuer.contact_email && <p>{r.issuer.contact_email}</p>}
              {r.issuer.contact_phone && <p>{r.issuer.contact_phone}</p>}
            </div>
          )}
        </header>
        {r.payment_status === 'VOIDED' && (
          <Alert variant="warning" className="mt-4">
            The payment on this receipt was voided.
          </Alert>
        )}
        <Section title="Received from">
          <p className="text-body text-primary">{r.resident_name}</p>
          <p className="text-caption text-secondary">
            Unit {r.unit_identifier} · {r.property_name}
          </p>
        </Section>
        <dl className="mt-6 grid grid-cols-2 gap-3 text-label">
          <dt className="text-secondary">Amount received</dt>
          <dd className="text-right font-mono text-primary">{money(r.amount_cents, r.currency)}</dd>
          <dt className="text-secondary">Payment date</dt>
          <dd className="text-right">{formatDay(r.payment_date)}</dd>
          <dt className="text-secondary">Method</dt>
          <dd className="text-right">{METHOD_LABEL[r.payment_method] ?? r.payment_method}</dd>
          {r.payment_reference && (
            <>
              <dt className="text-secondary">Reference</dt>
              <dd className="text-right font-mono">{r.payment_reference}</dd>
            </>
          )}
          <dt className="text-secondary">For bill</dt>
          <dd className="text-right">
            <Link to={`/bills/${r.bill_id}`} className="underline">
              {r.bill_number || formatPeriod(r.period_start)}
            </Link>{' '}
            · {formatPeriod(r.period_start)}
          </dd>
        </dl>
        {r.issuer?.footer && <p className="mt-6 text-caption text-secondary">{r.issuer.footer}</p>}
      </article>
    </div>
  )
}
