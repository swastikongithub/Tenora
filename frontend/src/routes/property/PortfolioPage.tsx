/**
 * /billing/portfolio — billing totals across every workspace the signed-in
 * owner controls (plan §16.2). The one billing view that is NOT scoped to the
 * active workspace: it calls a global endpoint whose workspace list comes from
 * the user's own memberships on the server, and it never adds amounts in
 * different currencies together. Opening a workspace goes through the normal
 * switcher, so the per-workspace pages stay tenant-scoped as before.
 */

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Badge, Button, EmptyState, Input, Table } from '../../components'
import { apiClient } from '../../lib/api-client'
import { currentPeriodParam, formatPeriod, money } from '../../lib/property/format'
import type { BillingPortfolio } from '../../lib/property/types'
import { queryKeys } from '../../lib/query-keys'
import { useTenant } from '../../lib/tenant'
import { QueryState, Section, StatGrid, StatTile } from './ui'

export function PortfolioPage() {
  const [period, setPeriod] = useState(currentPeriodParam())
  const { currentTenantId, switchTenant } = useTenant()
  const navigate = useNavigate()
  const portfolio = useQuery<BillingPortfolio>({
    queryKey: queryKeys.billingPortfolio(period),
    queryFn: () => apiClient.get<BillingPortfolio>(`/account/billing-portfolio/?period=${encodeURIComponent(period)}`),
    enabled: Boolean(period),
  })

  const open = (tenantId: string) => {
    if (tenantId !== currentTenantId) switchTenant(tenantId)
    navigate('/billing')
  }

  const data = portfolio.data
  return (
    <div>
      <p className="mb-4 max-w-[48rem] text-body text-secondary">
        Every workspace you own, side by side. Billed and collected are for the selected month; overdue is everything
        past its due date today, in any month.
      </p>
      <div className="mb-6 max-w-[14rem]">
        <Input label="Billing month" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
      </div>
      <QueryState isLoading={portfolio.isLoading} error={portfolio.error} onRetry={() => portfolio.refetch()} label="your workspaces’ billing" />

      {data && data.workspaces.length === 0 && (
        <EmptyState headline="No workspaces" description="Workspaces you own appear here." />
      )}

      {data &&
        data.totals.map((total) => (
          <Section
            key={total.currency}
            title={
              data.totals.length > 1
                ? `${total.currency} workspaces · ${formatPeriod(`${data.period}-01`)}`
                : `All workspaces · ${formatPeriod(`${data.period}-01`)}`
            }
          >
            <StatGrid>
              <StatTile label="Billed" value={money(total.billed_cents, total.currency)} hint={`${total.workspaces} workspace${total.workspaces === 1 ? '' : 's'}`} />
              <StatTile label="Collected" value={money(total.collected_cents, total.currency)} tone="success" />
              <StatTile label="Outstanding this month" value={money(total.outstanding_cents, total.currency)} />
              <StatTile
                label="Overdue now"
                value={money(total.total_overdue_cents, total.currency)}
                tone={total.total_overdue_cents > 0 ? 'danger' : undefined}
                hint={`${money(total.total_outstanding_cents, total.currency)} outstanding in total`}
              />
            </StatGrid>
          </Section>
        ))}

      {data && data.workspaces.length > 0 && (
        <Section title="By workspace">
          <Table
            caption="Billing by workspace"
            rows={data.workspaces}
            rowKey={(w) => w.id}
            columns={[
              {
                key: 'name',
                header: 'Workspace',
                render: (w) => (
                  <span className="inline-flex flex-wrap items-center gap-2">
                    {w.name}
                    {w.id === currentTenantId && <Badge variant="neutral">Current</Badge>}
                    {!w.is_active && <Badge variant="warning">Suspended</Badge>}
                  </span>
                ),
              },
              { key: 'billed', header: 'Billed', numeric: true, render: (w) => money(w.billed_cents, w.currency) },
              { key: 'collected', header: 'Collected', numeric: true, render: (w) => money(w.collected_cents, w.currency) },
              { key: 'outstanding', header: 'Outstanding', numeric: true, render: (w) => money(w.outstanding_cents, w.currency) },
              {
                key: 'overdue',
                header: 'Overdue now',
                numeric: true,
                render: (w) => (
                  <span className={w.total_overdue_cents > 0 ? 'text-danger' : undefined}>{money(w.total_overdue_cents, w.currency)}</span>
                ),
              },
              { key: 'drafts', header: 'Drafts', numeric: true, render: (w) => w.bills_draft },
              {
                key: 'open',
                header: '',
                render: (w) =>
                  w.is_active ? (
                    <Button size="sm" variant="ghost" onClick={() => open(w.id)} aria-label={`Open billing for ${w.name}`}>
                      Open billing
                    </Button>
                  ) : null,
              },
            ]}
          />
        </Section>
      )}
    </div>
  )
}
