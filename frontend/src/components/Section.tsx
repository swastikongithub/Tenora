/**
 * A numbered editorial section (Tenora redesign — design-reference-analysis
 * §3 / §5 "numbered primitives give a multi-part concept a spine", §8.4).
 *
 * Replaces the "card, then card, then card" grid. Each section is a `01 / 02 /
 * 03` index set tight against the title, a hairline rule under the title row,
 * an optional right-aligned aside (a count, a link), then the content — on the
 * bare page ground: no border, no elevation.
 *
 * The index is decorative (`aria-hidden`, `text-muted` — a de-emphasised glyph,
 * the token's documented-allowed use); the `<h2>` carries the meaning and the
 * outline position.
 *
 * Promoted from the approved UI-03 prototype (`src/prototype/components/
 * Section.tsx`).
 */

import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export interface SectionProps {
  /** "01", "02", … */
  index: string
  title: string
  /** Right-aligned in the title row — a count, a link. */
  aside?: ReactNode
  children: ReactNode
  className?: string
}

export function Section({
  index,
  title,
  aside,
  children,
  className,
}: SectionProps) {
  return (
    <section className={cn('min-w-0', className)}>
      <div className="flex items-baseline justify-between gap-4 border-b border-subtle pb-2">
        <h2 className="flex items-baseline gap-3 text-h2 text-primary">
          <span
            aria-hidden="true"
            className="font-mono text-caption font-normal text-muted"
          >
            {index}
          </span>
          {title}
        </h2>
        {aside && (
          <div className="shrink-0 text-caption text-secondary">{aside}</div>
        )}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  )
}
