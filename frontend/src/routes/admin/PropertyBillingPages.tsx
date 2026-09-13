/**
 * Platform-admin property billing (plan §15, §16.3): All workspaces -> workspace
 * -> property -> unit -> resident -> bills -> payments/receipts, plus a global
 * bill search. Reads only /api/platform/property-billing/* (IsPlatformStaff);
 * the one mutation, workspace role promote/demote, is Root-only server-side and
 * renders only for a Root viewer.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { Alert, Badge, Button, EmptyState, Input, Table } from '../../components'
import { useCurrentUser } from '../../components/layout/use-current-user'
import { apiClient } from '../../lib/api-client'
import { formatDay, formatDecimal, money } from '../../lib/property/format'
import { toQueryString } from '../../lib/property/hooks'
import type { AgingReport, Bill, BillDetail, Lease, Paginated, PeriodSummary, Property, Resident, Unit } from '../../lib/property/types'
import { queryKeys } from '../../lib/query-keys'
import { AgingView } from '../property/BillingPages'
import { BillDetailView } from '../property/BillDetailView'
import { BillTable } from '../property/BillTable'
import { PageHeader, QueryState, Section, Select, StatGrid, StatTile } from '../property/ui'
import { errorMessage } from '../../lib/property/errors'

function usePlatform<T>(resource: string, path: string, params: Record<string, string | undefined> = {}) {
  return useQuery({
    queryKey: queryKeys.platformPropertyBilling(resource, { path, ...params }),
    queryFn: () => apiClient.get<T>(`${path}${toQueryString(params)}`),
  })
}

interface GlobalSummary {
  workspaces: number
  active_subscriptions: number
  properties: number
  residents: number
  total_bills: number
  total_billed_cents: number
  total_collected_cents: number
  total_outstanding_cents: number
  total_overdue_cents: number
  total_payments: number
  total_payments_cents: number
  electricity_units: string
  current_period: PeriodSummary
}

interface WorkspaceRow {
  id: string
  name: string
  slug: string
  is_active: boolean
  closed_at: string | null
  owners: string[]
  subscription_status: string | null
  plan_name: string | null
  properties: number
  residents: number
  bills: number
  billed_cents: number
  collected_cents: number
  outstanding_cents: number
  overdue_bills: number
  overdue_cents: number
}

// Mixed currencies are not supported within one workspace; the global roll-up
// is labelled in INR, this deployment's property-billing default.
const CURRENCY = 'INR'

export function PropertyBillingAdminPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const filters = {
    search: params.get('search') ?? undefined,
    status: params.get('status') ?? undefined,
    payment_status: params.get('payment_status') ?? undefined,
    period: params.get('period') ?? undefined,
    tenant: params.get('tenant') ?? undefined,
  }
  const summary = usePlatform<GlobalSummary>('summary', '/platform/property-billing/summary/', { tenant: filters.tenant })
  const workspaces = usePlatform<Paginated<WorkspaceRow>>('workspaces', '/platform/property-billing/workspaces/')
  const bills = usePlatform<Paginated<Bill>>('bills', '/platform/property-billing/bills/', filters)
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const s = summary.data
  return (
    <div>
      <PageHeader title="Property billing" description="Resident → owner billing across every workspace. Separate from Tenora subscriptions." />
      <QueryState isLoading={summary.isLoading} error={summary.error} onRetry={() => summary.refetch()} label="the global summary" />
      {s && (
        <StatGrid>
          <StatTile label="Workspaces" value={s.workspaces} hint={`${s.active_subscriptions} active Tenora subscriptions`} />
          <StatTile label="Property bills" value={s.total_bills} hint={`${s.properties} properties · ${s.residents} residents`} />
          <StatTile label="Billed" value={money(s.total_billed_cents, CURRENCY)} />
          <StatTile label="Collected" value={money(s.total_collected_cents, CURRENCY)} tone="success" hint={`${s.total_payments} payments`} />
          <StatTile label="Outstanding" value={money(s.total_outstanding_cents, CURRENCY)} />
          <StatTile label="Overdue" value={money(s.total_overdue_cents, CURRENCY)} tone={s.total_overdue_cents ? 'danger' : undefined} />
          <StatTile label="Electricity" value={`${formatDecimal(s.electricity_units)} units`} />
        </StatGrid>
      )}

      <Section title="Workspaces">
        <QueryState isLoading={workspaces.isLoading} error={workspaces.error} label="workspaces" />
        {workspaces.data && workspaces.data.results.length === 0 && <EmptyState headline="No workspaces" description="Nothing registered yet." />}
        {workspaces.data && workspaces.data.results.length > 0 && (
          <Table
            caption="Workspaces with property billing"
            rows={workspaces.data.results}
            rowKey={(w) => w.id}
            onRowClick={(w) => navigate(`/admin/property-billing/${w.id}`)}
            columns={[
              { key: 'name', header: 'Workspace', render: (w) => w.name },
              { key: 'owner', header: 'Owner', render: (w) => w.owners.join(', ') || '—' },
              { key: 'plan', header: 'Tenora plan', render: (w) => (w.plan_name ? `${w.plan_name} · ${w.subscription_status}` : 'No subscription') },
              { key: 'residents', header: 'Residents', numeric: true, render: (w) => w.residents },
              { key: 'billed', header: 'Billed', numeric: true, render: (w) => money(w.billed_cents, CURRENCY) },
              { key: 'collected', header: 'Collected', numeric: true, render: (w) => money(w.collected_cents, CURRENCY) },
              { key: 'outstanding', header: 'Outstanding', numeric: true, render: (w) => money(w.outstanding_cents, CURRENCY) },
              { key: 'overdue', header: 'Overdue', numeric: true, render: (w) => (w.overdue_bills ? `${w.overdue_bills} · ${money(w.overdue_cents, CURRENCY)}` : '—') },
            ]}
          />
        )}
      </Section>

      <Section title="Search bills">
        <form className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-5" onSubmit={(e) => e.preventDefault()} aria-label="Global bill filters">
          <Select label="Workspace" value={filters.tenant ?? ''} onChange={(e) => set('tenant', e.target.value)}>
            <option value="">All</option>
            {workspaces.data?.results.map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </Select>
          <Input label="Month" type="month" value={filters.period ?? ''} onChange={(e) => set('period', e.target.value)} />
          <Select label="Status" value={filters.status ?? ''} onChange={(e) => set('status', e.target.value)}>
            <option value="">All</option>
            <option value="UNPAID">Unpaid</option>
            <option value="OVERDUE">Overdue</option>
            <option value="PAID">Paid</option>
            <option value="DRAFT">Draft</option>
            <option value="CANCELLED">Cancelled</option>
          </Select>
          <Select label="Payment" value={filters.payment_status ?? ''} onChange={(e) => set('payment_status', e.target.value)}>
            <option value="">All</option>
            <option value="UNPAID">Unpaid</option>
            <option value="PARTIALLY_PAID">Partial</option>
            <option value="PAID">Paid</option>
          </Select>
          <Input label="Resident / unit / bill" value={filters.search ?? ''} onChange={(e) => set('search', e.target.value)} />
        </form>
        <QueryState isLoading={bills.isLoading} error={bills.error} label="bills" />
        {bills.data && bills.data.results.length === 0 && <p className="text-body text-secondary">No bills match.</p>}
        {bills.data && bills.data.results.length > 0 && (
          <BillTable bills={bills.data.results} showWorkspace hrefFor={(b) => `/admin/property-billing/bills/${b.id}`} caption="All property bills" />
        )}
      </Section>
    </div>
  )
}

interface MembershipRow {
  id: string
  email: string
  role: 'OWNER' | 'MEMBER'
  status: string
}

interface WorkspaceDetail {
  id: string
  name: string
  slug: string
  is_active: boolean
  closed_at: string | null
  memberships: MembershipRow[]
  subscription: { status: string; plan: { name: string } } | null
  properties: Array<Property & { units: Array<Unit & { leases: Lease[] }> }>
  residents: Array<Resident & { bills: number; billed_cents: number; paid_cents: number }>
  aging: AgingReport
  current_period: PeriodSummary
}

export function PropertyWorkspaceAdminPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { isRoot } = useCurrentUser()
  const detail = usePlatform<WorkspaceDetail>('workspace', '/platform/property-billing/workspaces/detail/', { id })
  const bills = usePlatform<Paginated<Bill>>('workspace-bills', '/platform/property-billing/bills/', { tenant: id })
  const setRole = useMutation({
    mutationFn: ({ membershipId, role }: { membershipId: string; role: string }) =>
      apiClient.patch(`/platform/memberships/detail/?id=${membershipId}`, { role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['global', 'platform', 'property-billing'] }),
  })
  const [openProperty, setOpenProperty] = useState<string | null>(null)
  if (!detail.data) return <QueryState isLoading={detail.isLoading} error={detail.error} onRetry={() => detail.refetch()} label="this workspace" />
  const w = detail.data
  return (
    <div>
      <p className="mb-4 text-label">
        <Link to="/admin/property-billing" className="text-secondary hover:text-primary">← Property billing</Link>
      </p>
      <PageHeader
        title={w.name}
        description={`${w.subscription ? `Tenora ${w.subscription.plan.name} · ${w.subscription.status}` : 'No Tenora subscription'}${w.closed_at ? ' · closed' : ''}${w.is_active ? '' : ' · suspended'}`}
      />
      <SummaryTilesPlatform summary={w.current_period} />

      <Section title="Members & roles">
        {setRole.error && <Alert variant="danger" className="mb-3">{errorMessage(setRole.error)}</Alert>}
        <ul className="flex flex-col gap-2">
          {w.memberships.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-subtle p-3">
              <span className="text-label text-primary">{m.email}</span>
              <div className="flex items-center gap-2">
                <Badge variant={m.role === 'OWNER' ? 'accent' : 'neutral'}>{m.role === 'OWNER' ? 'Owner' : 'Resident'}</Badge>
                <Badge variant={m.status === 'ACTIVE' ? 'success' : 'neutral'}>{m.status}</Badge>
                {isRoot && m.status === 'ACTIVE' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={setRole.isPending}
                    onClick={() => setRole.mutate({ membershipId: m.id, role: m.role === 'OWNER' ? 'MEMBER' : 'OWNER' })}
                  >
                    {m.role === 'OWNER' ? 'Demote to resident' : 'Promote to owner'}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
        {isRoot && <p className="mt-2 text-caption text-secondary">Root control, independent of plan. A workspace always keeps at least one owner. Audited.</p>}
      </Section>

      <Section title="Properties → units → leases">
        {w.properties.length === 0 && <p className="text-body text-secondary">No properties.</p>}
        <ul className="flex flex-col gap-2">
          {w.properties.map((p) => (
            <li key={p.id} className="rounded-md border border-subtle">
              <button type="button" className="flex w-full items-center justify-between p-3 text-left" onClick={() => setOpenProperty(openProperty === p.id ? null : p.id)} aria-expanded={openProperty === p.id}>
                <span className="text-label text-primary">{p.name}</span>
                <span className="text-caption text-secondary">{p.units.length} units</span>
              </button>
              {openProperty === p.id && (
                <ul className="border-t border-subtle p-3 text-caption">
                  {p.units.map((u) => (
                    <li key={u.id} className="py-1">
                      <span className="text-primary">Unit {u.identifier}</span> · {u.status}
                      {u.leases.map((l) => (
                        <span key={l.id} className="block pl-4 text-secondary">
                          {l.resident_name} · {money(l.monthly_rent_cents, CURRENCY)}/month · {formatDay(l.start_date)} – {l.end_date ? formatDay(l.end_date) : 'present'} · {l.status}
                        </span>
                      ))}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Residents">
        <Table
          caption="Workspace residents"
          rows={w.residents}
          rowKey={(r) => r.id}
          onRowClick={(r) => navigate(`/admin/property-billing/${w.id}/bills?resident=${r.id}`)}
          columns={[
            { key: 'name', header: 'Resident', render: (r) => r.display_name },
            { key: 'unit', header: 'Unit', render: (r) => (r.active_lease ? r.active_lease.unit_identifier : '—') },
            { key: 'bills', header: 'Bills', numeric: true, render: (r) => r.bills },
            { key: 'billed', header: 'Billed', numeric: true, render: (r) => money(r.billed_cents, CURRENCY) },
            { key: 'paid', header: 'Paid', numeric: true, render: (r) => money(r.paid_cents, CURRENCY) },
            { key: 'balance', header: 'Balance', numeric: true, render: (r) => money(r.billed_cents - r.paid_cents, CURRENCY) },
          ]}
        />
      </Section>

      <Section title="Aging">
        <AgingView report={w.aging} currency={CURRENCY} onRow={(billId) => navigate(`/admin/property-billing/bills/${billId}`)} />
      </Section>

      <Section title="Bills">
        {bills.data && <BillTable bills={bills.data.results} hrefFor={(b) => `/admin/property-billing/bills/${b.id}`} caption="Workspace bills" />}
      </Section>
    </div>
  )
}

function SummaryTilesPlatform({ summary }: { summary: PeriodSummary }) {
  return (
    <StatGrid>
      <StatTile label="Billed this month" value={money(summary.billed_cents, CURRENCY)} />
      <StatTile label="Collected" value={money(summary.collected_cents, CURRENCY)} tone="success" />
      <StatTile label="Outstanding" value={money(summary.outstanding_cents, CURRENCY)} />
      <StatTile label="Overdue" value={money(summary.overdue_cents, CURRENCY)} tone={summary.overdue_cents ? 'danger' : undefined} />
    </StatGrid>
  )
}

export function PropertyWorkspaceBillsAdminPage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const bills = usePlatform<Paginated<Bill>>('workspace-bills', '/platform/property-billing/bills/', {
    tenant: id,
    resident: params.get('resident') ?? undefined,
  })
  return (
    <div>
      <p className="mb-4 text-label">
        <Link to={`/admin/property-billing/${id}`} className="text-secondary hover:text-primary">← Workspace</Link>
      </p>
      <PageHeader title="Billing history" />
      <QueryState isLoading={bills.isLoading} error={bills.error} label="bills" />
      {bills.data && <BillTable bills={bills.data.results} hrefFor={(b) => `/admin/property-billing/bills/${b.id}`} caption="Resident billing history" />}
    </div>
  )
}

export function PropertyBillAdminPage() {
  const { billId = '' } = useParams()
  const bill = usePlatform<BillDetail>('bill', '/platform/property-billing/bills/detail/', { id: billId })
  if (!bill.data) return <QueryState isLoading={bill.isLoading} error={bill.error} onRetry={() => bill.refetch()} label="this bill" />
  return (
    <div className="max-w-[960px]">
      <p className="mb-4 text-label">
        <Link to={bill.data.tenant_id ? `/admin/property-billing/${bill.data.tenant_id}` : '/admin/property-billing'} className="text-secondary hover:text-primary">
          ← {bill.data.tenant_name ?? 'Property billing'}
        </Link>
      </p>
      <BillDetailView bill={bill.data} mode="platform" proofPath={(readingId) => `/platform/property-billing/reading-proof/?id=${readingId}`} />
    </div>
  )
}
