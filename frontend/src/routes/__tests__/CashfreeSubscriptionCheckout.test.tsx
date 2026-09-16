/**
 * The Cashfree branch of subscription checkout: the page opens a MANDATE with
 * an opaque session token, never a key or an amount, and claims nothing about
 * activation on its own.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../../test/msw/server'
import {
  authHandlers,
  apiUrl,
  currentSubscriptionHandler,
  PLAN_PRO,
  plansHandler,
  TENANT_A,
  tenantsMeHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import { AppRoutes } from '../AppRoutes'

const opened: { sessionToken?: string; mode?: string }[] = []

vi.mock('../cashfreeSubscriptionCheckout', () => ({
  openCashfreeSubscriptionCheckout: (sessionToken: string, mode: string) => {
    opened.push({ sessionToken, mode })
    return Promise.resolve()
  },
}))

function cashfreeStart(overrides: Record<string, unknown> = {}) {
  return http.post(apiUrl('/subscriptions/current/checkout/'), () =>
    HttpResponse.json({
      provider: 'cashfree',
      subscription_id: 'tnrsub_live',
      session_token: 'sess_abc',
      checkout_mode: 'sandbox',
      razorpay_subscription_id: 'tnrsub_live',
      razorpay_key_id: '',
      plan: PLAN_PRO,
      status: 'CREATED',
      ...overrides,
    }),
  )
}

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

beforeEach(() => {
  opened.length = 0
  sessionStorage.clear()
  localStorage.clear()
})

describe('SubscriptionPage — Cashfree recurring checkout', () => {
  it('opens the mandate with the session token the server issued', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      cashfreeStart(),
    )
    renderSubscription()

    await screen.findByText('No active subscription')
    await userEvent.click(screen.getByRole('radio', { name: /Pro/ }))

    await waitFor(() => expect(opened).toHaveLength(1))
    expect(opened[0]).toEqual({ sessionToken: 'sess_abc', mode: 'sandbox' })
    // Nothing is claimed about the subscription from the browser's side.
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
  })

  it('confirms with the server on return and reports only "processing"', async () => {
    let confirmBody: Record<string, unknown> | null = null
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      http.post(apiUrl('/subscriptions/current/confirm-checkout/'), async ({ request }) => {
        confirmBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ status: 'processing' })
      }),
    )
    // Cashfree redirected this tab away and back; the parked checkout is what
    // survives the round trip.
    sessionStorage.setItem('tenora.pending_subscription_checkout', 'tnrsub_live')
    renderSubscription()

    expect(
      await screen.findByText(/activating your subscription/i),
    ).toBeInTheDocument()
    expect(confirmBody).toEqual({ subscription_id: 'tnrsub_live' })
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
    // Read exactly once — a reload must not re-confirm.
    expect(sessionStorage.getItem('tenora.pending_subscription_checkout')).toBeNull()
  })

  it('does not claim success when the server cannot confirm the mandate', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      plansHandler(),
      http.post(apiUrl('/subscriptions/current/confirm-checkout/'), () =>
        HttpResponse.json({ detail: 'Checkout could not be verified.' }, { status: 400 }),
      ),
    )
    sessionStorage.setItem('tenora.pending_subscription_checkout', 'tnrsub_live')
    renderSubscription()

    expect(await screen.findByText(/couldn’t verify the checkout/i)).toBeInTheDocument()
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
  })
})
