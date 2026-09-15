/**
 * The hero's focal object: a Tenora bill composed from the product's own
 * primitives (BillStatusBadge, the bill's line/total structure, Geist Mono
 * figures) over typed sample data. Nothing here fetches.
 *
 * Each line is a button. Focusing, hovering (fine pointers) or tapping it shows
 * where the amount comes from — the lease, the two meter readings and the
 * tariff. The electricity trace is shown by default, so the explanation is part
 * of the static first frame and never hover-only.
 */

import { useId, useState } from 'react'

import { cn } from '../../lib/cn'
import { formatPeriod, money } from '../../lib/property/format'
import { BillStatusBadge } from '../../routes/property/ui'
import { SAMPLE_BILL, SAMPLE_CURRENCY, SAMPLE_LINES } from '../sample-data'
import { SampleTag } from '../ui'

export function SampleBill({ className }: { className?: string }) {
  const [active, setActive] = useState('electricity')
  const baseId = useId()
  const current = SAMPLE_LINES.find((line) => line.id === active) ?? SAMPLE_LINES[1]

  return (
    <figure
      aria-label={`Sample Tenora bill ${SAMPLE_BILL.bill_number}`}
      className={cn('rounded-lg border border-subtle bg-raised shadow-overlay', className)}
    >
      <div className="flex items-start justify-between gap-4 border-b border-subtle px-5 py-4 sm:px-6">
        <div className="min-w-0">
          <p className="font-mono text-caption text-secondary">{SAMPLE_BILL.bill_number}</p>
          <p className="mt-1 text-h2 text-primary">{formatPeriod(SAMPLE_BILL.period_start)}</p>
          <p className="mt-0.5 truncate text-label text-secondary">
            {SAMPLE_BILL.property_name} · Unit {SAMPLE_BILL.unit_identifier} · {SAMPLE_BILL.resident_name}
          </p>
        </div>
        <BillStatusBadge status={SAMPLE_BILL.status} />
      </div>

      <ul className="px-2 py-2 sm:px-3" aria-label="Bill lines">
        {SAMPLE_LINES.map((line) => {
          const selected = line.id === active
          return (
            <li key={line.id} data-bill-line>
              <button
                type="button"
                aria-pressed={selected}
                aria-describedby={`${baseId}-${line.id}`}
                onFocus={() => setActive(line.id)}
                onMouseEnter={() => setActive(line.id)}
                onClick={() => setActive(line.id)}
                className={cn(
                  'flex w-full items-baseline justify-between gap-4 rounded-md px-3 py-3 text-left transition-colors',
                  'focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent-600',
                  selected ? 'bg-accent-subtle' : 'hover:bg-overlay',
                )}
              >
                <span className="flex items-center gap-2.5 text-body text-primary">
                  <span
                    aria-hidden="true"
                    className={cn('h-4 w-px', selected ? 'ledger-line' : 'bg-[var(--color-strong)]')}
                  />
                  {line.description}
                </span>
                <span className="font-mono text-body tabular-nums text-primary">
                  {money(line.amount_cents, SAMPLE_CURRENCY)}
                </span>
              </button>
              <span id={`${baseId}-${line.id}`} className="sr-only">
                {line.source.join('. ')}
              </span>
            </li>
          )
        })}
      </ul>

      <div className="mx-5 border-t border-dashed border-subtle py-3 sm:mx-6" aria-live="polite">
        <p className="text-caption text-secondary">Where {current.description.toLowerCase()} comes from</p>
        <ul className="mt-1.5 flex flex-col gap-1">
          {current.source.map((text) => (
            <li key={text} className="flex gap-2 font-mono text-caption text-primary">
              <span aria-hidden="true" className="text-accent-500">
                ↳
              </span>
              {text}
            </li>
          ))}
        </ul>
      </div>

      <div
        data-bill-total
        className="flex items-baseline justify-between gap-4 border-t border-subtle px-5 py-4 sm:px-6"
      >
        <span className="text-label text-secondary">Total due 10 Apr 2026</span>
        <span className="font-mono text-h1 tabular-nums text-primary">{money(SAMPLE_BILL.total_cents, SAMPLE_CURRENCY)}</span>
      </div>
      <figcaption className="border-t border-subtle px-5 py-2.5 sm:px-6">
        <SampleTag />
      </figcaption>
    </figure>
  )
}
