/**
 * §5 The billing engine · §6 Payments and receipts · §7 Aging and reporting.
 */

import boltIcon from '@iconify-icons/solar/bolt-linear'
import downloadIcon from '@iconify-icons/solar/download-minimalistic-linear'
import historyIcon from '@iconify-icons/solar/history-linear'
import rulerIcon from '@iconify-icons/solar/ruler-linear'

import { Badge } from '../../components'
import { formatDecimal, money } from '../../lib/property/format'
import { BillStatusBadge } from '../../routes/property/ui'
import {
  CLOSING_READING,
  ELECTRICITY_CENTS,
  MULTIPLIER,
  OPENING_READING,
  PARTIAL_PAYMENT_CENTS,
  RATE_PER_UNIT_CENTS,
  SAMPLE_AGING,
  SAMPLE_BILL,
  SAMPLE_CURRENCY,
  SAMPLE_RECEIPT,
  SAMPLE_TOTAL_CENTS,
  UNITS,
} from '../sample-data'
import { Frame, LandingIcon, SampleTag, SectionHeading } from '../ui'

const readings = (n: number) => n.toLocaleString('en-IN')

const ENGINE_STEPS = [
  {
    key: 'reading',
    label: 'Reading',
    value: `${readings(OPENING_READING)} → ${readings(CLOSING_READING)}`,
    note: 'Opening and closing readings, each with a photo of the meter.',
  },
  {
    key: 'consumption',
    label: 'Consumption',
    value: `${UNITS} units`,
    note: `Closing minus opening, × multiplier ${MULTIPLIER}.`,
  },
  {
    key: 'rate',
    label: 'Rate',
    value: `${money(RATE_PER_UNIT_CENTS, SAMPLE_CURRENCY)} / unit`,
    note: 'The tariff in effect for the billing period.',
  },
  {
    key: 'line',
    label: 'Bill line',
    value: money(ELECTRICITY_CENTS, SAMPLE_CURRENCY),
    note: 'Saved on the bill with the readings and rate it used.',
  },
  {
    key: 'bill',
    label: 'Bill',
    value: money(SAMPLE_TOTAL_CENTS, SAMPLE_CURRENCY),
    note: 'Rent, electricity and maintenance — published to the resident.',
  },
]

export function BillingEngine() {
  return (
    <section
      id="billing"
      aria-labelledby="billing-heading"
      className="landing-anchor border-t border-subtle py-24 lg:py-0"
    >
      <div data-engine className="lg:flex lg:min-h-screen lg:flex-col lg:justify-center lg:py-20">
        <Frame>
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
            <SectionHeading
              className="lg:col-span-7"
              id="billing-heading"
              index="04"
              overline="The billing engine"
              title="Every amount on a bill explains itself."
              lede="Tenora calculates electricity from the readings you record and the tariff in effect, then keeps that calculation on the bill."
            />
            <ul className="flex flex-col gap-4 self-end text-body text-secondary lg:col-span-5">
              <li className="flex gap-3">
                <LandingIcon icon={rulerIcon} className="mt-0.5 text-accent-500" />
                Tariffs change with an effective date; each bill uses the rate for its own month.
              </li>
              <li className="flex gap-3">
                <LandingIcon icon={historyIcon} className="mt-0.5 text-accent-500" />
                Raising April’s rent never changes March’s bill. Issued bills are history.
              </li>
              <li className="flex gap-3">
                <LandingIcon icon={boltIcon} className="mt-0.5 text-accent-500" />
                Mistakes are corrected with a recorded adjustment and a reason — never by overwriting.
              </li>
            </ul>
          </div>

          <ol aria-label="How an electricity charge is calculated" className="mt-14 grid grid-cols-1 gap-3 md:grid-cols-5 md:gap-0">
            {ENGINE_STEPS.map((step, i) => (
              <li
                key={step.key}
                data-engine-step
                className="relative border-subtle bg-raised p-5 max-md:rounded-lg max-md:border md:border-y md:border-r md:first:rounded-l-lg md:first:border-l md:last:rounded-r-lg"
              >
                {i > 0 && (
                  <span
                    data-engine-link
                    aria-hidden="true"
                    className="ledger-line absolute -left-px top-0 hidden h-0.5 w-full md:block"
                  />
                )}
                <p className="font-mono text-caption text-secondary">
                  {String(i + 1).padStart(2, '0')} · {step.label}
                </p>
                <p className="mt-4 font-mono text-h1 tabular-nums text-primary">{step.value}</p>
                <p className="mt-3 text-caption text-secondary">{step.note}</p>
              </li>
            ))}
          </ol>
          <p className="mt-4">
            <SampleTag />
          </p>
        </Frame>
      </div>
    </section>
  )
}

export function PaymentsReceipts() {
  const due = SAMPLE_TOTAL_CENTS - PARTIAL_PAYMENT_CENTS
  return (
    <section aria-labelledby="payments-heading" className="border-t border-subtle py-24 lg:py-32">
      <Frame>
        <SectionHeading
          id="payments-heading"
          index="05"
          overline="Payments and receipts"
          title="Record the payment. The receipt writes itself."
          lede="Log cash, bank transfers, UPI or card payments against a bill — in full or in part. Each payment issues a numbered receipt your resident can download as a PDF."
        />

        <ol aria-label="From bill to receipt" className="mt-14 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <li data-reveal className="rounded-lg border border-subtle bg-raised p-6">
            <p className="font-mono text-caption text-secondary">Bill · {SAMPLE_BILL.bill_number}</p>
            <p className="mt-4 font-mono text-h1 tabular-nums text-primary">{money(SAMPLE_TOTAL_CENTS, SAMPLE_CURRENCY)}</p>
            <div className="mt-4">
              <BillStatusBadge status="PUBLISHED" />
            </div>
          </li>
          <li data-reveal className="rounded-lg border border-subtle bg-raised p-6">
            <p className="font-mono text-caption text-secondary">Payment · UPI · 05 Apr 2026</p>
            <p className="mt-4 font-mono text-h1 tabular-nums text-primary">{money(PARTIAL_PAYMENT_CENTS, SAMPLE_CURRENCY)}</p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <BillStatusBadge status="PARTIALLY_PAID" />
              <span className="font-mono text-caption text-secondary">{money(due, SAMPLE_CURRENCY)} still due</span>
            </div>
          </li>
          <li data-reveal className="rounded-lg border border-accent-600 bg-raised p-6">
            <p className="font-mono text-caption text-secondary">Receipt · {SAMPLE_RECEIPT.receipt_number}</p>
            <p className="mt-4 font-mono text-h1 tabular-nums text-primary">
              {money(SAMPLE_RECEIPT.amount_cents, SAMPLE_RECEIPT.currency)}
            </p>
            <p className="mt-4 flex items-center gap-2 text-label text-accent-500">
              <LandingIcon icon={downloadIcon} className="size-4" />
              Download PDF
            </p>
          </li>
        </ol>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-[40rem] text-body text-secondary">
            A payment is refused if it would take a bill above what’s due, and a repeated submission never records the same payment twice.
          </p>
          <SampleTag />
        </div>
      </Frame>
    </section>
  )
}

export function AgingReporting() {
  const max = Math.max(...SAMPLE_AGING.map((b) => b.amount_cents))
  const outstanding = SAMPLE_AGING.reduce((sum, b) => sum + b.amount_cents, 0)
  const overdue = SAMPLE_AGING.filter((b) => b.key !== 'CURRENT').reduce((sum, b) => sum + b.amount_cents, 0)
  return (
    <section aria-labelledby="aging-heading" className="border-t border-subtle py-24 lg:py-32">
      <Frame className="grid grid-cols-1 gap-14 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-5">
          <SectionHeading
            id="aging-heading"
            index="06"
            overline="Aging and reporting"
            title="Know what’s late without building a spreadsheet."
            lede="Overdue is worked out from each bill’s due date, every day. Reports show what you billed, what you collected and what is still outstanding — per workspace, or across all of them."
          />
          <dl className="mt-10 grid grid-cols-2 gap-3" data-reveal>
            <div className="rounded-md border border-subtle bg-raised p-4">
              <dt className="text-caption text-secondary">Outstanding</dt>
              <dd className="mt-1 font-mono text-xl tabular-nums text-primary">{money(outstanding, SAMPLE_CURRENCY)}</dd>
            </div>
            <div className="rounded-md border border-subtle bg-raised p-4">
              <dt className="text-caption text-secondary">Overdue</dt>
              <dd className="mt-1 font-mono text-xl tabular-nums text-danger">{money(overdue, SAMPLE_CURRENCY)}</dd>
            </div>
          </dl>
        </div>

        <figure className="lg:col-span-7 lg:pt-24" aria-label="Sample aging report">
          <ul className="flex flex-col" aria-label="Aging buckets">
            {SAMPLE_AGING.map((bucket) => (
              <li
                key={bucket.key}
                className="grid grid-cols-[6.5rem_1fr] items-center gap-x-4 gap-y-2 border-t border-subtle py-4 sm:grid-cols-[7.5rem_1fr_11rem]"
              >
                <span className="text-label text-primary">{bucket.label}</span>
                <span className="h-2.5 overflow-hidden rounded-full bg-overlay" aria-hidden="true">
                  <span
                    data-bar
                    className={bucket.key === 'CURRENT' ? 'block h-full bg-accent-600' : 'block h-full bg-danger'}
                    style={{ width: `${max ? Math.round((bucket.amount_cents / max) * 100) : 0}%` }}
                  />
                </span>
                <span className="col-start-2 font-mono text-label tabular-nums text-primary sm:col-start-auto sm:text-right">
                  {money(bucket.amount_cents, SAMPLE_CURRENCY)} · {bucket.count} {bucket.count === 1 ? 'bill' : 'bills'}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-6 grid grid-cols-1 gap-3 border-t border-subtle pt-6 sm:grid-cols-3">
            {[
              ['Rent collected', 1_200_000],
              ['Electricity collected', 128_000],
              ['On partly paid bills', PARTIAL_PAYMENT_CENTS],
            ].map(([label, cents]) => (
              <div key={label as string}>
                <p className="text-caption text-secondary">{label}</p>
                <p className="mt-1 font-mono text-body tabular-nums text-primary">{money(cents as number, SAMPLE_CURRENCY)}</p>
              </div>
            ))}
          </div>
          <figcaption className="mt-5 flex items-center gap-3">
            <Badge variant="neutral">{formatDecimal(String(UNITS))} units this month</Badge>
            <SampleTag />
          </figcaption>
        </figure>
      </Frame>
    </section>
  )
}
