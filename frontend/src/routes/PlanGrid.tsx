/**
 * Plan cards (§C.4 Page 4). 3-across desktop → 2 tablet → 1 mobile.
 *
 * Two modes, and the distinction is deliberate:
 *
 *   - **Selectable** (`onSelect` given — OWNER, subscription not CANCELED):
 *     a real `role="radiogroup"` of `role="radio"` cards, per §C.4's
 *     accessibility note that plan cards are radio semantics rather than a set
 *     of unrelated buttons. There is no RadioGroup primitive in `components/`
 *     (it was on C1's deferred list) and the only ARIA-radio code in the repo is
 *     `TenantSwitcher`'s `menuitemradio`, which is a menu pattern — so the
 *     roving tabindex is implemented here.
 *
 *   - **Read-only** (`onSelect` omitted — MEMBER, or a CANCELED subscription):
 *     a plain `<ul>`. Rendering disabled radios would claim a choice exists
 *     when it does not; a list that marks the current plan is the honest
 *     shape, and it keeps the cards readable rather than focus-skipped.
 *
 * Arrow keys move focus but do NOT select. Strict WAI-ARIA radio behaviour
 * selects on arrow, which here would fire a real plan change (or open a
 * confirmation) on every keystroke while merely browsing the options. The
 * group's checked value is the tenant's actual subscribed plan, not a transient
 * cursor, so activation is explicit: Enter or Space.
 */

import { useRef, useState, type KeyboardEvent } from 'react'

import { Badge } from '../components'
import { cn } from '../lib/cn'
import { formatMoney } from '../lib/format'
import type { Plan } from './SubscriptionPage'

const INTERVAL_LABEL: Record<Plan['interval'], string> = {
  MONTHLY: 'per month',
  ANNUAL: 'per year',
}

const CARD_BASE =
  'block w-full rounded-lg border bg-raised p-4 text-left transition-colors'
const CARD_SELECTED = 'border-accent-600 bg-accent-subtle'
const CARD_PLAIN = 'border-subtle'
const CARD_FOCUS =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600'

const GRID = 'grid gap-4 sm:grid-cols-2 lg:grid-cols-3'

interface PlanGridProps {
  plans: Plan[]
  /** Id of the plan the tenant is actually subscribed to, if any. */
  currentPlanId?: string
  /** Omit to render read-only (MEMBER, or a terminal subscription). */
  onSelect?: (plan: Plan) => void
  /** True while a create/change request is in flight. */
  busy?: boolean
}

function PlanCardBody({
  plan,
  isCurrent,
}: {
  plan: Plan
  isCurrent: boolean
}) {
  return (
    <>
      <span className="flex items-center justify-between gap-2">
        <span className="text-label text-primary">{plan.name}</span>
        {isCurrent && <Badge variant="accent">Current</Badge>}
      </span>
      <span className="mt-2 block font-mono text-caption text-secondary">
        {plan.code}
      </span>
      <span className="mt-3 block text-h2 text-primary num">
        {formatMoney(plan.price_cents, plan.currency)}
      </span>
      <span className="mt-1 block text-caption text-secondary">
        {INTERVAL_LABEL[plan.interval] ?? plan.interval}
      </span>
    </>
  )
}

export function PlanGrid({
  plans,
  currentPlanId,
  onSelect,
  busy = false,
}: PlanGridProps) {
  const cardRefs = useRef<Array<HTMLButtonElement | null>>([])
  // Roving tabindex: the checked card is the tab stop, falling back to the
  // first card when nothing is subscribed yet.
  const initialFocus = Math.max(
    0,
    plans.findIndex((p) => p.id === currentPlanId),
  )
  const [focusIndex, setFocusIndex] = useState(initialFocus)

  if (!onSelect) {
    return (
      <ul aria-label="Available plans" className={GRID}>
        {plans.map((plan) => {
          const isCurrent = plan.id === currentPlanId
          return (
            <li
              key={plan.id}
              className={cn(CARD_BASE, isCurrent ? CARD_SELECTED : CARD_PLAIN)}
            >
              <PlanCardBody plan={plan} isCurrent={isCurrent} />
            </li>
          )
        })}
      </ul>
    )
  }

  function moveFocus(next: number) {
    const clamped = (next + plans.length) % plans.length
    setFocusIndex(clamped)
    cardRefs.current[clamped]?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault()
        moveFocus(focusIndex + 1)
        break
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault()
        moveFocus(focusIndex - 1)
        break
      case 'Home':
        event.preventDefault()
        moveFocus(0)
        break
      case 'End':
        event.preventDefault()
        moveFocus(plans.length - 1)
        break
      default:
        break
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label="Available plans"
      className={GRID}
      onKeyDown={onKeyDown}
    >
      {plans.map((plan, i) => {
        const isCurrent = plan.id === currentPlanId
        return (
          <button
            key={plan.id}
            ref={(el) => {
              cardRefs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={isCurrent}
            tabIndex={i === focusIndex ? 0 : -1}
            disabled={busy}
            onClick={() => onSelect(plan)}
            onFocus={() => setFocusIndex(i)}
            className={cn(
              CARD_BASE,
              CARD_FOCUS,
              isCurrent ? CARD_SELECTED : CARD_PLAIN,
              !isCurrent && !busy && 'hover:bg-overlay',
              busy && 'opacity-60',
            )}
          >
            <PlanCardBody plan={plan} isCurrent={isCurrent} />
          </button>
        )
      })}
    </div>
  )
}
