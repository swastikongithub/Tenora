/**
 * The owner's Billing hub — PROPERTY billing (residents -> this workspace's
 * owner). It is not the Tenora subscription, which stays under /subscription.
 *
 *   /billing           summary for the month + the monthly billing cycle
 *   /billing/bills     filterable bill list
 *   /billing/aging     outstanding balances by age
 *   /billing/readings  meter readings (+ proof) and corrections
 *   /billing/tariffs   electricity rate history
 *   /billing/reports   monthly series and electricity by unit
 */

import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, Outlet, useNavigate, useSearchParams } from 'react-router-dom'

import { Alert, Badge, Button, EmptyState, Input, Table } from '../../components'
import { apiClient } from '../../lib/api-client'
import {
  currentPeriodParam,
  formatDay,
  formatDecimal,
  formatPeriod,
  formatRate,
  money,
  toMinorRate,
} from '../../lib/property/format'
import { useInvalidateProperty, usePropertyQuery, useWorkspaceRole } from '../../lib/property/hooks'
import type {
  AgingReport,
  Bill,
  BillingCycle,
  CycleProgress,
  Meter,
  MeterReading,
  Paginated,
  PeriodSummary,
  Tariff,
  WorkspaceOverview,
  WorkspaceSettings,
} from '../../lib/property/types'
import { BillTable } from './BillTable'
import { ProofButton } from './BillDetailView'
import { OnboardingBanner } from './OnboardingBanner'
import { PageHeader, QueryState, Section, Select, StatGrid, StatTile, SubNav, TextArea } from './ui'
import { errorMessage, fieldError } from '../../lib/property/errors'

export function BillingLayout() {
  const { tenantName } = useWorkspaceRole()
  return (
    <div>
      <PageHeader
        eyebrow={tenantName}
        title="Billing"
        description="Rent, electricity and other charges your residents owe this workspace — separate from your Tenora subscription."
      />
      <SubNav
        label="Billing sections"
        items={[
          { to: '/billing', label: 'Overview', end: true },
          { to: '/billing/bills', label: 'Bills' },
          { to: '/billing/aging', label: 'Aging' },
          { to: '/billing/readings', label: 'Meter readings' },
          { to: '/billing/tariffs', label: 'Tariffs' },
          { to: '/billing/reports', label: 'Reports' },
        ]}
      />
      <Outlet />
    </div>
  )
}

function useCurrency() {
  const settings = usePropertyQuery<WorkspaceSettings>('settings', '/workspace/settings/')
  return settings.data?.currency ?? 'INR'
}

export function SummaryTiles({ summary }: { summary: PeriodSummary; }) {
  const currency = useCurrency()
  return (
    <StatGrid>
      <StatTile label="Billed" value={money(summary.billed_cents, currency)} hint={`${summary.bills_issued} bills issued`} />
      <StatTile label="Collected" value={money(summary.collected_cents, currency)} tone="success" hint={`${summary.bills_paid} paid`} />
      <StatTile label="Outstanding" value={money(summary.outstanding_cents, currency)} hint={`${summary.bills_unpaid} unpaid`} />
      <StatTile label="Overdue" value={money(summary.overdue_cents, currency)} tone={summary.overdue_cents > 0 ? 'danger' : undefined} />
      {summary.residents !== null && <StatTile label="Residents" value={summary.residents} />}
      <StatTile label="Electricity" value={`${formatDecimal(summary.electricity_units)} units`} />
      <StatTile label="Drafts awaiting review" value={summary.bills_draft} />
    </StatGrid>
  )
}

function CycleCard({ cycle, currency }: { cycle: BillingCycle; currency: string }) {
  const invalidate = useInvalidateProperty()
  const detail = usePropertyQuery<BillingCycle & { progress: CycleProgress }>('cycle', `/billing/cycles/${cycle.id}/`)
  const [message, setMessage] = useState<string | null>(null)
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) =>
      apiClient.post<{ created?: number; skipped?: Array<{ message: string }>; published?: number }>(path, body ?? {}),
    onSuccess: (data) => {
      if (data && typeof data.created === 'number') {
        setMessage(`${data.created} draft bill(s) generated${data.skipped?.length ? `, ${data.skipped.length} skipped` : ''}.`)
      } else if (data && typeof data.published === 'number') {
        setMessage(`${data.published} bill(s) published.`)
      } else {
        setMessage('Done.')
      }
      invalidate()
    },
  })
  const p = detail.data?.progress
  return (
    <div className="rounded-lg border border-subtle bg-raised p-5" aria-label={`Billing cycle ${formatPeriod(cycle.period_start)}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-medium text-primary">{formatPeriod(cycle.period_start)}</h3>
          <p className="text-caption text-secondary">
            Status: <Badge variant={cycle.status === 'OPEN' ? 'accent' : 'neutral'}>{cycle.status}</Badge>
          </p>
        </div>
        {cycle.status === 'OPEN' && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" loading={action.isPending} onClick={() => action.mutate({ path: `/billing/cycles/${cycle.id}/generate/` })}>
              Generate bills
            </Button>
            <Button size="sm" variant="secondary" onClick={() => action.mutate({ path: `/billing/cycles/${cycle.id}/generate/`, body: { regenerate_drafts: true } })}>
              Regenerate drafts
            </Button>
            <Button size="sm" disabled={!p?.bills_draft} onClick={() => action.mutate({ path: `/billing/cycles/${cycle.id}/publish/` })}>
              Publish drafts
            </Button>
            <Button size="sm" variant="ghost" onClick={() => action.mutate({ path: `/billing/cycles/${cycle.id}/close/` })}>
              Close cycle
            </Button>
          </div>
        )}
      </div>
      {message && <Alert variant="success" className="mt-3">{message}</Alert>}
      {action.error && <Alert variant="danger" className="mt-3">{errorMessage(action.error)}</Alert>}
      <QueryState isLoading={detail.isLoading} error={detail.error} label="cycle progress" />
      {p && (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ['Readings', `${p.readings_entered} / ${p.meters_expected}`],
              ['Bills generated', `${p.bills_generated} / ${p.expected_bills}`],
              ['Published', `${p.bills_published} / ${p.expected_bills}`],
              ['Collected', `${money(p.collected_cents, currency)} / ${money(p.billed_cents, currency)}`],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-caption text-secondary">{label}</dt>
                <dd className="font-mono text-label tabular-nums text-primary">{value}</dd>
              </div>
            ))}
          </dl>
          {p.exceptions.length > 0 && (
            <div className="mt-4">
              <h4 className="text-label font-medium text-primary">Exceptions to resolve ({p.exceptions.length})</h4>
              <ul className="mt-2 flex flex-col gap-1">
                {p.exceptions.map((ex, i) => (
                  <li key={`${ex.lease_id}-${ex.code}-${i}`} className="flex flex-wrap items-center gap-2 text-caption">
                    <Badge variant={ex.blocking ? 'danger' : 'warning'}>{ex.blocking ? 'Blocking' : 'Warning'}</Badge>
                    <span className="text-primary">
                      Unit {ex.unit_identifier} · {ex.resident_name}:
                    </span>
                    <span className="text-secondary">{ex.message}</span>
                    {ex.code.includes('READING') && (
                      <Link to="/billing/readings" className="text-accent-500 underline">
                        Enter reading
                      </Link>
                    )}
                    {ex.code === 'MISSING_TARIFF' && (
                      <Link to="/billing/tariffs" className="text-accent-500 underline">
                        Set rate
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="mt-4 text-label">
            <Link to={`/billing/bills?cycle=${cycle.id}`} className="text-accent-500 underline">
              Review this cycle’s bills
            </Link>
          </p>
        </>
      )}
    </div>
  )
}

export function BillingOverviewPage() {
  const currency = useCurrency()
  const invalidate = useInvalidateProperty()
  const [period, setPeriod] = useState(currentPeriodParam())
  const summary = usePropertyQuery<PeriodSummary>('summary', '/billing/summary/', { period })
  const cycles = usePropertyQuery<BillingCycle[]>('cycles', '/billing/cycles/')
  const overview = usePropertyQuery<WorkspaceOverview>('overview', '/workspace/overview/')
  const open = useMutation({
    mutationFn: () => apiClient.post('/billing/cycles/', { period }),
    onSuccess: () => invalidate(),
  })
  const reminders = useMutation({
    mutationFn: () => apiClient.post<Record<string, number>>('/billing/reminders/run/'),
  })
  const cycleForPeriod = cycles.data?.find((c) => c.period_start.startsWith(period))

  return (
    <div>
      {overview.data && !overview.data.onboarding.ready_to_bill && <OnboardingBanner overview={overview.data} />}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Input label="Billing month" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
        </div>
        {!cycleForPeriod && (
          <Button onClick={() => open.mutate()} loading={open.isPending}>
            Start {formatPeriod(`${period}-01`)} cycle
          </Button>
        )}
        <Button variant="secondary" onClick={() => reminders.mutate()} loading={reminders.isPending}>
          Send due & overdue reminders
        </Button>
      </div>
      {open.error && <Alert variant="danger" className="mt-3">{errorMessage(open.error)}</Alert>}
      {reminders.data && (
        <Alert variant="success" className="mt-3">
          Reminders sent: {reminders.data.overdue ?? 0} overdue, {reminders.data.due_soon ?? 0} due soon.
        </Alert>
      )}

      <Section title={`${formatPeriod(`${period}-01`)} summary`}>
        <QueryState isLoading={summary.isLoading} error={summary.error} onRetry={() => summary.refetch()} label="the billing summary" />
        {summary.data && <SummaryTiles summary={summary.data} />}
      </Section>

      <Section title="Billing cycles">
        <QueryState isLoading={cycles.isLoading} error={cycles.error} onRetry={() => cycles.refetch()} label="billing cycles" />
        {cycles.data && cycles.data.length === 0 && (
          <EmptyState headline="No billing cycles yet" description="Start a cycle for a month, enter meter readings, then generate and publish bills." />
        )}
        <div className="flex flex-col gap-4">
          {cycles.data?.slice(0, 6).map((cycle) => <CycleCard key={cycle.id} cycle={cycle} currency={currency} />)}
        </div>
      </Section>
    </div>
  )
}

export function BillsPage() {
  const [params, setParams] = useSearchParams()
  const filters = {
    period: params.get('period') ?? undefined,
    status: params.get('status') ?? undefined,
    payment_status: params.get('payment_status') ?? undefined,
    search: params.get('search') ?? undefined,
    cycle: params.get('cycle') ?? undefined,
    resident: params.get('resident') ?? undefined,
    property: params.get('property') ?? undefined,
    page: params.get('page') ?? undefined,
  }
  const bills = usePropertyQuery<Paginated<Bill>>('bills', '/bills/', filters)
  const properties = usePropertyQuery<Array<{ id: string; name: string }>>('properties', '/properties/')
  function set(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setParams(next, { replace: true })
  }
  const page = Number(filters.page ?? '1')
  return (
    <div>
      <form className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-6" onSubmit={(e) => e.preventDefault()} aria-label="Bill filters">
        <Input label="Month" type="month" value={filters.period ?? ''} onChange={(e) => set('period', e.target.value)} />
        <Select label="Status" value={filters.status ?? ''} onChange={(e) => set('status', e.target.value)}>
          <option value="">All</option>
          <option value="DRAFT">Draft</option>
          <option value="UNPAID">Unpaid (any)</option>
          <option value="OVERDUE">Overdue</option>
          <option value="PARTIALLY_PAID">Partially paid</option>
          <option value="PAID">Paid</option>
          <option value="CANCELLED">Cancelled</option>
        </Select>
        <Select label="Payment" value={filters.payment_status ?? ''} onChange={(e) => set('payment_status', e.target.value)}>
          <option value="">All</option>
          <option value="UNPAID">Unpaid</option>
          <option value="PARTIALLY_PAID">Partial</option>
          <option value="PAID">Paid</option>
        </Select>
        <Select label="Property" value={filters.property ?? ''} onChange={(e) => set('property', e.target.value)}>
          <option value="">All</option>
          {properties.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <div className="sm:col-span-2">
          <Input label="Search resident, unit or bill no." value={filters.search ?? ''} onChange={(e) => set('search', e.target.value)} />
        </div>
      </form>
      <QueryState isLoading={bills.isLoading} error={bills.error} onRetry={() => bills.refetch()} label="bills" />
      {bills.data && bills.data.results.length === 0 && (
        <EmptyState headline="No bills match" description="Adjust the filters, or generate bills from a billing cycle." />
      )}
      {bills.data && bills.data.results.length > 0 && (
        <>
          <BillTable bills={bills.data.results} />
          <div className="mt-3 flex items-center justify-between text-caption text-secondary">
            <span>{bills.data.count} bill(s)</span>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" disabled={!bills.data.previous} onClick={() => set('page', String(page - 1))}>
                Previous
              </Button>
              <Button size="sm" variant="ghost" disabled={!bills.data.next} onClick={() => { const n = new URLSearchParams(params); n.set('page', String(page + 1)); setParams(n) }}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export function AgingView({ report, currency, onRow }: { report: AgingReport; currency: string; onRow?: (billId: string) => void }) {
  const max = Math.max(1, ...report.buckets.map((b) => b.amount_cents))
  return (
    <div>
      <StatGrid>
        <StatTile label="Total outstanding" value={money(report.total_outstanding_cents, currency)} />
        <StatTile label="Total overdue" value={money(report.total_overdue_cents, currency)} tone={report.total_overdue_cents > 0 ? 'danger' : undefined} />
      </StatGrid>
      <ul className="mt-6 flex flex-col gap-2" aria-label="Aging buckets">
        {report.buckets.map((b) => (
          <li key={b.key} className="grid grid-cols-[7rem_1fr_auto] items-center gap-3">
            <span className="text-label text-secondary">{b.label}</span>
            <span className="h-3 overflow-hidden rounded-full bg-overlay" aria-hidden="true">
              <span
                className={b.key === 'CURRENT' ? 'block h-full bg-accent-600' : 'block h-full bg-danger'}
                style={{ width: `${Math.round((b.amount_cents / max) * 100)}%` }}
              />
            </span>
            <span className="font-mono text-label tabular-nums text-primary">
              {money(b.amount_cents, currency)} · {b.count}
            </span>
          </li>
        ))}
      </ul>
      <Section title="Outstanding balances">
        {report.rows.length === 0 ? (
          <p className="text-body text-secondary">Nothing outstanding.</p>
        ) : (
          <Table
            caption="Outstanding balances"
            rows={report.rows}
            rowKey={(r) => r.bill_id}
            onRowClick={onRow ? (r) => onRow(r.bill_id) : undefined}
            columns={[
              { key: 'resident', header: 'Resident', render: (r) => r.resident_name },
              { key: 'unit', header: 'Unit', render: (r) => `${r.unit_identifier} · ${r.property_name}` },
              { key: 'period', header: 'Period', render: (r) => formatPeriod(r.period_start) },
              { key: 'amount', header: 'Amount', numeric: true, render: (r) => money(r.amount_due_cents, r.currency) },
              { key: 'due', header: 'Due date', render: (r) => formatDay(r.due_date) },
              {
                key: 'overdue',
                header: 'Overdue',
                numeric: true,
                render: (r) => (r.overdue_days > 0 ? `${r.overdue_days} days` : 'Current'),
              },
            ]}
          />
        )}
      </Section>
    </div>
  )
}

export function AgingPage() {
  const currency = useCurrency()
  const navigate = useNavigate()
  const report = usePropertyQuery<AgingReport>('aging', '/billing/aging/')
  return (
    <div>
      <p className="mb-4 text-body text-secondary">
        Overdue age is calculated on the server from each bill’s due date — it is the same number the resident sees.
      </p>
      <QueryState isLoading={report.isLoading} error={report.error} onRetry={() => report.refetch()} label="the aging report" />
      {report.data && <AgingView report={report.data} currency={currency} onRow={(id) => navigate(`/bills/${id}`)} />}
    </div>
  )
}

export function ReadingForm({ meters, onDone }: { meters: Meter[]; onDone: () => void }) {
  const [meterId, setMeterId] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [value, setValue] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const mutation = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.set('meter_id', meterId || meters[0]?.id || '')
      form.set('reading_date', date)
      form.set('reading_value', value)
      form.set('notes', notes)
      if (file) form.set('proof', file)
      return apiClient.post('/meter-readings/', form)
    },
    onSuccess: () => {
      setValue('')
      setNotes('')
      setFile(null)
      onDone()
    },
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    mutation.mutate()
  }
  if (meters.length === 0) {
    return <p className="text-body text-secondary">Add a meter to a unit first (Properties → unit → Meters).</p>
  }
  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3 rounded-lg border border-subtle bg-raised p-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Record meter reading">
      {mutation.error && !fieldError(mutation.error, 'reading_value') && (
        <div className="sm:col-span-2 lg:col-span-4">
          <Alert variant="danger">{errorMessage(mutation.error)}</Alert>
        </div>
      )}
      {mutation.isSuccess && (
        <div className="sm:col-span-2 lg:col-span-4">
          <Alert variant="success">Reading recorded.</Alert>
        </div>
      )}
      <Select label="Meter" value={meterId || meters[0]?.id} onChange={(e) => setMeterId(e.target.value)}>
        {meters
          .filter((m) => m.is_active)
          .map((m) => (
            <option key={m.id} value={m.id}>
              {m.meter_number} · Unit {m.unit_identifier}
              {m.latest_reading ? ` (last ${formatDecimal(m.latest_reading.reading_value)})` : ''}
            </option>
          ))}
      </Select>
      <Input label="Reading date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      <Input
        label="Reading value"
        inputMode="decimal"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        error={Boolean(fieldError(mutation.error, 'reading_value'))}
        helperText={fieldError(mutation.error, 'reading_value')}
      />
      <div className="flex flex-col gap-1.5">
        <label htmlFor="proof-input" className="text-label text-secondary">
          Proof image (optional)
        </label>
        <input
          id="proof-input"
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-caption text-secondary"
        />
      </div>
      <div className="sm:col-span-2 lg:col-span-3">
        <Input label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>
      <div className="flex items-end">
        <Button type="submit" loading={mutation.isPending} disabled={!value}>
          Save reading
        </Button>
      </div>
    </form>
  )
}

function CorrectReading({ reading, onDone }: { reading: MeterReading; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(reading.reading_value)
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: () =>
      apiClient.post<{ affected_bills: Array<{ bill_number: string }> }>(`/meter-readings/${reading.id}/correct/`, {
        corrected_value: value,
        reason,
      }),
    onSuccess: () => onDone(),
  })
  if (!open)
    return (
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        Correct
      </Button>
    )
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        mutation.mutate()
      }}
    >
      <Input label="Corrected value" value={value} onChange={(e) => setValue(e.target.value)} />
      <TextArea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      {mutation.error && <Alert variant="danger">{errorMessage(mutation.error)}</Alert>}
      {mutation.data && mutation.data.affected_bills.length > 0 && (
        <Alert variant="warning">
          Issued bills keep their original reading. Review with a bill correction: {mutation.data.affected_bills.map((b) => b.bill_number || 'draft').join(', ')}.
        </Alert>
      )}
      <div className="flex gap-2">
        <Button size="sm" type="submit" loading={mutation.isPending} disabled={!reason.trim()}>
          Save correction
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Close
        </Button>
      </div>
    </form>
  )
}

export function ReadingsPage() {
  const invalidate = useInvalidateProperty()
  const [period, setPeriod] = useState(currentPeriodParam())
  const meters = usePropertyQuery<Meter[]>('meters', '/meters/')
  const readings = usePropertyQuery<Paginated<MeterReading>>('readings', '/meter-readings/', { period })
  return (
    <div>
      <Section title="Record a reading">
        <QueryState isLoading={meters.isLoading} error={meters.error} label="meters" />
        {meters.data && <ReadingForm meters={meters.data} onDone={() => invalidate()} />}
      </Section>
      <Section
        title="Readings"
        actions={
          <div className="w-44">
            <Input label="Month" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </div>
        }
      >
        <QueryState isLoading={readings.isLoading} error={readings.error} label="readings" />
        {readings.data && readings.data.results.length === 0 && <p className="text-body text-secondary">No readings in this month.</p>}
        <ul className="flex flex-col gap-2">
          {readings.data?.results.map((r) => (
            <li key={r.id} className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-subtle p-3">
              <div>
                <p className="text-label text-primary">
                  {r.meter_number} · Unit {r.unit_identifier} · <span className="font-mono">{formatDecimal(r.reading_value)}</span>
                </p>
                <p className="text-caption text-secondary">
                  {formatDay(r.reading_date)}
                  {r.notes ? ` · ${r.notes}` : ''}
                  {r.corrections.length > 0 ? ` · corrected from ${formatDecimal(r.corrections[0].original_value)} (${r.corrections[0].reason})` : ''}
                </p>
              </div>
              <div className="flex items-start gap-2">
                {r.has_proof && <ProofButton path={`/meter-readings/${r.id}/proof/`} label="View proof" />}
                <CorrectReading reading={r} onDone={() => invalidate()} />
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}

export function TariffsPage() {
  const invalidate = useInvalidateProperty()
  const currency = useCurrency()
  const tariffs = usePropertyQuery<{ current: Tariff | null; results: Tariff[] }>('tariffs', '/billing/tariffs/')
  const [rate, setRate] = useState('')
  const [from, setFrom] = useState('')
  const minorRate = toMinorRate(rate)
  const mutation = useMutation({
    mutationFn: () => apiClient.post('/billing/tariffs/', { rate_per_unit_cents: minorRate, effective_from: from }),
    onSuccess: () => {
      setRate('')
      invalidate()
    },
  })
  return (
    <div>
      <StatGrid>
        <StatTile
          label="Current electricity rate"
          value={tariffs.data?.current ? formatRate(tariffs.data.current.rate_per_unit_cents, currency, 'unit') : 'Not set'}
          hint={tariffs.data?.current ? `Since ${formatDay(tariffs.data.current.effective_from)}` : 'Bills with meters need a rate.'}
        />
      </StatGrid>
      <Section title="Set a new rate">
        <form
          className="grid grid-cols-1 gap-3 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (minorRate && from) mutation.mutate()
          }}
          aria-label="New electricity rate"
        >
          <Input
            label={`Rate per unit (${currency})`}
            inputMode="decimal"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            error={rate !== '' && !minorRate}
            helperText="e.g. 8 or 8.25"
          />
          <Input label="Effective from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} helperText="Applies to billing periods ending on or after this date." />
          <div className="flex items-end">
            <Button type="submit" loading={mutation.isPending} disabled={!minorRate || !from}>
              Save rate
            </Button>
          </div>
        </form>
        {mutation.error && <Alert variant="danger" className="mt-3">{errorMessage(mutation.error)}</Alert>}
        <p className="mt-2 text-caption text-secondary">Issued bills keep the rate they were calculated with.</p>
      </Section>
      <Section title="Rate history">
        <QueryState isLoading={tariffs.isLoading} error={tariffs.error} label="tariffs" />
        {tariffs.data && (
          <Table
            caption="Electricity rate history"
            rows={tariffs.data.results}
            rowKey={(t) => t.id}
            columns={[
              { key: 'rate', header: 'Rate', render: (t) => formatRate(t.rate_per_unit_cents, currency) },
              { key: 'from', header: 'From', render: (t) => formatDay(t.effective_from) },
              { key: 'to', header: 'To', render: (t) => (t.effective_to ? formatDay(t.effective_to) : 'Open') },
            ]}
          />
        )}
      </Section>
    </div>
  )
}

interface ReportData {
  period: string
  monthly: Array<{
    period: string
    billed_cents: number
    collected_cents: number
    outstanding_cents: number
    rent_billed_cents: number
    electricity_billed_cents: number
    other_billed_cents: number
    electricity_units: string
    cash_received_cents: number
  }>
  electricity_by_unit: Array<{ property_name: string; unit_identifier: string; units: string; amount_cents: number }>
}

export function ReportsPage() {
  const currency = useCurrency()
  const [period, setPeriod] = useState(currentPeriodParam())
  const report = usePropertyQuery<ReportData>('reports', '/billing/reports/', { period, months: '12' })
  return (
    <div>
      <QueryState isLoading={report.isLoading} error={report.error} onRetry={() => report.refetch()} label="reports" />
      {report.data && (
        <>
          <Section title="Last 12 months">
            <Table
              caption="Monthly billing report"
              rows={[...report.data.monthly].reverse()}
              rowKey={(r) => r.period}
              columns={[
                { key: 'period', header: 'Month', render: (r) => formatPeriod(`${r.period}-01`) },
                { key: 'billed', header: 'Billed', numeric: true, render: (r) => money(r.billed_cents, currency) },
                { key: 'collected', header: 'Collected', numeric: true, render: (r) => money(r.collected_cents, currency) },
                { key: 'outstanding', header: 'Outstanding', numeric: true, render: (r) => money(r.outstanding_cents, currency) },
                { key: 'rent', header: 'Rent', numeric: true, render: (r) => money(r.rent_billed_cents, currency) },
                { key: 'elec', header: 'Electricity', numeric: true, render: (r) => money(r.electricity_billed_cents, currency) },
                { key: 'other', header: 'Other', numeric: true, render: (r) => money(r.other_billed_cents, currency) },
                { key: 'units', header: 'Units', numeric: true, render: (r) => formatDecimal(r.electricity_units) },
                { key: 'cash', header: 'Cash received', numeric: true, render: (r) => money(r.cash_received_cents, currency) },
              ]}
            />
          </Section>
          <Section
            title="Electricity by unit"
            actions={
              <div className="w-44">
                <Input label="Month" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
              </div>
            }
          >
            {report.data.electricity_by_unit.length === 0 ? (
              <p className="text-body text-secondary">No issued electricity charges for this month.</p>
            ) : (
              <Table
                caption="Electricity by unit"
                rows={report.data.electricity_by_unit}
                rowKey={(r) => `${r.property_name}-${r.unit_identifier}`}
                columns={[
                  { key: 'unit', header: 'Unit', render: (r) => `${r.unit_identifier} · ${r.property_name}` },
                  { key: 'units', header: 'Units', numeric: true, render: (r) => formatDecimal(r.units) },
                  { key: 'amount', header: 'Amount', numeric: true, render: (r) => money(r.amount_cents, currency) },
                ]}
              />
            )}
          </Section>
        </>
      )}
    </div>
  )
}
