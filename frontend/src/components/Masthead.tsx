/**
 * The editorial page opener (Tenora redesign — design-reference-analysis §4.4,
 * §6.3, §8.3).
 *
 * Replaces the terse `h1 + muted line` (and, on Overview, the KPI-card row):
 * the page STATES its primary fact once, large, in the composed register
 * (`text-edge`), with the supporting figures in the `readout` line below it.
 * Everything sits on the bare page ground — no card.
 *
 *   <Overline>   the page's domain area — e.g. "OVERVIEW"
 *   <h1>         the stated primary fact (a ReactNode, so a status word can
 *                carry semantic colour). `text-display sm:text-edge` — the
 *                fixed step-down that keeps 44px off a phone.
 *   <p> lede     one plain line, secondary — the "principle → consequence" voice
 *   {readout}    optional <Readout> (figures, monospace, hairline above)
 *
 * Promoted from the approved UI-03 prototype (`src/prototype/components/
 * Masthead.tsx`).
 */

import type { ReactNode } from 'react'

import { cn } from '../lib/cn'
import { Overline } from './Overline'

export interface MastheadProps {
  overline: string
  statement: ReactNode
  lede?: ReactNode
  readout?: ReactNode
  className?: string
}

export function Masthead({
  overline,
  statement,
  lede,
  readout,
  className,
}: MastheadProps) {
  return (
    <header className={cn('pt-14 sm:pt-20', className)}>
      <Overline as="p" tone="accent">
        {overline}
      </Overline>
      <h1 className="mt-4 max-w-[34rem] text-balance text-display tracking-edge text-primary sm:text-edge">
        {statement}
      </h1>
      {lede && (
        <p className="mt-4 max-w-[38rem] text-body text-secondary">{lede}</p>
      )}
      {readout && <div className="mt-7">{readout}</div>}
    </header>
  )
}
