import { useNavigate } from 'react-router-dom'

import { Table, type Column } from '../../components'
import { formatDay, formatPeriod, money } from '../../lib/property/format'
import type { Bill } from '../../lib/property/types'
import { BillStatusBadge } from './ui'

interface BillTableProps {
  bills: Bill[]
  /** Where a row links to — owner/resident `/bills/:id`, platform `/admin/...`. */
  hrefFor?: (bill: Bill) => string
  showResident?: boolean
  showWorkspace?: boolean
  caption?: string
}

export function BillTable({
  bills,
  hrefFor = (b) => `/bills/${b.id}`,
  showResident = true,
  showWorkspace = false,
  caption = 'Bills',
}: BillTableProps) {
  const navigate = useNavigate()
  const columns: Array<Column<Bill>> = [
    ...(showWorkspace
      ? [{ key: 'workspace', header: 'Workspace', render: (b: Bill) => b.tenant_name ?? '—' }]
      : []),
    { key: 'period', header: 'Period', render: (b) => formatPeriod(b.period_start) },
    { key: 'unit', header: 'Unit', render: (b) => `${b.unit_identifier} · ${b.property_name}` },
    ...(showResident ? [{ key: 'resident', header: 'Resident', render: (b: Bill) => b.resident_name }] : []),
    { key: 'rent', header: 'Rent', numeric: true, render: (b) => money(b.rent_cents, b.currency) },
    { key: 'electricity', header: 'Electricity', numeric: true, render: (b) => money(b.electricity_cents, b.currency) },
    { key: 'total', header: 'Total', numeric: true, render: (b) => money(b.total_cents, b.currency) },
    { key: 'paid', header: 'Paid', numeric: true, render: (b) => money(b.amount_paid_cents, b.currency) },
    { key: 'due', header: 'Due', numeric: true, render: (b) => money(b.amount_due_cents, b.currency) },
    { key: 'due_date', header: 'Due date', render: (b) => formatDay(b.due_date) },
    {
      key: 'status',
      header: 'Status',
      render: (b) => <BillStatusBadge status={b.display_status} overdueDays={b.overdue_days} />,
    },
  ]
  return (
    <Table
      caption={caption}
      columns={columns}
      rows={bills}
      rowKey={(b) => b.id}
      onRowClick={(b) => navigate(hrefFor(b))}
      renderMobileCard={(b) => (
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-label text-primary">{formatPeriod(b.period_start)}</span>
            <BillStatusBadge status={b.display_status} overdueDays={b.overdue_days} />
          </div>
          <span className="text-caption text-secondary">
            Unit {b.unit_identifier}
            {showResident ? ` · ${b.resident_name}` : ''}
          </span>
          <span className="font-mono text-label tabular-nums text-primary">
            {money(b.total_cents, b.currency)} · due {money(b.amount_due_cents, b.currency)}
          </span>
        </div>
      )}
    />
  )
}
