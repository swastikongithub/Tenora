/**
 * The resident portal (plan §13, §16.4) — intentionally narrow. Everything here
 * is the authenticated resident's OWN data: /api/residency/, /api/bills/,
 * /api/receipts/ are filtered server-side on the resident linked to the signed-in
 * user. There is no resident id in any request.
 */

import { Link } from 'react-router-dom'

import { Alert, EmptyState } from '../../components'
import { formatDay, formatPeriod, money } from '../../lib/property/format'
import { usePropertyQuery, useWorkspaceRole } from '../../lib/property/hooks'
import type { Bill, Paginated, Residency } from '../../lib/property/types'
import { BillTable } from './BillTable'
import { BillStatusBadge, PageHeader, QueryState, Section, StatGrid, StatTile } from './ui'

export function ResidentHomePage() {
  const { tenantName } = useWorkspaceRole()
  const residency = usePropertyQuery<Residency>('residency', '/residency/')
  const bills = usePropertyQuery<Paginated<Bill>>('bills', '/bills/', { page_size: '6' })
  const data = residency.data
  const latest = data?.latest_bill
  return (
    <div className="max-w-[960px]">
      <PageHeader
        eyebrow={tenantName}
        title={data?.resident ? `Welcome, ${data.resident.display_name.split(' ')[0]}` : 'Welcome'}
        description={
          data?.lease
            ? `${data.lease.property_name} · Unit ${data.lease.unit_identifier}`
            : 'Your property owner hasn’t assigned your unit yet.'
        }
      />
      <QueryState isLoading={residency.isLoading} error={residency.error} onRetry={() => residency.refetch()} label="your residency" />
      {data && (
        <StatGrid>
          <StatTile label="Outstanding" value={money(data.outstanding_cents ?? 0, latest?.currency)} />
          <StatTile label="Overdue bills" value={data.overdue_bills ?? 0} tone={data.overdue_bills ? 'danger' : undefined} />
          {data.lease && <StatTile label="Monthly rent" value={money(data.lease.monthly_rent_cents, latest?.currency)} hint={`Since ${formatDay(data.lease.start_date)}`} />}
        </StatGrid>
      )}
      <Section title="Current bill">
        {latest ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-subtle bg-raised p-5">
            <div>
              <p className="text-label text-secondary">{formatPeriod(latest.period_start)}</p>
              <p className="font-mono text-display tabular-nums text-primary">{money(latest.total_cents, latest.currency)}</p>
              <p className="text-caption text-secondary">Due {formatDay(latest.due_date)}</p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <BillStatusBadge status={latest.display_status} overdueDays={latest.overdue_days} />
              <Link
                to={`/bills/${latest.id}`}
                className="inline-flex h-8 items-center rounded-md bg-accent-600 px-3 text-label text-[var(--color-base)]"
              >
                View bill
              </Link>
            </div>
          </div>
        ) : (
          <EmptyState headline="No bills yet" description="Your bills appear here once your property owner publishes them." />
        )}
      </Section>
      <Section title="Previous bills" actions={<Link to="/billing-history" className="text-label text-accent-500 underline">Full history</Link>}>
        {bills.data && bills.data.results.length > 0 && <BillTable bills={bills.data.results} showResident={false} caption="Recent bills" />}
      </Section>
    </div>
  )
}

export function ResidentBillsPage({ mode }: { mode: 'open' | 'history' }) {
  const { tenantName } = useWorkspaceRole()
  const bills = usePropertyQuery<Paginated<Bill>>('bills', '/bills/', mode === 'open' ? { status: 'UNPAID' } : { page_size: '200' })
  return (
    <div className="max-w-[1080px]">
      <PageHeader
        eyebrow={tenantName}
        title={mode === 'open' ? 'My bills' : 'Billing history'}
        description={
          mode === 'open'
            ? 'Bills with an amount still due. Overdue days are calculated by the server from each due date.'
            : 'Every bill issued to you: rent, electricity readings, other charges, payments and receipts.'
        }
      />
      <QueryState isLoading={bills.isLoading} error={bills.error} onRetry={() => bills.refetch()} label="your bills" />
      {bills.data?.results.length === 0 && (
        <EmptyState headline={mode === 'open' ? 'Nothing due' : 'No bills yet'} description={mode === 'open' ? 'You have no unpaid bills.' : 'Your bills appear here once published.'} />
      )}
      {bills.data && bills.data.results.length > 0 && (
        <>
          {mode === 'open' && bills.data.results.some((b) => b.display_status === 'OVERDUE') && (
            <Alert variant="danger" className="mb-4">You have overdue bills. Contact your property owner to arrange payment.</Alert>
          )}
          <BillTable bills={bills.data.results} showResident={false} caption={mode === 'open' ? 'Unpaid bills' : 'Billing history'} />
        </>
      )}
    </div>
  )
}
