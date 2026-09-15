/**
 * P10: PDF downloads for bills and receipts, and the owner's cross-workspace
 * billing portfolio. Presentation and request-shape claims only — visibility of
 * the PDFs and the portfolio's workspace set are enforced and tested on the
 * backend (apps/properties/tests/test_documents.py, test_portfolio.py).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../../../lib/auth'
import type { BillingPortfolio, Receipt } from '../../../lib/property/types'
import { createQueryClient } from '../../../lib/query-client'
import type { TenantMembership } from '../../../lib/tenant'
import { server } from '../../../test/msw/server'
import { apiUrl, authHandlers, TENANT_A, TENANT_B, tenantsMeHandler } from '../../../test/fixtures'
import { BILL_DETAIL, OVERVIEW, json, shellHandlers } from '../../../test/property-fixtures'
import { AppRoutes } from '../../AppRoutes'

const OWNER_B: TenantMembership = { ...TENANT_B, role: 'OWNER' }

function renderAt(path: string, asTenant: TenantMembership = TENANT_A) {
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

const RECEIPT: Receipt = {
  id: 'rcpt-1',
  receipt_number: 'REC-2026-000001',
  issued_at: '2026-04-05T10:00:00Z',
  amount_cents: 1378000,
  currency: 'INR',
  resident_name: 'Rahul Sharma',
  unit_identifier: '203',
  property_name: 'Sunrise Building A',
  bill_id: 'bill-1',
  bill_number: 'BILL-2026-000001',
  payment_id: 'pay-1',
  payment_method: 'UPI',
  payment_status: 'COMPLETED',
  payment_date: '2026-04-05',
  payment_reference: 'UPI-778',
  period_start: '2026-03-01',
  issuer: { name: 'Alpha', contact_email: '', contact_phone: '', address: '', footer: '' },
}

const buckets = (overdue: number) => [
  { key: 'CURRENT' as const, label: 'Current', amount_cents: 0, count: 0 },
  { key: '1_30' as const, label: '1–30 days', amount_cents: overdue, count: overdue ? 1 : 0 },
  { key: '31_60' as const, label: '31–60 days', amount_cents: 0, count: 0 },
  { key: '61_90' as const, label: '61–90 days', amount_cents: 0, count: 0 },
  { key: '90_PLUS' as const, label: '90+ days', amount_cents: 0, count: 0 },
]

const workspace = (id: string, name: string, currency: string, billed: number, overdue: number) => ({
  id,
  name,
  slug: id,
  is_active: true,
  currency,
  billed_cents: billed,
  collected_cents: billed - overdue,
  outstanding_cents: overdue,
  overdue_cents: overdue,
  bills_issued: 1,
  bills_draft: 0,
  bills_paid: overdue ? 0 : 1,
  bills_unpaid: overdue ? 1 : 0,
  total_outstanding_cents: overdue,
  total_overdue_cents: overdue,
  buckets: buckets(overdue),
})

const total = (currency: string, workspaces: number, billed: number, overdue: number) => ({
  currency,
  workspaces,
  billed_cents: billed,
  collected_cents: billed - overdue,
  outstanding_cents: overdue,
  overdue_cents: overdue,
  total_outstanding_cents: overdue,
  total_overdue_cents: overdue,
  buckets: buckets(overdue),
})

const PORTFOLIO: BillingPortfolio = {
  period: '2026-03',
  workspaces: [workspace(TENANT_A.id, TENANT_A.name, 'INR', 1378000, 1000000), workspace(OWNER_B.id, OWNER_B.name, 'INR', 500000, 0)],
  totals: [total('INR', 2, 1878000, 1000000)],
}

beforeEach(() => {
  server.use(...authHandlers(), ...shellHandlers(), tenantsMeHandler([TENANT_A, OWNER_B]))
  URL.createObjectURL = vi.fn(() => 'blob:tenora-test')
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PDF downloads', () => {
  it('an issued bill downloads its PDF through the authenticated client', async () => {
    const clicked: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download)
    })
    const seen: Array<string | null> = []
    server.use(
      json('/bills/bill-1/', { ...BILL_DETAIL, line_items: [], payments: [], receipts: [], corrections: [] }),
      http.get(apiUrl('/bills/bill-1/pdf/'), ({ request }) => {
        seen.push(request.headers.get('X-Tenant-ID'))
        return new HttpResponse(new Blob(['%PDF-1.4'], { type: 'application/pdf' }), { headers: { 'Content-Type': 'application/pdf' } })
      }),
    )
    renderAt('/bills/bill-1')
    await userEvent.click(await screen.findByRole('button', { name: 'Download PDF' }))
    await vi.waitFor(() => expect(clicked).toEqual(['BILL-2026-000001.pdf']))
    expect(seen).toEqual([TENANT_A.id])
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('a draft bill offers no PDF', async () => {
    server.use(
      json('/bills/bill-1/', {
        ...BILL_DETAIL, status: 'DRAFT', display_status: 'DRAFT', bill_number: '', published_at: null,
        line_items: [], payments: [], receipts: [], corrections: [],
      }),
    )
    renderAt('/bills/bill-1')
    expect(await screen.findByRole('heading', { name: 'March 2026' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Download PDF' })).not.toBeInTheDocument()
  })

  it('a failed download says so instead of failing silently', async () => {
    server.use(
      json('/bills/bill-1/', { ...BILL_DETAIL, line_items: [], payments: [], receipts: [], corrections: [] }),
      json('/bills/bill-1/pdf/', { detail: 'Not found.' }, 404),
    )
    renderAt('/bills/bill-1')
    await userEvent.click(await screen.findByRole('button', { name: 'Download PDF' }))
    expect(await screen.findByText('Not found.')).toHaveAttribute('role', 'alert')
  })

  it('a receipt downloads its own PDF', async () => {
    const paths: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    server.use(
      json('/receipts/rcpt-1/', RECEIPT),
      http.get(apiUrl('/receipts/rcpt-1/pdf/'), ({ request }) => {
        paths.push(new URL(request.url).pathname)
        return new HttpResponse(new Blob(['%PDF-1.4'], { type: 'application/pdf' }))
      }),
    )
    renderAt('/receipts/rcpt-1')
    await userEvent.click(await screen.findByRole('button', { name: 'Download PDF' }))
    await vi.waitFor(() => expect(paths).toEqual(['/api/receipts/rcpt-1/pdf/']))
  })
})

describe('owner billing portfolio', () => {
  it('shows totals and each owned workspace, without a workspace header', async () => {
    const tenantHeaders: Array<string | null> = []
    server.use(
      http.get(apiUrl('/account/billing-portfolio/'), ({ request }) => {
        tenantHeaders.push(request.headers.get('X-Tenant-ID'))
        return HttpResponse.json(PORTFOLIO)
      }),
    )
    renderAt('/billing/portfolio')
    const table = await screen.findByRole('table', { name: 'Billing by workspace' })
    expect(within(table).getByText(TENANT_A.name)).toBeInTheDocument()
    expect(within(table).getByText(OWNER_B.name)).toBeInTheDocument()
    expect(within(table).getByText('Current')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /All workspaces · March 2026/ })).toBeInTheDocument()
    expect(screen.getByText('₹18,780.00')).toBeInTheDocument()
    expect(tenantHeaders.every((h) => h === null)).toBe(true)
  })

  it('keeps each currency in its own totals', async () => {
    server.use(
      json('/account/billing-portfolio/', {
        period: '2026-03',
        workspaces: [workspace(TENANT_A.id, TENANT_A.name, 'INR', 1378000, 0), workspace(OWNER_B.id, OWNER_B.name, 'USD', 5000, 0)],
        totals: [total('INR', 1, 1378000, 0), total('USD', 1, 5000, 0)],
      }),
    )
    renderAt('/billing/portfolio')
    expect(await screen.findByRole('heading', { name: /INR workspaces/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /USD workspaces/ })).toBeInTheDocument()
  })

  it('opening another workspace switches to it and lands on its billing', async () => {
    const overviewTenants: Array<string | null> = []
    server.use(
      json('/account/billing-portfolio/', PORTFOLIO),
      http.get(apiUrl('/workspace/overview/'), ({ request }) => {
        overviewTenants.push(request.headers.get('X-Tenant-ID'))
        return HttpResponse.json(OVERVIEW)
      }),
      json('/billing/summary/', OVERVIEW.current_month),
      json('/billing/cycles/', []),
    )
    renderAt('/billing/portfolio')
    await userEvent.click(await screen.findByRole('button', { name: `Open billing for ${OWNER_B.name}` }))
    await vi.waitFor(() => expect(overviewTenants).toContain(OWNER_B.id))
    expect(await screen.findByRole('button', { name: new RegExp(OWNER_B.name) })).toBeInTheDocument()
  })
})
