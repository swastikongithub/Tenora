/**
 * A borderless spec-sheet (Tenora redesign — design-reference-analysis §6, §8.6
 * "depth from hairlines, not boxes").
 *
 * The editorial replacement for a `<Card>` wrapped around a `<dl>` (the
 * "Plan" / "Workspace" panels). Aligned term / value rows, hairline-separated,
 * on the page ground. No box.
 *
 * Term is a small wide label in `text-secondary`; value is `text-body`
 * `text-primary`. Machine values (slug, plan code, dates) are set monospace by
 * the caller (§6).
 *
 * Promoted from the approved UI-03 prototype (`src/prototype/components/
 * DataList.tsx`).
 */

import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export interface DataRow {
  term: string
  children: ReactNode
}

export interface DataListProps {
  rows: DataRow[]
  className?: string
}

export function DataList({ rows, className }: DataListProps) {
  return (
    <dl className={cn('flex flex-col', className)}>
      {rows.map((row, i) => (
        <div
          key={row.term}
          className={cn(
            'flex flex-col gap-1 py-2.5 sm:flex-row sm:items-baseline sm:gap-6',
            i > 0 && 'border-t border-subtle',
          )}
        >
          <dt className="text-caption text-secondary sm:w-36 sm:shrink-0">
            {row.term}
          </dt>
          <dd className="min-w-0 text-body text-primary">{row.children}</dd>
        </div>
      ))}
    </dl>
  )
}
