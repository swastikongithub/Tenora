/**
 * P9 online resident payments — UI contract. The server decides eligibility,
 * amounts and outcomes (apps/properties/tests/test_online_payments.py); these
 * tests pin that the UI only renders what the server says, sends no amount,
 * launches Cashfree with the returned session, never double-submits, and never
 * claims success before the status endpoint does.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../../lib/auth'
import type { BillDetail, OnlinePaymentAttempt, OnlinePaymentEligibility } from '../../../lib/property/types'
import { createQueryClient } from '../../../lib/query-client'
import type { TenantMembership } from '../../../lib/tenant'
import { server } from '../../../test/msw/server'
import { apiUrl, authHandlers, TENANT_A, TENANT_B, tenantsMeHandler } from '../../../test/fixtures'
import { BILL_DETAIL, json, page, shellHandlers } from '../../../test/property-fixtures'
import { AppRoutes } from '../../AppRoutes'

const checkout = vi.fn()
const load = vi.fn()
vi.mock('@cashfreepayments/cashfree-js', () => ({ load: (...args: unknown[]) => load(...args) }))

function renderAt(path: string, asTenant: TenantMembership = TENANT_B) {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  localStorage.setItem('billing.last_tenant_id', asTenant.id)
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const eligible = (over: Partial<OnlinePaymentEligibility> = {}): OnlinePaymentEligibility => ({
  available: true,
  reason: null,
  amount_cents: 1078000,
  currency: 'INR',
  open_attempt: null,
  ...over,
})

const billWith = (online_payment?: OnlinePaymentEligibility, over: Partial<BillDetail> = {}): BillDetail => ({
  ...BILL_DETAIL,
  line_items: [],
  payments: [],
  receipts: [],
  corrections: [],
  online_payment,
  ...over,
})

const attempt = (over: Partial<OnlinePaymentAttempt> = {}): OnlinePaymentAttempt => ({
  id: 'att-1',
  bill_id: 'bill-1',
  status: 'ACTIVE',
  display_state: 'processing',
  amount_cents: 1078000,
  currency: 'INR',
  order_id: 'TNRatt1',
  expires_at: '2026-04-05T10:30:00Z',
  failure_message: '',
  unapplied_reason: '',
  refund_status: '',
  receipt_id: null,
  created_at: '2026-04-05T10:00:00Z',
  finalized_at: null,
  ...over,
})

beforeEach(() => {
  checkout.mockReset().mockResolvedValue({ redirect: true })
  load.mockReset().mockResolvedValue({ checkout })
  server.use(...authHandlers(), ...shellHandlers(), tenantsMeHandler([TENANT_A, TENANT_B]))
})

describe('Pay online button', () => {
  it('shows the server-computed amount for an eligible bill', async () => {
    server.use(json('/bills/bill-1/', billWith(eligible())))
    renderAt('/bills/bill-1')
    expect(await screen.findByRole('button', { name: 'Pay ₹10,780.00 online' })).toBeEnabled()
  })

  it.each([
    ['paid / nothing due', eligible({ available: false, reason: 'NOTHING_DUE', amount_cents: 0 })],
    ['feature disabled', eligible({ available: false, reason: 'DISABLED' })],
    ['viewer is not the resident', eligible({ available: false, reason: 'NOT_RESIDENT' })],
    ['no block at all', undefined],
  ])('is hidden when %s', async (_label, block) => {
    server.use(json('/bills/bill-1/', billWith(block, { status: 'PAID', display_status: 'PAID' })))
    renderAt('/bills/bill-1')
    expect(await screen.findByRole('heading', { name: 'March 2026' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /online/ })).not.toBeInTheDocument()
  })

  it('asks for a phone number instead of offering checkout', async () => {
    server.use(json('/bills/bill-1/', billWith(eligible({ available: false, reason: 'PHONE_REQUIRED' }))))
    renderAt('/bills/bill-1')
    const hint = await screen.findByText(/add a 10-digit mobile number/)
    expect(within(hint).getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings')
    expect(screen.queryByRole('button', { name: /online/ })).not.toBeInTheDocument()
  })

  it('starts checkout with no amount in the request and opens Cashfree with the returned session', async () => {
    const bodies: unknown[] = []
    let resolveStart: () => void = () => {}
    const gate = new Promise<void>((r) => (resolveStart = r))
    server.use(
      json('/bills/bill-1/', billWith(eligible())),
      http.post(apiUrl('/bills/bill-1/online-payment/'), async ({ request }) => {
        bodies.push(await request.text())
        await gate
        return HttpResponse.json(attempt({ payment_session_id: 'session_abc', checkout_mode: 'sandbox' }), { status: 201 })
      }),
    )
    renderAt('/bills/bill-1')
    const button = await screen.findByRole('button', { name: 'Pay ₹10,780.00 online' })
    await userEvent.click(button)
    // Loading and disabled while the server creates the order: no double submit.
    await waitFor(() => expect(button).toBeDisabled())
    await userEvent.click(button)
    resolveStart()
    await waitFor(() => expect(checkout).toHaveBeenCalledTimes(1))
    expect(bodies).toHaveLength(1)
    expect(bodies[0]).not.toMatch(/amount/)
    expect(load).toHaveBeenCalledWith({ mode: 'sandbox' })
    expect(checkout).toHaveBeenCalledWith({ paymentSessionId: 'session_abc', redirectTarget: '_self' })
  })

  it('shows the server error and re-enables the button', async () => {
    server.use(
      json('/bills/bill-1/', billWith(eligible())),
      http.post(apiUrl('/bills/bill-1/online-payment/'), () =>
        HttpResponse.json({ detail: 'Couldn’t reach the payment provider. Try again.', code: 'PAYMENT_PROVIDER_UNAVAILABLE' }, { status: 503 }),
      ),
    )
    renderAt('/bills/bill-1')
    const button = await screen.findByRole('button', { name: 'Pay ₹10,780.00 online' })
    await userEvent.click(button)
    expect(await screen.findByText('Couldn’t reach the payment provider. Try again.')).toBeInTheDocument()
    expect(button).toBeEnabled()
    expect(checkout).not.toHaveBeenCalled()
  })

  it('offers to continue an open checkout', async () => {
    server.use(json('/bills/bill-1/', billWith(eligible({ open_attempt: attempt() }))))
    renderAt('/bills/bill-1')
    expect(await screen.findByRole('button', { name: 'Continue payment' })).toBeInTheDocument()
  })
})

describe('returning from checkout', () => {
  it('shows processing until the server confirms, then success with the receipt', async () => {
    let calls = 0
    server.use(
      json('/bills/bill-1/', billWith(eligible())),
      http.get(apiUrl('/online-payments/att-1/'), () => {
        calls += 1
        return HttpResponse.json(
          calls < 2
            ? attempt()
            : attempt({ status: 'SUCCEEDED', display_state: 'succeeded', receipt_id: 'rcpt-9', finalized_at: '2026-04-05T10:02:00Z' }),
        )
      }),
    )
    renderAt('/bills/bill-1?online_payment=att-1')
    expect(await screen.findByText('Payment processing.')).toBeInTheDocument()
    expect(screen.queryByText('Payment successful.')).not.toBeInTheDocument()
    expect(await screen.findByText('Payment successful.', {}, { timeout: 4000 })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View receipt' })).toHaveAttribute('href', '/receipts/rcpt-9')
  })

  it.each([
    [attempt({ display_state: 'failed', failure_message: 'Card declined.' }), 'Payment failed.', /Card declined\. You can try again\./],
    [attempt({ status: 'EXPIRED', display_state: 'expired' }), 'Payment expired.', /start a new payment/],
    [attempt({ status: 'UNAPPLIED', display_state: 'already_paid' }), 'Payment already completed.', /will refund it/],
  ])('renders the %s state from the server', async (state, title, detail) => {
    server.use(json('/bills/bill-1/', billWith(eligible())), json('/online-payments/att-1/', state))
    renderAt('/bills/bill-1?online_payment=att-1')
    const status = await screen.findByText(title)
    expect(status.closest('[role="status"]')).toHaveTextContent(detail)
  })
})

describe('owner views', () => {
  it('hides void for online payments and offers no Pay online to the owner', async () => {
    const onlinePayment = { ...BILL_DETAIL, id: 'pay-online', method: 'ONLINE', status: 'COMPLETED', amount_cents: 1378000 }
    server.use(
      json('/bills/bill-1/', billWith(eligible({ available: false, reason: 'NOT_RESIDENT' }), {
        payments: [
          { ...onlinePayment, bill_id: 'bill-1', bill_number: 'BILL-2026-000001', resident_name: 'Rahul', unit_identifier: '203', period_start: '2026-03-01', currency: 'INR', payment_date: '2026-04-05', reference: 'cashfree:1', notes: '', voided_at: null, void_reason: '', receipt_id: 'r1', receipt_number: 'REC-1', created_at: '2026-04-05T10:00:00Z' },
          { ...onlinePayment, id: 'pay-cash', method: 'CASH', bill_id: 'bill-1', bill_number: 'BILL-2026-000001', resident_name: 'Rahul', unit_identifier: '203', period_start: '2026-03-01', currency: 'INR', payment_date: '2026-04-05', reference: '', notes: '', voided_at: null, void_reason: '', receipt_id: 'r2', receipt_number: 'REC-2', created_at: '2026-04-05T10:00:00Z', amount_cents: 1000 },
        ] as BillDetail['payments'],
      })),
      json('/payments/', page([])),
      json('/online-payments/', page([attempt({ status: 'UNAPPLIED', display_state: 'already_paid', resident_name: 'Rahul Sharma', unit_identifier: '203', bill_number: 'BILL-2026-000001', period_start: '2026-03-01' })])),
    )
    renderAt('/bills/bill-1', TENANT_A)
    expect(await screen.findByRole('button', { name: 'Void ₹10.00 payment' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Void ₹13,780.00 payment' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /online/ })).not.toBeInTheDocument()
  })

  it('lets an owner refund an unapplied online payment from Payments', async () => {
    let refunded = 0
    server.use(
      json('/payments/', page([])),
      json('/online-payments/', page([attempt({ status: 'UNAPPLIED', display_state: 'already_paid', resident_name: 'Rahul Sharma', unit_identifier: '203', bill_number: 'BILL-2026-000001', period_start: '2026-03-01' })])),
      http.post(apiUrl('/online-payments/att-1/refund/'), () => {
        refunded += 1
        return HttpResponse.json(attempt({ status: 'REFUNDED', display_state: 'already_paid' }))
      }),
    )
    renderAt('/payments', TENANT_A)
    const table = await screen.findByRole('table', { name: 'Online payments needing a refund' })
    await userEvent.click(within(table).getByRole('button', { name: 'Refund' }))
    await waitFor(() => expect(refunded).toBe(1))
  })
})
