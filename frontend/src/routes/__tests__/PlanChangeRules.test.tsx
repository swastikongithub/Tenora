/**
 * What the Subscription page offers once a workspace already subscribes.
 *
 * The backend is the authority — these assert only that the page shows the
 * same answer instead of inviting a click it knows will be refused, and that a
 * refusal it did not predict is surfaced as the server worded it.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  currentSubscriptionHandler,
  PLAN_BASIC,
  PLAN_PRO_ANNUAL,
  PLAN_PRO_MONTHLY,
  plansHandler,
  subscriptionFor,
  TENANT_A,
  tenantsMeHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import { AppRoutes } from '../AppRoutes'
import { classifyPlanChange } from '../planChangeRules'

const ALL_PLANS = [PLAN_BASIC, PLAN_PRO_MONTHLY, PLAN_PRO_ANNUAL]

function renderSubscription() {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  setCurrentTenantId(TENANT_A.id)
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/subscription']}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

/**
 * The card for a plan, found by its code inside the plan group — the code also
 * appears in the current-subscription panel above, so the lookup is scoped.
 */
async function cardFor(code: string) {
  const group = await screen.findByRole('radiogroup', { name: 'Available plans' })
  const codeEl = await within(group).findByText(code)
  return codeEl.closest('[role="radio"]') as HTMLElement
}

/**
 * The plan grid renders as soon as the PLANS query resolves, which can be a
 * tick before the SUBSCRIPTION query it derives availability from — so wait
 * for the current plan to be marked before asserting on the other cards.
 */
async function cardsReady(currentCode: string) {
  const current = await cardFor(currentCode)
  await waitFor(() => expect(current).toHaveAttribute('aria-checked', 'true'))
}

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
})

describe('plan-change rules (mirror of the backend policy)', () => {
  it('classifies every production transition the way the backend does', () => {
    expect(classifyPlanChange('BASIC_MONTHLY', 'BASIC_MONTHLY').kind).toBe('current')
    expect(classifyPlanChange('BASIC_MONTHLY', 'PRO_MONTHLY').kind).toBe('upgrade')
    expect(classifyPlanChange('BASIC_MONTHLY', 'PRO_ANNUAL').kind).toBe('upgrade')
    expect(classifyPlanChange('PRO_MONTHLY', 'BASIC_MONTHLY').kind).toBe('blocked')
    expect(classifyPlanChange('PRO_ANNUAL', 'BASIC_MONTHLY').kind).toBe('blocked')
    expect(classifyPlanChange('PRO_MONTHLY', 'PRO_ANNUAL').kind).toBe('blocked')
    expect(classifyPlanChange('PRO_ANNUAL', 'PRO_MONTHLY').kind).toBe('blocked')
    // An unrecognised code is unavailable, never guessed into an upgrade.
    expect(classifyPlanChange('BASIC_MONTHLY', 'ENTERPRISE_X').kind).toBe('blocked')
  })
})

describe('SubscriptionPage — plan availability', () => {
  it('marks the current plan and offers no action on it', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO_MONTHLY, 'ACTIVE')),
      plansHandler(ALL_PLANS),
      http.post(apiUrl('/subscriptions/current/checkout/'), () => {
        throw new Error('the current plan must start no checkout')
      }),
    )
    renderSubscription()

    await cardsReady('PRO_MONTHLY')
    const current = await cardFor('PRO_MONTHLY')
    expect(within(current).getByText('Current')).toBeInTheDocument()

    await userEvent.click(current)
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })

  it('shows an upgrade as payment-required and lets it be chosen', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_BASIC, 'ACTIVE')),
      plansHandler(ALL_PLANS),
    )
    renderSubscription()

    await cardsReady('BASIC_MONTHLY')
    const upgrade = await cardFor('PRO_MONTHLY')
    expect(await within(upgrade).findByText(/Payment required/i)).toBeInTheDocument()
    expect(upgrade).toBeEnabled()

    await userEvent.click(upgrade)
    expect(
      await screen.findByRole('dialog', { name: 'Upgrade plan' }),
    ).toBeInTheDocument()
  })

  it('disables a downgrade and explains why', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO_MONTHLY, 'ACTIVE')),
      plansHandler(ALL_PLANS),
      http.post(apiUrl('/subscriptions/current/checkout/'), () => {
        throw new Error('a downgrade must start no checkout')
      }),
    )
    renderSubscription()

    await cardsReady('PRO_MONTHLY')
    const downgrade = await cardFor('BASIC_MONTHLY')
    await waitFor(() => expect(downgrade).toBeDisabled())
    expect(
      within(downgrade).getByText(/Downgrading isn’t supported/i),
    ).toBeInTheDocument()

    await userEvent.click(downgrade)
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })

  it('disables switching billing cycle in both directions', async () => {
    for (const [current, blockedCode] of [
      [PLAN_PRO_MONTHLY, 'PRO_ANNUAL'],
      [PLAN_PRO_ANNUAL, 'PRO_MONTHLY'],
    ] as const) {
      server.use(
        ...authHandlers(),
        tenantsMeHandler([TENANT_A]),
        currentSubscriptionHandler(subscriptionFor(current, 'ACTIVE')),
        plansHandler(ALL_PLANS),
        http.post(apiUrl('/subscriptions/current/checkout/'), () => {
          throw new Error('a billing-cycle change must start no checkout')
        }),
      )
      const view = renderSubscription()

      await cardsReady(current.code)
      const blocked = await cardFor(blockedCode)
      await waitFor(() => expect(blocked).toBeDisabled())
      expect(
        within(blocked).getByText(/Changing billing cycle isn’t supported/i),
      ).toBeInTheDocument()

      view.unmount()
    }
  })

  it('surfaces a backend refusal the page did not predict', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_BASIC, 'ACTIVE')),
      plansHandler(ALL_PLANS),
      http.post(apiUrl('/subscriptions/current/checkout/'), () =>
        HttpResponse.json(
          {
            detail: 'Downgrading isn’t supported yet.',
            code: 'downgrade_not_supported',
          },
          { status: 409 },
        ),
      ),
    )
    renderSubscription()

    await cardsReady('BASIC_MONTHLY')
    await userEvent.click(await cardFor('PRO_MONTHLY'))
    const dialog = await screen.findByRole('dialog', { name: 'Upgrade plan' })
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Continue to payment' }),
    )

    expect(
      await screen.findByText('Downgrading isn’t supported yet.'),
    ).toBeInTheDocument()
    // And the page still shows the plan the workspace actually has.
    expect(await cardFor('BASIC_MONTHLY')).toHaveAttribute('aria-checked', 'true')
  })
})
