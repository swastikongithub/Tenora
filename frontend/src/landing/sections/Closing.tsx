/**
 * §8 Two sides of every bill · §9 Built to be trusted · §10 Pricing ·
 * §11 Final CTA · §12 Footer.
 *
 * Claims here are limited to shipped behaviour (P1–P8, P10). Online resident
 * payments (P9) are not shipped and are not mentioned. No certifications,
 * customers, metrics or partners.
 */

import bellIcon from '@iconify-icons/solar/bell-linear'
import billIcon from '@iconify-icons/solar/bill-list-linear'
import buildingsIcon from '@iconify-icons/solar/buildings-2-linear'
import chartIcon from '@iconify-icons/solar/chart-2-linear'
import clipboardIcon from '@iconify-icons/solar/clipboard-list-linear'
import documentIcon from '@iconify-icons/solar/document-text-linear'
import homeIcon from '@iconify-icons/solar/home-2-linear'
import keyIcon from '@iconify-icons/solar/key-minimalistic-linear'
import lockIcon from '@iconify-icons/solar/lock-keyhole-linear'
import shieldIcon from '@iconify-icons/solar/shield-check-linear'
import usersIcon from '@iconify-icons/solar/users-group-rounded-linear'
import walletIcon from '@iconify-icons/solar/wallet-money-linear'
import { useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'

import { Wordmark } from '../../components/layout/Wordmark'
import { cn } from '../../lib/cn'
import { money } from '../../lib/property/format'
import { PARTIAL_PAYMENT_CENTS, PLAN_LIMITS, SAMPLE_CURRENCY, SAMPLE_TOTAL_CENTS } from '../sample-data'
import { CtaLink, Frame, LandingIcon, SampleTag, SectionHeading } from '../ui'

const SIDES = [
  {
    key: 'owner',
    label: 'Owner',
    title: 'Run every workspace from one place.',
    body: 'Open a billing cycle, see which readings are still missing, generate and review drafts, then publish. Record payments as they arrive and follow up on what’s overdue.',
    items: [
      { icon: buildingsIcon, text: 'Properties, units, residents and leases' },
      { icon: clipboardIcon, text: 'Monthly billing cycles with draft review' },
      { icon: walletIcon, text: 'Payments, receipts and PDF bills' },
      { icon: chartIcon, text: 'Aging, reports and an all-workspaces view' },
    ],
    tiles: [
      ['Billed in March', money(SAMPLE_TOTAL_CENTS, SAMPLE_CURRENCY)],
      ['Collected', money(PARTIAL_PAYMENT_CENTS, SAMPLE_CURRENCY)],
      ['Readings entered', '4 of 4'],
    ],
  },
  {
    key: 'resident',
    label: 'Resident',
    title: 'Residents see their own bills — and nothing else.',
    body: 'Residents accept an invitation, then see their current bill, how it was calculated, their billing history and every receipt. Notifications tell them when a bill is published or a payment is recorded.',
    items: [
      { icon: homeIcon, text: 'A dashboard with their unit and current bill' },
      { icon: billIcon, text: 'My Bills and full billing history' },
      { icon: documentIcon, text: 'Receipts, downloadable as PDF' },
      { icon: bellIcon, text: 'Notifications for bills and payments' },
    ],
    tiles: [
      ['Outstanding', money(SAMPLE_TOTAL_CENTS - PARTIAL_PAYMENT_CENTS, SAMPLE_CURRENCY)],
      ['Monthly rent', money(1_200_000, SAMPLE_CURRENCY)],
      ['Receipts', '1'],
    ],
  },
] as const

export function TwoSides() {
  const [selected, setSelected] = useState(0)
  const tabs = useRef<Array<HTMLButtonElement | null>>([])
  const side = SIDES[selected]

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, number> = {
      ArrowRight: (selected + 1) % SIDES.length,
      ArrowLeft: (selected - 1 + SIDES.length) % SIDES.length,
      Home: 0,
      End: SIDES.length - 1,
    }
    if (!(event.key in keys)) return
    event.preventDefault()
    const next = keys[event.key]
    setSelected(next)
    tabs.current[next]?.focus()
  }

  return (
    <section id="residents" aria-labelledby="sides-heading" className="landing-anchor border-t border-subtle py-24 lg:py-32">
      <Frame>
        <SectionHeading
          id="sides-heading"
          index="07"
          overline="Owner and resident"
          title="Two sides of every bill."
          lede="Owners manage the workspace. Residents get a calm view of what they owe and what they’ve paid."
        />

        <div
          role="tablist"
          aria-label="Choose a view"
          onKeyDown={onKeyDown}
          className="mt-12 inline-flex rounded-md border border-subtle bg-raised p-1"
        >
          {SIDES.map((s, i) => (
            <button
              key={s.key}
              ref={(el) => {
                tabs.current[i] = el
              }}
              id={`side-tab-${s.key}`}
              type="button"
              role="tab"
              aria-selected={i === selected}
              aria-controls={`side-panel-${s.key}`}
              tabIndex={i === selected ? 0 : -1}
              onClick={() => setSelected(i)}
              className={cn(
                'h-10 min-w-28 rounded-sm px-4 text-label transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
                i === selected ? 'bg-accent-600 text-[var(--color-on-accent)]' : 'text-secondary hover:text-primary',
              )}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div
          key={side.key}
          id={`side-panel-${side.key}`}
          role="tabpanel"
          aria-labelledby={`side-tab-${side.key}`}
          tabIndex={0}
          className="landing-fade mt-8 grid grid-cols-1 gap-10 rounded-lg border border-subtle bg-raised p-6 focus-visible:outline-2 focus-visible:outline-accent-600 sm:p-8 lg:grid-cols-12"
        >
          <div className="lg:col-span-6">
            <h3 className="text-h1 text-primary">{side.title}</h3>
            <p className="mt-3 text-body text-secondary">{side.body}</p>
            <ul className="mt-6 flex flex-col gap-3">
              {side.items.map((item) => (
                <li key={item.text} className="flex items-center gap-3 text-body text-primary">
                  <LandingIcon icon={item.icon} className="text-accent-500" />
                  {item.text}
                </li>
              ))}
            </ul>
          </div>
          <div className="lg:col-span-6">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {side.tiles.map(([label, value]) => (
                <div key={label} className="rounded-md border border-subtle bg-base p-4">
                  <p className="text-caption text-secondary">{label}</p>
                  <p className="mt-1 font-mono text-lg tabular-nums text-primary">{value}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-end">
              <SampleTag />
            </div>
          </div>
        </div>
      </Frame>
    </section>
  )
}

const TRUST = [
  {
    icon: lockIcon,
    title: 'Workspaces are isolated',
    detail: 'A record from another workspace simply isn’t found.',
  },
  {
    icon: usersIcon,
    title: 'Residents see only their own bills',
    detail: 'What a resident sees is decided on the server, from who is signed in.',
  },
  {
    icon: documentIcon,
    title: 'Issued bills are history',
    detail: 'Corrections add a recorded adjustment with a reason; the original stays.',
  },
  {
    icon: keyIcon,
    title: 'Payments are recorded once',
    detail: 'A retried or double-clicked submission can’t record the same payment twice.',
  },
  {
    icon: shieldIcon,
    title: 'Money actions are audited',
    detail: 'Publishing, payments, receipts and corrections each leave an audit record.',
  },
]

export function Trust() {
  return (
    <section aria-labelledby="trust-heading" className="border-t border-subtle py-24 lg:py-32">
      <Frame className="grid grid-cols-1 gap-14 lg:grid-cols-12 lg:gap-10">
        <SectionHeading
          className="lg:col-span-5"
          id="trust-heading"
          index="08"
          overline="Built to be trusted"
          title="Correct by construction, not by promise."
          lede="These aren’t settings you have to remember. They’re how Tenora stores and checks every record."
        />
        <ul className="lg:col-span-7">
          {TRUST.map((item) => (
            <li key={item.title} data-reveal className="flex gap-4 border-t border-subtle py-5 last:border-b">
              <LandingIcon icon={item.icon} className="mt-0.5 text-accent-500" />
              <div>
                <p className="text-h2 text-primary">{item.title}</p>
                <p className="mt-1 text-body text-secondary">{item.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </Frame>
    </section>
  )
}

export function Pricing() {
  return (
    <section id="pricing" aria-labelledby="pricing-heading" className="landing-anchor border-t border-subtle py-24 lg:py-32">
      <Frame>
        <SectionHeading
          id="pricing-heading"
          index="09"
          overline="Pricing"
          title="Plans sized to your portfolio."
          lede="Your Tenora plan sets how many workspaces you can own and how many active members each one can have. Pricing is shown after you sign in."
        />
        <ul className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-2">
          {PLAN_LIMITS.map((plan) => (
            <li key={plan.name} data-reveal className="flex flex-col rounded-lg border border-subtle bg-raised p-6 sm:p-8">
              <h3 className="text-h1 text-primary">{plan.name}</h3>
              <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-subtle pt-6">
                <div>
                  <dt className="text-caption text-secondary">Workspaces</dt>
                  <dd className="mt-1 font-mono text-display tabular-nums text-primary">
                    <span className="sr-only">Up to </span>
                    {plan.workspaces}
                  </dd>
                </div>
                <div>
                  <dt className="text-caption text-secondary">Active members per workspace</dt>
                  <dd className="mt-1 font-mono text-display tabular-nums text-primary">
                    <span className="sr-only">Up to </span>
                    {plan.members}
                  </dd>
                </div>
              </dl>
              <p className="mt-4 text-caption text-secondary">
                Up to {plan.workspaces} workspaces and up to {plan.members} active members or residents in each.
              </p>
              <CtaLink to="/register" variant={plan.name === 'Pro' ? 'primary' : 'secondary'} className="mt-8 self-start">
                Get started with {plan.name}
              </CtaLink>
            </li>
          ))}
        </ul>
        <div className="mt-8 grid grid-cols-1 gap-4 rounded-lg border border-dashed border-strong p-6 md:grid-cols-2">
          <div>
            <p className="text-label text-primary">Your Tenora subscription</p>
            <p className="mt-1 text-body text-secondary">Between you, the workspace owner, and Tenora.</p>
          </div>
          <div>
            <p className="text-label text-primary">Your residents’ bills</p>
            <p className="mt-1 text-body text-secondary">
              Rent, electricity and charges your residents owe you. Kept completely separate from your subscription.
            </p>
          </div>
        </div>
      </Frame>
    </section>
  )
}

export function FinalCta() {
  return (
    <section aria-labelledby="final-heading" className="border-t border-subtle py-28 lg:py-40">
      <Frame className="flex flex-col items-start gap-10">
        <h2 id="final-heading" data-split-heading className="max-w-[18ch] text-hero tracking-[var(--tracking-hero)] text-primary text-balance">
          Close the month in one workspace.
        </h2>
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <CtaLink to="/register" size="lg">
            Get started
          </CtaLink>
          <CtaLink to="/login" variant="secondary" size="lg">
            Sign in
          </CtaLink>
        </div>
      </Frame>
    </section>
  )
}

const FOOTER_LINK =
  'rounded-sm text-secondary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600'

export function LandingFooter() {
  const year = new Date().getFullYear()
  return (
    <footer className="border-t border-subtle py-12">
      <Frame className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-[22rem] text-body text-secondary">
            Property management and billing for owners and their residents.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-10 text-label">
          <ul className="flex flex-col gap-3">
            <li><a className={FOOTER_LINK} href="#workflow">Workflow</a></li>
            <li><a className={FOOTER_LINK} href="#billing">Billing</a></li>
            <li><a className={FOOTER_LINK} href="#pricing">Pricing</a></li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li><Link className={FOOTER_LINK} to="/login">Sign in</Link></li>
            <li><Link className={FOOTER_LINK} to="/register">Create account</Link></li>
          </ul>
        </nav>
      </Frame>
      <Frame className="mt-10">
        <div className="flex flex-col gap-2 border-t border-subtle pt-6 text-caption text-secondary sm:flex-row sm:justify-between">
        <p>© {year} Tenora</p>
        <p>
          Icons:{' '}
          <a className={`underline ${FOOTER_LINK}`} href="https://www.figma.com/community/file/1166831539721848736" rel="noreferrer" target="_blank">
            Solar by 480 Design
          </a>
          , licensed{' '}
          <a className={`underline ${FOOTER_LINK}`} href="https://creativecommons.org/licenses/by/4.0/" rel="noreferrer" target="_blank">
            CC BY 4.0
          </a>
          .
        </p>
        </div>
      </Frame>
    </footer>
  )
}
