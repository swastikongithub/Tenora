/**
 * Overline / eyebrow (Tenora redesign — design-reference-analysis §6.3 / §8.3).
 *
 * A short, uppercase, wide-tracked micro-label that sits above a heading or
 * labels a value / a section. A first-class type role, distinct from headings
 * and body — a quiet signature the redesign leans on instead of boxed chrome.
 *
 * NOT a heading: it must never enter the heading outline. Renders a `<span>` by
 * default; pass `as="p"` for a block, or `as="dt"` inside a description list.
 * Colour is a prop: `secondary` (default) or `accent`. Uses existing tokens
 * only — no new value.
 *
 * Promoted from the approved UI-03 prototype (`src/prototype/components/
 * Overline.tsx`), rebuilt with plain utilities (no `[data-prototype]` scope).
 */

import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export interface OverlineProps {
  children: ReactNode
  /** `span` (default, inline), `p` (block), or `dt` (a description-list term). */
  as?: 'span' | 'p' | 'dt'
  tone?: 'secondary' | 'accent'
  className?: string
}

const BASE = 'text-caption font-semibold uppercase tracking-[0.14em]'

export function Overline({
  children,
  as: Tag = 'span',
  tone = 'secondary',
  className,
}: OverlineProps) {
  return (
    <Tag
      className={cn(
        BASE,
        tone === 'accent' ? 'text-accent-500' : 'text-secondary',
        className,
      )}
    >
      {children}
    </Tag>
  )
}
