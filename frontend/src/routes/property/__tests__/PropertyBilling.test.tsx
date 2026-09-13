/**
 * Property billing UI (docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md §29.8).
 *
 * Presentation claims only — what renders for whom, what is sent, and that
 * stored values are shown rather than recomputed. Every refusal these tests
 * mention is enforced by the backend suites; the UI merely mirrors it.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import type { TenantMembership } from '../../../lib/tenant'
import { server } from '../../../test/msw/server'
import { apiUrl, authHandlers, TENANT_A, TENANT_B, tenantsMeHandler } from '../../../test/fixtures'
import {
  AGING,
  BILL,
  BILL_DETAIL,
  INVITATION,
  NOTIFICATION,
  OVERVIEW,
  RESIDENCY,
  USAGE_AT_LIMIT,
  json,
  page,
  shellHandlers,
} from '../../../test/property-fixtures'
import { AppRoutes } from '../../AppRoutes'

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

beforeEach(() => {
  server.use(...authHandlers(), ...shellHandlers(), tenantsMeHandler([TENANT_A, TENANT_B]))
})

describe('navigation by role', () => {
  it('an owner sees property management and Subscription', async () => {
    server.use(json('/properties/', []), json('/workspace/overview/', OVERVIEW))
    renderAt('/properties')
    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    for (const label of ['Properties', 'Residents', 'Billing', 'Payments', 'Subscription', 'Settings']) {
      expect(await within(nav).findByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(within(nav).queryByRole('link', { name: 'My Bills' })).not.toBeInTheDocument()
  })

  it('a resident sees the narrow portal and no Subscription', async () => {
    server.use(json('/residency/', RESIDENCY), json('/bills/', page([BILL])))
    renderAt('/home', TENANT_B)
    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    for (const label of ['Dashboard', 'My Bills', 'Billing History', 'Receipts', 'Notifications', 'Settings']) {
      expect(await within(nav).findByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(within(nav).queryByRole('link', { name: 'Subscription' })).not.toBeInTheDocument()
    expect(within(nav).queryByRole('link', { name: 'Properties' })).not.toBeInTheDocument()
  })

  it('a resident typing an owner URL is sent to their dashboard', async () => {
    server.use(json('/residency/', RESIDENCY), json('/bills/', page([BILL])))
    renderAt('/billing/aging', TENANT_B)
    expect(await screen.findByRole('heading', { name: 'Welcome, Rahul' })).toBeInTheDocument()
    expect(screen.queryByText('Total outstanding')).not.toBeInTheDocument()
  })

  it('switching workspace refetches property data under the new X-Tenant-ID', async () => {
    const OWNER_B = { ...TENANT_B, role: 'OWNER' as const }
    const seen: Array<string | null> = []
    server.use(
      tenantsMeHandler([TENANT_A, OWNER_B]),
      json('/workspace/overview/', OVERVIEW),
      http.get(apiUrl('/properties/'), ({ request }) => {
        const tenant = request.headers.get('X-Tenant-ID')
        seen.push(tenant)
        return HttpResponse.json(
          tenant === TENANT_A.id
            ? [{ id: 'pa', name: 'Alpha Tower', is_active: true, unit_count: 1, occupied_count: 1, address_line_1: '', city: '' }]
            : [{ id: 'pb', name: 'Beta Heights', is_active: true, unit_count: 2, occupied_count: 0, address_line_1: '', city: '' }],
        )
      }),
    )
    renderAt('/properties')
    expect(await screen.findByText('Alpha Tower')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: new RegExp(TENANT_A.name) }))
    await userEvent.click(await screen.findByRole('menuitemradio', { name: new RegExp(TENANT_B.name) }))
    expect(await screen.findByText('Beta Heights')).toBeInTheDocument()
    expect(screen.queryByText('Alpha Tower')).not.toBeInTheDocument()
    expect(seen).toContain(TENANT_B.id)
  })
})

describe('bill detail', () => {
  it('explains the bill from stored values: readings, units, rate, total', async () => {
    server.use(json('/bills/bill-1/', BILL_DETAIL))
    renderAt('/bills/bill-1')
    expect(await screen.findByRole('heading', { name: 'March 2026' })).toBeInTheDocument()
    expect(screen.getByText(/12,450/)).toBeInTheDocument()
    expect(screen.getByText(/12,610/)).toBeInTheDocument()
    expect(screen.getAllByText(/160 units/).length).toBeGreaterThan(0)
    expect(screen.getByText(/\/unit/)).toBeInTheDocument()
    expect(screen.getByText(/12 days overdue/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View closing proof' })).toBeInTheDocument()
  })

  it('an owner can record a payment; the body carries an idempotency key and no tenant', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      json('/bills/bill-1/', BILL_DETAIL),
      http.post(apiUrl('/payments/'), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 'pay-1' }, { status: 201 })
      }),
    )
    renderAt('/bills/bill-1')
    await userEvent.click(await screen.findByRole('button', { name: 'Record payment' }))
    const dialog = await screen.findByRole('dialog', { name: 'Record payment' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Record payment' }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ bill_id: 'bill-1', amount_cents: 1378000, method: 'UPI' })
    expect(typeof (body as unknown as Record<string, unknown>).idempotency_key).toBe('string')
    expect(body).not.toHaveProperty('tenant_id')
  })

  it('a resident sees the same bill with no owner actions', async () => {
    server.use(json('/bills/bill-1/', BILL_DETAIL))
    renderAt('/bills/bill-1', TENANT_B)
    expect(await screen.findByRole('heading', { name: 'March 2026' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Record payment' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel bill' })).not.toBeInTheDocument()
  })

  it('renders a server 404 (another resident’s bill) as not found', async () => {
    server.use(http.get(apiUrl('/bills/other/'), () => HttpResponse.json({ detail: 'Not found.' }, { status: 404 })))
    renderAt('/bills/other', TENANT_B)
    expect(await screen.findByText(/doesn’t exist in this workspace/)).toBeInTheDocument()
  })
})

describe('billing aging', () => {
  it('shows buckets and the server-computed overdue days per resident', async () => {
    server.use(json('/billing/aging/', AGING))
    renderAt('/billing/aging')
    expect(await screen.findByText('Total outstanding')).toBeInTheDocument()
    const table = await screen.findByRole('table', { name: 'Outstanding balances' })
    expect(within(table).getByText('74 days')).toBeInTheDocument()
    expect(within(table).getByText('37 days')).toBeInTheDocument()
    expect(within(table).getByText('12 days')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Aging buckets' })).getByText('61–90 days')).toBeInTheDocument()
  })
})

describe('residents, invitations and plan usage', () => {
  it('shows the member usage meter and disables inviting at the limit', async () => {
    server.use(json('/residents/', []), json('/invitations/', []), json('/workspace/usage/', USAGE_AT_LIMIT))
    renderAt('/residents')
    expect(await screen.findByRole('meter', { name: /Members/ })).toHaveAttribute('aria-valuenow', '10')
    expect(await screen.findByText(/Limit reached/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Invite resident' })).toBeDisabled()
  })

  it('sends an invitation (not a membership) and surfaces a limit refusal', async () => {
    server.use(
      json('/residents/', []),
      json('/invitations/', []),
      json('/units/', []),
      json('/workspace/usage/', { ...USAGE_AT_LIMIT, members: { active: 1, pending_invitations: 0, used: 1, limit: 10 } }),
      http.post(apiUrl('/invitations/'), () =>
        HttpResponse.json({ detail: 'This workspace has reached its plan’s member limit (10/10).', code: 'member_limit_reached' }, { status: 403 }),
      ),
    )
    renderAt('/residents')
    await userEvent.click(await screen.findByRole('button', { name: 'Invite resident' }))
    const dialog = await screen.findByRole('dialog', { name: 'Invite a resident' })
    await userEvent.type(within(dialog).getByLabelText('Email'), 'new@example.com')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Send invitation' }))
    expect(await within(dialog).findByText(/member limit/)).toBeInTheDocument()
  })
})

describe('notifications and invitation acceptance', () => {
  it('lists invitations and accepting posts the decision for that invitation only', async () => {
    let sent: Record<string, unknown> | null = null
    server.use(
      json('/notifications/', page([NOTIFICATION])),
      json('/invitations/mine/', [INVITATION]),
      http.post(apiUrl('/invitations/respond/'), async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...INVITATION, status: 'ACCEPTED' })
      }),
    )
    renderAt('/notifications')
    const card = await screen.findByRole('listitem', { name: `Invitation from ${INVITATION.tenant_name}` })
    expect(within(card).getByText(/Unit 203/)).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Accept' }))
    await waitFor(() => expect(sent).toEqual({ id: 'inv-1', action: 'accept' }))
    expect(screen.getByText('Your March 2026 bill is ready')).toBeInTheDocument()
  })

  it('marks a notification as read', async () => {
    let marked: unknown = null
    server.use(
      json('/notifications/', page([NOTIFICATION])),
      json('/invitations/mine/', []),
      http.post(apiUrl('/notifications/read/'), async ({ request }) => {
        marked = await request.json()
        return HttpResponse.json({ updated: 1 })
      }),
    )
    renderAt('/notifications')
    await userEvent.click(await screen.findByRole('button', { name: 'Mark read' }))
    await waitFor(() => expect(marked).toEqual({ ids: ['n-1'] }))
  })

  it('the bell shows the unread count', async () => {
    server.use(json('/notifications/unread-count/', { unread: 3 }), json('/properties/', []), json('/workspace/overview/', OVERVIEW))
    renderAt('/properties')
    expect(await screen.findByRole('link', { name: 'Notifications, 3 unread' })).toBeInTheDocument()
  })
})

describe('settings', () => {
  const profile = {
    id: 'u', email: 'user@example.com', first_name: '', last_name: '', phone: '', has_usable_password: true,
    date_joined: '2026-01-01T00:00:00Z', deletion_blockers: [],
  }
  const settingsHandlers = () => [
    json('/account/profile/', profile),
    json('/notifications/preferences/', { billing: true, payments: true, membership: true, email_enabled: false }),
    json('/account/usage/', { plan_code: null, plan_name: null, workspaces: { used: 1, limit: 2 }, owned_workspaces: [] }),
    json('/memberships/', []),
  ]

  it('an owner gets workspace billing defaults and plan usage', async () => {
    server.use(...settingsHandlers())
    renderAt('/settings')
    expect(await screen.findByRole('heading', { name: 'Workspace profile & billing defaults' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Plan & subscription' })).toBeInTheDocument()
    expect(await screen.findByRole('meter', { name: 'Workspaces' })).toHaveAttribute('aria-valuenow', '1')
  })

  it('a resident gets no workspace or subscription settings, and can leave the workspace', async () => {
    let left = false
    server.use(
      ...settingsHandlers(),
      http.post(apiUrl('/memberships/leave/'), () => {
        left = true
        return new HttpResponse(null, { status: 200 })
      }),
    )
    renderAt('/settings', TENANT_B)
    expect(await screen.findByRole('heading', { name: 'Memberships' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Workspace profile & billing defaults' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Plan & subscription' })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: `Leave ${TENANT_B.name}` }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Your Tenora account stays/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Leave workspace' }))
    await waitFor(() => expect(left).toBe(true))
  })

  it('delete account stays disabled until the email is typed exactly', async () => {
    server.use(...settingsHandlers())
    renderAt('/settings', TENANT_B)
    await userEvent.click(await screen.findByRole('button', { name: 'Delete account' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete your account?' })
    const confirm = within(dialog).getByRole('button', { name: 'Permanently delete' })
    expect(confirm).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText(/Type user@example.com/), 'user@example.com')
    expect(confirm).toBeEnabled()
  })

  it('an owner of a workspace cannot start deletion', async () => {
    // First match wins within one server.use call, so the override goes first.
    server.use(json('/account/profile/', { ...profile, deletion_blockers: [{ id: 'tenant-a', name: 'Alpha Corp' }] }), ...settingsHandlers())
    renderAt('/settings')
    expect(await screen.findByText(/Transfer ownership or close it/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete account' })).toBeDisabled()
  })
})

describe('onboarding and billing summary', () => {
  it('shows setup progress on the billing overview until ready', async () => {
    server.use(
      json('/workspace/overview/', OVERVIEW),
      json('/billing/summary/', OVERVIEW.current_month),
      json('/billing/cycles/', []),
    )
    renderAt('/billing')
    expect(await screen.findByText(/4 of 6 steps · 67%/)).toBeInTheDocument()
    expect(await screen.findByText('Billed')).toBeInTheDocument()
    expect(screen.getByText('Overdue')).toBeInTheDocument()
  })

  it('the resident dashboard shows their unit and current bill', async () => {
    server.use(json('/residency/', RESIDENCY), json('/bills/', page([BILL])))
    renderAt('/home', TENANT_B)
    expect(await screen.findByText('Sunrise Building A · Unit 203')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View bill' })).toHaveAttribute('href', '/bills/bill-1')
  })
})
