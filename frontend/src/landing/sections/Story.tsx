/**
 * §2 Month-end, before · §3 The Tenora line · §4 Your portfolio, structured.
 */

import checkIcon from '@iconify-icons/solar/check-circle-linear'
import userCheck from '@iconify-icons/solar/user-check-rounded-linear'

import { Badge } from '../../components'
import { money } from '../../lib/property/format'
import { scrollRailTo } from '../motion/useLandingMotion'
import { SAMPLE_CURRENCY, SAMPLE_UNITS, WORKFLOW } from '../sample-data'
import { Frame, LandingIcon, SampleTag, SectionHeading } from '../ui'

const HABITS = [
  { before: 'Meter readings in a notebook.', after: 'Readings saved with a photo of the meter.' },
  { before: 'Rent tracked across chats.', after: 'Every bill issued from the lease it belongs to.' },
  { before: 'Receipts written by hand.', after: 'A numbered receipt for every payment recorded.' },
  { before: 'Late payments noticed late.', after: 'Overdue balances grouped by how late they are.' },
]

export function Problem() {
  return (
    <section aria-labelledby="problem-heading" className="border-t border-subtle py-24 lg:py-32">
      <Frame>
        <SectionHeading
          id="problem-heading"
          index="01"
          overline="Month-end, before"
          title="The month closes in five different places."
          lede="Most property owners keep the numbers in notebooks, spreadsheets and message threads — and reconcile them by hand. Tenora keeps one record, from the reading to the receipt."
        />
        <ul className="mt-14 flex flex-col">
          {HABITS.map((habit) => (
            <li
              key={habit.before}
              data-strike-row
              className="grid grid-cols-1 gap-3 border-t border-subtle py-6 md:grid-cols-2 md:items-center md:gap-10"
            >
              <p className="relative w-fit text-h1 text-secondary md:text-[1.75rem] md:leading-9">
                {habit.before}
                <span
                  data-strike
                  aria-hidden="true"
                  className="ledger-line absolute left-0 top-1/2 h-px w-full"
                />
              </p>
              <p data-answer className="flex items-center gap-3 text-body text-primary md:text-lg">
                <LandingIcon icon={checkIcon} className="text-accent-500" />
                {habit.after}
              </p>
            </li>
          ))}
        </ul>
      </Frame>
    </section>
  )
}

export function WorkflowRail() {
  return (
    <section
      id="workflow"
      aria-labelledby="workflow-heading"
      className="landing-anchor border-t border-subtle py-24 lg:py-0"
    >
      {/* Static by default: a wrapped grid, complete without motion. The motion
          hook sets data-pinned on desktop, which switches the track to a single
          horizontal row that the pinned ScrollTrigger scrubs through. */}
      <div
        data-rail
        className="group lg:py-24 lg:data-[pinned]:flex lg:data-[pinned]:min-h-screen lg:data-[pinned]:flex-col lg:data-[pinned]:justify-center lg:data-[pinned]:overflow-hidden"
      >
        <Frame>
          <SectionHeading
            id="workflow-heading"
            index="02"
            overline="The Tenora line"
            title="One chain of records, from workspace to receipt."
            lede="Each record is created from the one before it, so every number on a bill can be traced back to where it started."
          />
        </Frame>

        <div className="relative mt-14">
          <span aria-hidden="true" className="ledger-rule absolute left-0 right-0 top-[1.625rem] hidden border-t lg:group-data-[pinned]:block" />
          <span
            data-rail-progress
            aria-hidden="true"
            className="ledger-line absolute left-0 right-0 top-[1.625rem] hidden h-px lg:group-data-[pinned]:block"
          />
          <Frame>
            <ol
              data-rail-track
              aria-label="Tenora workflow"
              className="relative flex flex-col gap-0 border-l border-subtle pl-6 lg:grid lg:grid-cols-5 lg:gap-x-6 lg:gap-y-4 lg:border-l-0 lg:pl-0 lg:group-data-[pinned]:flex lg:group-data-[pinned]:w-max lg:group-data-[pinned]:flex-row"
            >
              {WORKFLOW.map((stop, i) => (
                <li key={stop.key} className="relative py-4 lg:py-0 lg:group-data-[pinned]:w-60">
                  <span
                    aria-hidden="true"
                    className="absolute -left-[1.8rem] top-6 size-2 bg-accent-600 lg:static lg:mb-5 lg:mt-5 lg:block"
                  />
                  <div
                    tabIndex={0}
                    onFocus={() => scrollRailTo(i, WORKFLOW.length)}
                    className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent-600"
                  >
                    <p className="font-mono text-caption text-secondary">{String(i + 1).padStart(2, '0')}</p>
                    <p className="mt-1 text-h2 text-primary">{stop.label}</p>
                    <p className="mt-3 w-fit rounded-sm border border-subtle bg-raised px-2.5 py-1.5 font-mono text-caption text-primary">
                      {stop.detail}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </Frame>
        </div>
      </div>
    </section>
  )
}

export function Portfolio() {
  return (
    <section aria-labelledby="portfolio-heading" className="border-t border-subtle py-24 lg:py-32">
      <Frame className="grid grid-cols-1 gap-14 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-5">
          <SectionHeading
            id="portfolio-heading"
            index="03"
            overline="Properties · Units · Residents"
            title="Your portfolio, structured the way you own it."
            lede="Add a property, its units and the residents who live there. Every lease records the rent and the dates it applies to."
          />
          <div data-reveal className="mt-10 rounded-lg border border-subtle bg-raised p-5">
            <p className="flex items-center gap-2 text-label text-primary">
              <LandingIcon icon={userCheck} className="text-accent-500" />
              No one is added silently
            </p>
            <p className="mt-2 text-body text-secondary">
              Residents are invited and choose to accept or decline. Only an accepted invitation joins them to your workspace.
            </p>
            <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-subtle bg-base px-3 py-2.5">
              <span className="min-w-0 truncate text-label text-primary">Invitation · Unit 203</span>
              <span className="flex shrink-0 gap-2" aria-hidden="true">
                <span className="rounded-md bg-accent-600 px-2.5 py-1 text-caption text-[var(--color-on-accent)]">Accept</span>
                <span className="rounded-md border border-subtle px-2.5 py-1 text-caption text-secondary">Decline</span>
              </span>
            </div>
          </div>
        </div>

        <figure data-reveal className="lg:col-span-7 lg:pt-24" aria-label="Sample units in Sunrise Apartments">
          <div className="overflow-hidden rounded-lg border border-subtle bg-raised">
            <div className="flex items-center justify-between border-b border-subtle px-5 py-4">
              <div>
                <p className="text-h2 text-primary">Sunrise Apartments</p>
                <p className="text-caption text-secondary">Building A · 4 units · 3 occupied</p>
              </div>
              <SampleTag />
            </div>
            <table className="w-full text-left">
              <caption className="sr-only">Units, residents and rent</caption>
              <thead>
                <tr className="border-b border-subtle text-caption text-secondary">
                  <th scope="col" className="px-5 py-2.5 font-medium">Unit</th>
                  <th scope="col" className="px-5 py-2.5 font-medium">Resident</th>
                  <th scope="col" className="hidden px-5 py-2.5 font-medium sm:table-cell">Status</th>
                  <th scope="col" className="px-5 py-2.5 text-right font-medium">Rent</th>
                </tr>
              </thead>
              <tbody>
                {SAMPLE_UNITS.map((unit) => (
                  <tr key={unit.identifier} className="border-b border-subtle last:border-0">
                    <td className="px-5 py-3.5 font-mono text-body text-primary">{unit.identifier}</td>
                    <td className="px-5 py-3.5 text-body text-primary">{unit.resident}</td>
                    <td className="hidden px-5 py-3.5 sm:table-cell">
                      <Badge variant={unit.status === 'Occupied' ? 'success' : 'neutral'}>{unit.status}</Badge>
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono text-body tabular-nums text-primary">
                      {unit.rent_cents ? money(unit.rent_cents, SAMPLE_CURRENCY) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </figure>
      </Frame>
    </section>
  )
}
