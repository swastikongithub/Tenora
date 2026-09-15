/**
 * Report tables shared by the owner Reports page and the platform-admin
 * property billing page (plan §16: "same metrics aggregated globally"). Every
 * number is the server's; nothing is summed or split here.
 */

import { Table } from '../../components'
import { formatDecimal, formatPeriod, money } from '../../lib/property/format'
import type { ElectricityUnitRow, MonthlyReportRow } from '../../lib/property/types'
import { Section } from './ui'

export function MonthlyReportTables({ monthly, currency, title }: { monthly: MonthlyReportRow[]; currency: string; title: string }) {
  const rows = [...monthly].reverse()
  return (
    <>
      <Section title={title}>
        <Table
          caption="Monthly billing report"
          rows={rows}
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
      <Section title="Collections by charge">
        <p className="mb-3 max-w-[48rem] text-body text-secondary">
          A payment is recorded against a whole bill, so only fully paid bills can be split into rent, electricity and other
          charges. Money received on bills that are still partly paid is shown separately.
        </p>
        <Table
          caption="Collections by charge"
          rows={rows}
          rowKey={(r) => r.period}
          columns={[
            { key: 'period', header: 'Month', render: (r) => formatPeriod(`${r.period}-01`) },
            { key: 'rent', header: 'Rent collected', numeric: true, render: (r) => money(r.rent_collected_cents, currency) },
            { key: 'elec', header: 'Electricity collected', numeric: true, render: (r) => money(r.electricity_collected_cents, currency) },
            { key: 'other', header: 'Other collected', numeric: true, render: (r) => money(r.other_collected_cents, currency) },
            { key: 'partial', header: 'On partly paid bills', numeric: true, render: (r) => money(r.collected_unallocated_cents, currency) },
            { key: 'total', header: 'Total collected', numeric: true, render: (r) => money(r.collected_cents, currency) },
          ]}
        />
      </Section>
    </>
  )
}

export function ElectricityByUnitTable({ rows, currency, showWorkspace = false }: { rows: ElectricityUnitRow[]; currency: string; showWorkspace?: boolean }) {
  if (rows.length === 0) {
    return <p className="text-body text-secondary">No issued electricity charges for this month.</p>
  }
  return (
    <Table
      caption="Electricity by unit"
      rows={rows}
      rowKey={(r) => `${r.tenant_id}-${r.property_name}-${r.unit_identifier}`}
      columns={[
        ...(showWorkspace ? [{ key: 'workspace', header: 'Workspace', render: (r: ElectricityUnitRow) => r.tenant_name ?? '—' }] : []),
        { key: 'unit', header: 'Unit', render: (r) => `${r.unit_identifier} · ${r.property_name}` },
        { key: 'units', header: 'Units', numeric: true, render: (r) => formatDecimal(r.units) },
        { key: 'amount', header: 'Amount', numeric: true, render: (r) => money(r.amount_cents, currency) },
      ]}
    />
  )
}
