/**
 * §1 Hero — the strongest authored moment, complete without animation.
 * Copy is fixed by the landing plan §5. The focal object is a real Tenora bill
 * (SampleBill) with its receipt tucked behind; the ledger line starts at the
 * bill and runs down into the rest of the page.
 */

import receiptIcon from '@iconify-icons/solar/document-text-linear'

import { Overline, Readout } from '../../components'
import { money } from '../../lib/property/format'
import { SampleBill } from '../product/SampleBill'
import { PARTIAL_PAYMENT_CENTS, SAMPLE_CURRENCY, SAMPLE_RECEIPT, SAMPLE_TOTAL_CENTS } from '../sample-data'
import { CtaLink, Frame, LandingIcon } from '../ui'

export function Hero() {
  return (
    <section data-hero aria-labelledby="hero-heading" className="relative overflow-hidden">
      <Frame className="grid grid-cols-1 items-center gap-12 pb-20 pt-12 md:pt-16 lg:grid-cols-12 lg:gap-10 lg:pb-28 lg:pt-20">
        <div className="lg:col-span-6">
          <Overline tone="accent" as="p" className="font-mono">
            Tenora · Property management
          </Overline>
          <h1
            id="hero-heading"
            data-hero-heading
            className="mt-6 text-hero tracking-[var(--tracking-hero)] text-primary text-balance"
          >
            Property management, without the paperwork.
          </h1>
          <div data-hero-support>
            <p className="mt-6 max-w-[34rem] text-lg leading-8 text-secondary">
              Manage properties, residents, rent, electricity, bills, payments and receipts from one workspace.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <CtaLink to="/register" size="lg">
                Get started
              </CtaLink>
              <CtaLink to="/login" variant="secondary" size="lg">
                Sign in
              </CtaLink>
            </div>
            <Readout
              className="mt-10 max-w-[34rem] text-label"
              items={[
                { value: 'Sample · March 2026', tone: 'success' },
                { value: `${money(SAMPLE_TOTAL_CENTS, SAMPLE_CURRENCY)} billed` },
                { value: `${money(PARTIAL_PAYMENT_CENTS, SAMPLE_CURRENCY)} received` },
              ]}
            />
          </div>
        </div>

        <div className="relative lg:col-span-6 lg:pl-6">
          {/* Receipt tucked behind the bill: the payment story begins here. */}
          <div
            data-hero-receipt
            data-parallax="0.5"
            aria-hidden="true"
            className="absolute -bottom-10 right-0 z-10 hidden w-56 rotate-2 rounded-lg border border-subtle bg-overlay p-4 shadow-overlay sm:block"
          >
            <p className="flex items-center gap-2 font-mono text-caption text-secondary">
              <LandingIcon icon={receiptIcon} className="size-4" />
              {SAMPLE_RECEIPT.receipt_number}
            </p>
            <p className="mt-3 font-mono text-h2 tabular-nums text-primary">
              {money(SAMPLE_RECEIPT.amount_cents, SAMPLE_RECEIPT.currency)}
            </p>
            <p className="mt-1 text-caption text-secondary">UPI · 05 Apr 2026</p>
          </div>

          <div data-parallax="1" className="relative">
            <SampleBill className="relative sm:mb-12 sm:mr-16 lg:mr-24" />
          </div>

          <span
            data-hero-ledger
            aria-hidden="true"
            className="ledger-line absolute -bottom-28 left-[1.75rem] hidden h-24 w-px lg:block"
          />
        </div>
      </Frame>
    </section>
  )
}
