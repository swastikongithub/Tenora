import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../test/msw/server'
import {
  authHandlers,
  apiUrl,
  checkoutConfirmHandler,
  checkoutStartHandler,
  currentSubscriptionByTenantHandler,
  currentSubscriptionHandler,
  PLAN_PRO,
  PLAN_TEAM,
  plansHandler,
  subscriptionFor,
  TENANT_A,
  TENANT_B,
  tenantsMeHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import { queryKeys } from '../../lib/query-keys'
import { AppRoutes } from '../AppRoutes'

/** Render the app at /subscription. `asTenant` picks the active tenant (and so
 *  the caller's role): TENANT_A → OWNER, TENANT_B → MEMBER. Returns the query
 *  client used, so a test can inspect the cache directly. */
function renderSubscription(asTenant = TENANT_A) {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  localStorage.setItem('billing.last_tenant_id', asTenant.id)
  const queryClient = createQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/subscription']}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
  return queryClient
}

/**
 * The subscription panel and the plan grid both render a plan's name/code/price
 * (the panel shows the tenant's current plan; the grid lists every plan,
 * including that same one) — so a bare `getByText('PRO')` is ambiguous the
 * moment both have loaded. Scope to the panel via its Card, found from the
 * status badge (nothing else on the page renders a status).
 */
async function findPanel(): Promise<HTMLElement> {
  const badge = await screen.findByText(/^(Trialing|Active|Past due|Canceled)$/)
  const panel = badge.closest('.rounded-lg')
  if (!panel) throw new Error('Could not locate the subscription panel Card')
  return panel as HTMLElement
}

/**
 * Stub `window.Razorpay` the way checkout.js would define it — captures the
 * options `useRazorpayCheckout` passes so a test can fire the success handler,
 * the modal `ondismiss`, or a `payment.failed` event directly, without any real
 * Checkout popup (spec §9/§11).
 */
function stubRazorpayCheckout() {
  const state: {
    opts?: {
      key: string
      subscription_id: string
      handler: (r: {
        razorpay_payment_id: string
        razorpay_subscription_id: string
        razorpay_signature: string
      }) => void
      modal: { ondismiss: () => void }
    }
    failHandlers: Array<(resp: unknown) => void>
    opened: boolean
  } = { failHandlers: [], opened: false }

  class FakeRazorpay {
    constructor(opts: (typeof state)['opts']) {
      state.opts = opts
    }
    on(_event: string, cb: (resp: unknown) => void) {
      state.failHandlers.push(cb)
    }
    open() {
      state.opened = true
    }
  }
  ;(window as unknown as { Razorpay: unknown }).Razorpay = FakeRazorpay

  return {
    get options() {
      return state.opts
    },
    get opened() {
      return state.opened
    },
    succeed: () =>
      state.opts?.handler({
        razorpay_payment_id: 'pay_TEST',
        razorpay_subscription_id: state.opts.subscription_id,
        razorpay_signature: 'sig_TEST',
      }),
    dismiss: () => state.opts?.modal.ondismiss(),
    fail: (description = 'Card declined') =>
      state.failHandlers.forEach((cb) => cb({ error: { description } })),
  }
}

beforeEach(() => {
  setCurrentTenantId(null)
  localStorage.clear()
  sessionStorage.clear()
  delete (window as unknown as { Razorpay?: unknown }).Razorpay
})

describe('SubscriptionPage — current subscription panel', () => {
  it('renders plan, price, status badge, and period for an active subscription', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    const panel = await findPanel()
    expect(within(panel).getByText('Active')).toBeInTheDocument()
    expect(within(panel).getByRole('heading', { name: 'Pro' })).toBeInTheDocument()
    expect(within(panel).getByText('PRO')).toBeInTheDocument()
    expect(within(panel).getByText(/29\.00/)).toBeInTheDocument()
  })

  it('treats a 404 as "no subscription yet", not an error', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    expect(
      await screen.findByText('No active subscription'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(
      screen.getByText('Choose a plan below to start billing for this workspace.'),
    ).toBeInTheDocument()
  })

  it('MEMBER sees the no-subscription message without an action hint', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_B]),
      currentSubscriptionHandler(null),
      plansHandler(),
    )
    renderSubscription(TENANT_B)

    expect(
      await screen.findByText('No active subscription'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('An owner of this workspace can start one.'),
    ).toBeInTheDocument()
  })

  it('shows a retry panel for a genuine failure, distinct from the 404 empty state', async () => {
    let attempts = 0
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/subscriptions/current/'), () => {
        attempts += 1
        return attempts === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(subscriptionFor(PLAN_PRO))
      }),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    expect(
      await screen.findByText('Couldn’t load this workspace’s subscription.'),
    ).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))

    const panel = await findPanel()
    expect(within(panel).getByText('PRO')).toBeInTheDocument()
  })

  it('shows a skeleton while the subscription is loading', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/subscriptions/current/'), async () => {
        await new Promise((r) => setTimeout(r, 40))
        return HttpResponse.json(subscriptionFor(PLAN_PRO))
      }),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    expect(await screen.findByText('Loading subscription')).toBeInTheDocument()
    const panel = await findPanel()
    expect(within(panel).getByText('PRO')).toBeInTheDocument()
  })
})

describe('SubscriptionPage — status badge', () => {
  it.each([
    ['TRIALING', 'Trialing'],
    ['ACTIVE', 'Active'],
    ['PAST_DUE', 'Past due'],
    ['CANCELED', 'Canceled'],
  ] as const)('%s renders as "%s"', async (status, label) => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, status)),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    expect(await screen.findByText(label)).toBeInTheDocument()
  })

  it('CANCELED shows no reactivate control anywhere on the page', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'CANCELED')),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('Canceled')
    expect(
      screen.queryByRole('button', { name: /reactivate/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /activate/i }),
    ).not.toBeInTheDocument()
  })

  it('CANCELED removes plan selection entirely — a plain list, not disabled radios', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'CANCELED')),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('Canceled')
    await screen.findByText('Team') // plans have loaded
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  })
})

describe('SubscriptionPage — plan grid', () => {
  it('shows a skeleton while loading', async () => {
    // A real-timer delay (the pattern used elsewhere, e.g. MembersPage) races
    // against how long the plans query takes to actually start fetching: unlike
    // the tenant-gated subscription query, plans fetches immediately on mount,
    // so under system load the timer can fire — and the pending state flip
    // back to resolved — before the loading skeleton is ever painted. A
    // manually-controlled promise makes the pending window deterministic
    // instead of racing a clock.
    let resolvePlans: (plans: typeof PLAN_PRO[]) => void = () => {}
    const deferred = new Promise<Array<typeof PLAN_PRO>>((resolve) => {
      resolvePlans = resolve
    })
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      http.get(apiUrl('/plans/'), async () => HttpResponse.json(await deferred)),
    )
    renderSubscription(TENANT_A)

    expect(await screen.findByText('Loading plans')).toBeInTheDocument()
    resolvePlans([PLAN_PRO, PLAN_TEAM])
    expect(await screen.findByText('Team')).toBeInTheDocument()
  })

  it('phrases an empty plan catalogue as an operational problem', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler([]),
    )
    renderSubscription(TENANT_A)

    expect(
      await screen.findByText(/No plans available/),
    ).toBeInTheDocument()
  })

  it('shows a retry panel on plan-list failure', async () => {
    let attempts = 0
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      http.get(apiUrl('/plans/'), () => {
        attempts += 1
        return attempts === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json([PLAN_PRO, PLAN_TEAM])
      }),
    )
    renderSubscription(TENANT_A)

    await userEvent.click(await screen.findByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Team')).toBeInTheDocument()
  })

  it('marks the radiogroup, checks the current plan, and moves focus with arrow keys', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    // Wait for the subscription to resolve first — otherwise the grid renders
    // with no plan yet marked current, and the aria-checked assertions below
    // would race against that second render.
    await findPanel()

    const group = await screen.findByRole('radiogroup', {
      name: 'Available plans',
    })
    const radios = within(group).getAllByRole('radio')
    expect(radios).toHaveLength(2)

    const proRadio = within(group).getByRole('radio', { name: /Pro/ })
    const teamRadio = within(group).getByRole('radio', { name: /Team/ })
    expect(proRadio).toHaveAttribute('aria-checked', 'true')
    expect(teamRadio).toHaveAttribute('aria-checked', 'false')
    expect(proRadio).toHaveAttribute('tabindex', '0')
    expect(teamRadio).toHaveAttribute('tabindex', '-1')

    proRadio.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(teamRadio).toHaveFocus()
    expect(teamRadio).toHaveAttribute('tabindex', '0')
  })
})

describe('SubscriptionPage — OWNER change plan', () => {

  it('opens a confirmation modal naming current and target plan before changing', async () => {
    let current = subscriptionFor(PLAN_PRO, 'ACTIVE')
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/subscriptions/current/'), () =>
        HttpResponse.json(current),
      ),
      plansHandler(),
      http.patch(apiUrl('/subscriptions/current/'), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        expect(body).toEqual({ plan_id: PLAN_TEAM.id })
        current = subscriptionFor(PLAN_TEAM, 'ACTIVE')
        return HttpResponse.json(current)
      }),
    )
    renderSubscription(TENANT_A)

    await findPanel()
    await userEvent.click(screen.getByRole('radio', { name: /Team/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Change plan' })
    expect(within(dialog).getByText(/Pro/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Team/)).toBeInTheDocument()

    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Change plan' }),
    )

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    const panel = await findPanel()
    expect(within(panel).getByText('TEAM')).toBeInTheDocument()
  })

  it('dismissing the confirmation modal sends no request', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      plansHandler(),
      http.patch(apiUrl('/subscriptions/current/'), () => {
        throw new Error('PATCH must not be called when the modal is dismissed')
      }),
    )
    renderSubscription(TENANT_A)

    await findPanel()
    await userEvent.click(screen.getByRole('radio', { name: /Team/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Change plan' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const panel = await findPanel()
    expect(within(panel).getByText('PRO')).toBeInTheDocument()
  })

  it('re-selecting the current plan is a no-op', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      plansHandler(),
      http.patch(apiUrl('/subscriptions/current/'), () => {
        throw new Error('PATCH must not be called for the already-selected plan')
      }),
    )
    renderSubscription(TENANT_A)

    await findPanel()
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('SubscriptionPage — checkout (D2)', () => {
  it('opens Razorpay Checkout (no local subscription created) when none exists yet', async () => {
    const rzp = stubRazorpayCheckout()
    let confirmBody: Record<string, unknown> | null = null
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      http.post(apiUrl('/subscriptions/current/checkout/'), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        expect(body).toEqual({ plan_id: PLAN_PRO.id })
        return HttpResponse.json({
          razorpay_subscription_id: 'sub_RZP1',
          razorpay_key_id: 'rzp_test_KEY',
          plan: PLAN_PRO,
        })
      }),
      http.post(
        apiUrl('/subscriptions/current/confirm-checkout/'),
        async ({ request }) => {
          confirmBody = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({ status: 'processing' })
        },
      ),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('No active subscription')
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))

    await waitFor(() => expect(rzp.opened).toBe(true))
    expect(rzp.options?.key).toBe('rzp_test_KEY')
    expect(rzp.options?.subscription_id).toBe('sub_RZP1')

    // Fire Checkout's success callback.
    rzp.succeed()

    expect(
      await screen.findByText(/activating your subscription/i),
    ).toBeInTheDocument()
    // Honest state: never "Active"/"Trialing", no subscription panel.
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
    expect(screen.queryByText('Trialing')).not.toBeInTheDocument()
    expect(confirmBody).toEqual({
      razorpay_payment_id: 'pay_TEST',
      razorpay_subscription_id: 'sub_RZP1',
      razorpay_signature: 'sig_TEST',
    })
  })

  it('dismissing Checkout sends no confirm request and shows a clean message', async () => {
    const rzp = stubRazorpayCheckout()
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      checkoutStartHandler({ razorpay_subscription_id: 'sub_RZP2' }),
      http.post(apiUrl('/subscriptions/current/confirm-checkout/'), () => {
        throw new Error('confirm-checkout must not be called on dismiss')
      }),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('No active subscription')
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))
    await waitFor(() => expect(rzp.opened).toBe(true))

    rzp.dismiss()

    expect(
      await screen.findByText(/closed before payment/i),
    ).toBeInTheDocument()
    // The empty state + plan grid are still there to retry.
    expect(screen.getByText('No active subscription')).toBeInTheDocument()
    expect(screen.getByRole('radiogroup')).toBeInTheDocument()
  })

  it('a failed payment shows a clean error', async () => {
    const rzp = stubRazorpayCheckout()
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      checkoutStartHandler(),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('No active subscription')
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))
    await waitFor(() => expect(rzp.opened).toBe(true))

    rzp.fail('Your card was declined')

    expect(
      await screen.findByText('Your card was declined'),
    ).toBeInTheDocument()
  })

  it('a confirm-checkout signature failure does not claim success', async () => {
    const rzp = stubRazorpayCheckout()
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      checkoutStartHandler(),
      checkoutConfirmHandler(false), // 400
    )
    renderSubscription(TENANT_A)

    await screen.findByText('No active subscription')
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))
    await waitFor(() => expect(rzp.opened).toBe(true))

    rzp.succeed()

    expect(
      await screen.findByText(/couldn.t verify the checkout/i),
    ).toBeInTheDocument()
    expect(screen.queryByText(/activating your subscription/i)).not.toBeInTheDocument()
  })
})

describe('SubscriptionPage — OWNER cancel subscription', () => {
  const CANCEL_BTN = { name: 'Cancel subscription' }

  it('shows the cancel control for an OWNER on a cancellable subscription', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    const panel = await findPanel()
    expect(within(panel).getByRole('button', CANCEL_BTN)).toBeInTheDocument()
  })

  it('hides the cancel control for a MEMBER', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_B]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      plansHandler(),
    )
    renderSubscription(TENANT_B)

    await findPanel()
    expect(screen.queryByRole('button', CANCEL_BTN)).not.toBeInTheDocument()
  })

  it('hides the cancel control once the subscription is CANCELED', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'CANCELED')),
      plansHandler(),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('Canceled')
    expect(screen.queryByRole('button', CANCEL_BTN)).not.toBeInTheDocument()
  })

  it('cancels through the type-to-confirm flow and renders the terminal state', async () => {
    let current = subscriptionFor(PLAN_PRO, 'ACTIVE')
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/subscriptions/current/'), () =>
        HttpResponse.json(current),
      ),
      plansHandler(),
      http.patch(apiUrl('/subscriptions/current/'), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        expect(body).toEqual({ status: 'CANCELED' })
        expect(body.plan_id).toBeUndefined()
        expect(body.tenant_id).toBeUndefined()
        current = { ...current, status: 'CANCELED' }
        return HttpResponse.json(current)
      }),
    )
    renderSubscription(TENANT_A)

    const panel = await findPanel()
    await userEvent.click(within(panel).getByRole('button', { name: 'Cancel subscription' }))

    const dialog = await screen.findByRole('dialog', { name: 'Cancel subscription' })
    const confirm = within(dialog).getByRole('button', {
      name: 'Cancel subscription',
    })
    expect(confirm).toBeDisabled()

    await userEvent.type(within(dialog).getByLabelText(/to confirm/i), TENANT_A.name)
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(await screen.findByText('Canceled')).toBeInTheDocument()
    // Terminal state: the cancel control is gone.
    expect(
      screen.queryByRole('button', { name: 'Cancel subscription' }),
    ).not.toBeInTheDocument()
  })

  it('sends no request when the modal is dismissed', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      plansHandler(),
      http.patch(apiUrl('/subscriptions/current/'), () => {
        throw new Error('PATCH must not fire when the cancel modal is dismissed')
      }),
    )
    renderSubscription(TENANT_A)

    const panel = await findPanel()
    await userEvent.click(within(panel).getByRole('button', { name: 'Cancel subscription' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cancel subscription' })
    // type a valid confirmation, then dismiss anyway
    await userEvent.type(within(dialog).getByLabelText(/to confirm/i), TENANT_A.name)
    await userEvent.keyboard('{Escape}')

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(within(await findPanel()).getByText('Active')).toBeInTheDocument()
  })

  it('surfaces a stale-render 400 (already CANCELED) in the modal without crashing', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      plansHandler(),
      http.patch(apiUrl('/subscriptions/current/'), () =>
        HttpResponse.json(
          { status: ['Cannot transition from CANCELED to CANCELED.'] },
          { status: 400 },
        ),
      ),
    )
    renderSubscription(TENANT_A)

    const panel = await findPanel()
    await userEvent.click(within(panel).getByRole('button', { name: 'Cancel subscription' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cancel subscription' })
    await userEvent.type(within(dialog).getByLabelText(/to confirm/i), TENANT_A.name)
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Cancel subscription' }),
    )

    expect(
      await within(dialog).findByText(
        'Cannot transition from CANCELED to CANCELED.',
      ),
    ).toBeInTheDocument()
    // still open, still on-screen
    expect(screen.getByRole('dialog', { name: 'Cancel subscription' })).toBeInTheDocument()
  })
})

describe('SubscriptionPage — MEMBER view', () => {
  it('renders read-only: no radiogroup, no create/change affordance', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_B]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      plansHandler(),
    )
    renderSubscription(TENANT_B)

    await findPanel()
    await screen.findByText('Team')
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  })

  it('MEMBER with no subscription sees no plan-selection controls', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_B]),
      currentSubscriptionHandler(null),
      plansHandler(),
    )
    renderSubscription(TENANT_B)

    await screen.findByText('No active subscription')
    await screen.findByText('Team')
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
  })
})

describe('SubscriptionPage — error surfaces', () => {
  it('403 on a stale-render checkout attempt renders inline, not a crash', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      http.post(apiUrl('/subscriptions/current/checkout/'), () =>
        HttpResponse.json(
          { detail: 'You do not have permission to perform this action.' },
          { status: 403 },
        ),
      ),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('No active subscription')
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))

    expect(
      await screen.findByText(/don.t have permission to change/i),
    ).toBeInTheDocument()
  })

  it('400 (plan not available for checkout) renders the field message inline', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      http.post(apiUrl('/subscriptions/current/checkout/'), () =>
        HttpResponse.json(
          { plan_id: ['This plan isn’t available for checkout yet.'] },
          { status: 400 },
        ),
      ),
    )
    renderSubscription(TENANT_A)

    await screen.findByText('No active subscription')
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))

    expect(
      await screen.findByText('This plan isn’t available for checkout yet.'),
    ).toBeInTheDocument()
  })

  it('§0: 400 on a CANCELED subscription’s plan change renders the field message inline', async () => {
    // Exercises the backend §0 guard's exact error shape end-to-end, even
    // though the page itself never offers this action once CANCELED — a race
    // or a stale render could still reach it.
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      plansHandler(),
      http.patch(apiUrl('/subscriptions/current/'), () =>
        HttpResponse.json(
          {
            plan_id: [
              'Cannot change the plan of a CANCELED subscription.',
            ],
          },
          { status: 400 },
        ),
      ),
    )
    renderSubscription(TENANT_A)

    await findPanel()
    await userEvent.click(screen.getByRole('radio', { name: /Team/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Change plan' })
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Change plan' }),
    )

    expect(
      await within(dialog).findByText(
        'Cannot change the plan of a CANCELED subscription.',
      ),
    ).toBeInTheDocument()
    // The modal stays open with the error attached, per the page's contract.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('SubscriptionPage — tenant isolation (mixed global + tenant-scoped queries)', () => {
  it('switching tenant refetches the subscription but never the global plan list', async () => {
    let plansCalls = 0
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A, TENANT_B]),
      currentSubscriptionByTenantHandler({
        [TENANT_A.id]: subscriptionFor(PLAN_PRO, 'ACTIVE'),
        [TENANT_B.id]: subscriptionFor(PLAN_TEAM, 'TRIALING'),
      }),
      http.get(apiUrl('/plans/'), () => {
        plansCalls += 1
        return HttpResponse.json([PLAN_PRO, PLAN_TEAM])
      }),
    )
    const queryClient = renderSubscription(TENANT_A)

    const panelA = await findPanel()
    expect(within(panelA).getByText('PRO')).toBeInTheDocument()
    expect(within(panelA).getByText('Active')).toBeInTheDocument()

    await userEvent.click(
      screen.getByRole('button', { name: new RegExp(TENANT_A.name) }),
    )
    await userEvent.click(
      await screen.findByRole('menuitemradio', {
        name: new RegExp(TENANT_B.name),
      }),
    )

    await waitFor(async () => {
      const panelB = await findPanel()
      expect(within(panelB).getByText('TEAM')).toBeInTheDocument()
    })
    const panelB = await findPanel()
    expect(within(panelB).getByText('Trialing')).toBeInTheDocument()

    // The global plan catalogue was fetched once, never refetched on switch —
    // and isolation didn't come from nuking its cache entry.
    expect(plansCalls).toBe(1)
    expect(queryClient.getQueryData(queryKeys.plans())).toBeDefined()
  })
})
