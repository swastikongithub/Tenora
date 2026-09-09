import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Table, type Column, type TableProps } from '../Table'

interface Plan {
  id: string
  name: string
  priceCents: number
}

const PLANS: Plan[] = [
  { id: 'p1', name: 'Starter', priceCents: 900 },
  { id: 'p2', name: 'Pro', priceCents: 2900 },
]

const columns: Array<Column<Plan>> = [
  { key: 'name', header: 'Plan', sortable: true },
  { key: 'priceCents', header: 'Price', numeric: true, sortable: true },
]

function renderTable(props: Partial<TableProps<Plan>> = {}) {
  return render(
    <Table
      columns={columns}
      rows={PLANS}
      rowKey={(r) => r.id}
      caption="Plans"
      {...props}
    />,
  )
}

describe('Table', () => {
  it('renders a real table with scoped column headers', () => {
    renderTable()
    expect(screen.getByRole('table', { name: 'Plans' })).toBeInTheDocument()
    const headers = screen.getAllByRole('columnheader')
    expect(headers).toHaveLength(2)
    headers.forEach((h) => expect(h).toHaveAttribute('scope', 'col'))
  })

  it('right-aligns numeric columns in header and body', () => {
    renderTable()
    const priceHeader = screen.getByRole('columnheader', { name: /Price/ })
    expect(priceHeader).toHaveClass('text-right')

    const priceCell = screen.getByText('2900')
    expect(priceCell).toHaveClass('text-right')
  })

  it('marks the selected row and keeps a reserved left border on every row', () => {
    renderTable({ selectedRowKey: 'p2' })
    const rows = screen.getAllByRole('row').slice(1) // drop the header row
    const [starter, pro] = rows

    expect(pro).toHaveAttribute('aria-selected', 'true')
    expect(pro).toHaveClass('border-l-accent-600')
    expect(starter).not.toHaveAttribute('aria-selected')
    // Reserved transparent border on all rows so selection never shifts layout.
    rows.forEach((r) => expect(r).toHaveClass('border-l-2'))
  })

  it('reflects controlled sort state via aria-sort and calls onSortChange', async () => {
    const onSortChange = vi.fn()
    renderTable({
      sort: { key: 'priceCents', direction: 'desc' },
      onSortChange,
    })

    const priceHeader = screen.getByRole('columnheader', { name: /Price/ })
    expect(priceHeader).toHaveAttribute('aria-sort', 'descending')

    const planHeader = screen.getByRole('columnheader', { name: /Plan/ })
    expect(planHeader).toHaveAttribute('aria-sort', 'none')

    await userEvent.click(within(planHeader).getByRole('button'))
    expect(onSortChange).toHaveBeenCalledWith('name')
  })

  it('fires onRowClick with the row data', async () => {
    const onRowClick = vi.fn()
    renderTable({ onRowClick })
    await userEvent.click(screen.getByText('Starter'))
    expect(onRowClick).toHaveBeenCalledWith(PLANS[0])
  })
})

describe('Table — mobile stacked cards (§C.7)', () => {
  const originalMatchMedia = window.matchMedia

  function stubNarrow() {
    window.matchMedia = ((query: string) => ({
      matches: false, // < 768px
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia
  }

  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it('renders a card list, not a table, below the breakpoint when renderMobileCard is given', () => {
    stubNarrow()
    renderTable({
      renderMobileCard: (p) => <span>{`${p.name} — ${p.priceCents}`}</span>,
    })

    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    const list = screen.getByRole('list', { name: 'Plans' })
    expect(within(list).getByText('Starter — 900')).toBeInTheDocument()
    expect(within(list).getByText('Pro — 2900')).toBeInTheDocument()
  })

  it('still renders a table below the breakpoint when no renderMobileCard is given', () => {
    stubNarrow()
    renderTable()
    expect(screen.getByRole('table', { name: 'Plans' })).toBeInTheDocument()
  })
})
