import type { ReactNode } from 'react'
import { cn } from '../lib/cn'
import { useMediaQuery } from './use-media-query'

export type SortDirection = 'asc' | 'desc'

export interface Column<T> {
  key: string
  header: string
  /** Right-align the cell and use tabular figures (money, counts, IDs). */
  numeric?: boolean
  sortable?: boolean
  /** Custom cell renderer. Defaults to `String(row[key])`. */
  render?: (row: T) => ReactNode
}

export interface TableProps<T> {
  columns: Array<Column<T>>
  rows: T[]
  rowKey: (row: T) => string | number
  /** Key of the currently selected row (accent-subtle bg + accent left border). */
  selectedRowKey?: string | number
  onRowClick?: (row: T) => void
  /** Controlled sort state; render a direction affordance on the active column. */
  sort?: { key: string; direction: SortDirection }
  onSortChange?: (key: string) => void
  /** Accessible caption for the table. */
  caption?: string
  /**
   * Mobile (<768px) card renderer. When provided, below the breakpoint the table
   * is replaced by a stacked `<ul>` of these cards — not a shrunken or
   * horizontally-scrolling table (UI spec §C.7). Omit it and the table renders
   * at every width (existing behaviour, unchanged).
   */
  renderMobileCard?: (row: T) => ReactNode
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  selectedRowKey,
  onRowClick,
  sort,
  onSortChange,
  caption,
  renderMobileCard,
}: TableProps<T>) {
  // §C.7: below the tablet breakpoint a data table becomes a stacked card list,
  // never a horizontally-scrolling shrunken table. `useMediaQuery` defaults to
  // `true` where `matchMedia` is unavailable, so the table is the fallback.
  const wide = useMediaQuery('(min-width: 768px)')

  if (!wide && renderMobileCard) {
    return (
      <ul aria-label={caption} className="flex flex-col gap-3">
        {rows.map((row) => {
          const key = rowKey(row)
          const selected = selectedRowKey != null && key === selectedRowKey
          const className = cn(
            'block w-full rounded-lg border bg-raised p-4 text-left',
            selected
              ? 'border-accent-600 bg-accent-subtle'
              : 'border-subtle',
            onRowClick &&
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
          )
          return (
            <li key={key}>
              {onRowClick ? (
                <button
                  type="button"
                  onClick={() => onRowClick(row)}
                  aria-selected={selected || undefined}
                  className={className}
                >
                  {renderMobileCard(row)}
                </button>
              ) : (
                <div
                  aria-selected={selected || undefined}
                  className={className}
                >
                  {renderMobileCard(row)}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <table className="w-full border-collapse text-body text-primary">
      {caption && <caption className="sr-only">{caption}</caption>}

      <thead>
        <tr className="bg-raised">
          {columns.map((col) => {
            const active = sort?.key === col.key
            const ariaSort = !col.sortable
              ? undefined
              : active
                ? sort.direction === 'asc'
                  ? 'ascending'
                  : 'descending'
                : 'none'

            return (
              <th
                key={col.key}
                scope="col"
                aria-sort={ariaSort}
                className={cn(
                  'h-10 px-4 text-label font-medium text-secondary',
                  col.numeric ? 'text-right' : 'text-left',
                )}
              >
                {col.sortable ? (
                  <button
                    type="button"
                    onClick={() => onSortChange?.(col.key)}
                    className={cn(
                      'inline-flex items-center gap-1',
                      col.numeric && 'flex-row-reverse',
                      'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
                    )}
                  >
                    {col.header}
                    <SortGlyph
                      direction={active ? sort.direction : undefined}
                    />
                  </button>
                ) : (
                  col.header
                )}
              </th>
            )
          })}
        </tr>
      </thead>

      <tbody>
        {rows.map((row) => {
          const key = rowKey(row)
          const selected = selectedRowKey != null && key === selectedRowKey

          return (
            <tr
              key={key}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              aria-selected={selected || undefined}
              className={cn(
                'h-[52px] border-b border-subtle',
                // Every row reserves a 2px left border so selecting one never
                // shifts the layout — only its color changes.
                'border-l-2 border-l-transparent',
                onRowClick && 'cursor-pointer',
                selected
                  ? 'border-l-accent-600 bg-accent-subtle'
                  : 'hover:bg-overlay',
              )}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn(
                    'px-4',
                    col.numeric ? 'num text-right' : 'text-left',
                  )}
                >
                  {col.render
                    ? col.render(row)
                    : String((row as Record<string, unknown>)[col.key] ?? '')}
                </td>
              ))}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function SortGlyph({ direction }: { direction?: SortDirection }) {
  return (
    <span aria-hidden="true" className="text-muted">
      {direction === 'asc' ? '▲' : direction === 'desc' ? '▼' : '↕'}
    </span>
  )
}
