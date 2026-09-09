/**
 * The machine-readout line (Tenora redesign — design-reference-analysis §2.1
 * "label + tabular figure + status word, no chart chrome", §6.2).
 *
 * A page's primary quantitative facts stated inline as `figure · figure ·
 * figure` under a hairline — monospace, tabular, no boxes, no chart. This is
 * where the "system pulse" idea lives in the redesign: the readout that belongs
 * to a page's opening statement, not a separate labelled strip.
 *
 * A status dot is never the only signal — its word is always present (§C.8).
 *
 * Promoted from the approved UI-03 prototype (`src/prototype/components/
 * Readout.tsx`).
 */

import { cn } from '../lib/cn'

export type ReadoutTone = 'success' | 'warning' | 'danger' | 'neutral'

export interface ReadoutItem {
  value: string
  /** A small dot before the value; the word still carries the meaning. */
  tone?: ReadoutTone
}

const DOT: Record<ReadoutTone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  neutral: 'bg-neutral',
}

export interface ReadoutProps {
  items: ReadoutItem[]
  className?: string
}

export function Readout({ items, className }: ReadoutProps) {
  return (
    <p
      className={cn(
        'flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-subtle pt-3 font-mono text-body text-primary',
        className,
      )}
    >
      {items.map((item, i) => (
        <span key={item.value} className="flex items-center gap-1.5">
          {item.tone && (
            <span
              aria-hidden="true"
              className={cn('size-1.5 shrink-0 rounded-full', DOT[item.tone])}
            />
          )}
          <span className="num">{item.value}</span>
          {i < items.length - 1 && (
            <span aria-hidden="true" className="ml-2.5 text-muted">
              ·
            </span>
          )}
        </span>
      ))}
    </p>
  )
}
