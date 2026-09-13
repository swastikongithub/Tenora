/**
 * Platform-admin property billing: Staff sees the global roll-up and the
 * workspace drill-down; only a Root viewer is offered the promote/demote control
 * (refused server-side for anyone else regardless).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  TENANT_A,
  tenantsMeHandler,
  usersMeRootHandler,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AGING, BILL, OVERVIEW, json, page, shellHandlers } from '../../../test/property-fixtures'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path: string) {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  localStorage.setItem('billing.last_tenant_id', TENANT_A.id)
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

const WORKSPACE_ROW = {
  id: 'tenant-a', name: 'Alpha Corp', slug: 'alpha', is_active: true, closed_at: null, owners: ['owner@alpha.test'],
  subscription_status: 'ACTIVE', plan_name: 'Pro', properties: 1, residents: 2, bills: 1, billed_cents: 1378000,
  collected_cents: 0, outstanding_cents: 1378000, overdue_bills: 1, overdue_cents: 1378000,
}

const DETAIL = {
  id: 'tenant-a', name: 'Alpha Corp', slug: 'alpha', is_active: true, closed_at: null,
  memberships: [
    { id: 'm-owner', email: 'owner@alpha.test', role: 'OWNER', status: 'ACTIVE' },
    { id: 'm-res', email: 'rahul@alpha.test', role: 'MEMBER', status: 'ACTIVE' },
  ],
  subscription: { status: 'ACTIVE', plan: { name: 'Pro' } },
  properties: [],
  residents: [],
  aging: AGING,
  current_period: OVERVIEW.current_month,
}

beforeEach(() => {
  server.use(
    ...authHandlers(),
    ...shellHandlers(),
    tenantsMeHandler([TENANT_A]),
    json('/platform/property-billing/summary/', {
      workspaces: 1, active_subscriptions: 1, properties: 1, residents: 2, total_bills: 1, total_billed_cents: 1378000,
      total_collected_cents: 0, total_outstanding_cents: 1378000, total_overdue_cents: 1378000, total_payments: 0,
      total_payments_cents: 0, electricity_units: '160.000', current_period: OVERVIEW.current_month,
    }),
    json('/platform/property-billing/workspaces/', page([WORKSPACE_ROW])),
    json('/platform/property-billing/bills/', page([{ ...BILL, tenant_id: 'tenant-a', tenant_name: 'Alpha Corp' }])),
    json('/platform/property-billing/workspaces/detail/', DETAIL),
  )
})

describe('/admin/property-billing', () => {
  it('shows the global roll-up, workspaces and bills to Staff', async () => {
    server.use(usersMeStaffHandler())
    renderAt('/admin/property-billing')
    expect(await screen.findByRole('heading', { name: 'Property billing' })).toBeInTheDocument()
    const workspaces = await screen.findByRole('table', { name: 'Workspaces with property billing' })
    expect(within(workspaces).getByText('owner@alpha.test')).toBeInTheDocument()
    const bills = await screen.findByRole('table', { name: 'All property bills' })
    expect(within(bills).getByText('Rahul Sharma')).toBeInTheDocument()
  })

  it('offers no role control to a Staff-tier viewer', async () => {
    server.use(usersMeStaffHandler())
    renderAt('/admin/property-billing/tenant-a')
    expect(await screen.findByText('rahul@alpha.test')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Promote to owner' })).not.toBeInTheDocument()
  })

  it('lets a Root viewer promote a resident, sending only the role', async () => {
    let body: unknown = null
    let url = ''
    server.use(
      usersMeRootHandler(),
      http.patch(apiUrl('/platform/memberships/detail/'), async ({ request }) => {
        url = request.url
        body = await request.json()
        return HttpResponse.json({ id: 'm-res', role: 'OWNER' })
      }),
    )
    renderAt('/admin/property-billing/tenant-a')
    await userEvent.click(await screen.findByRole('button', { name: 'Promote to owner' }))
    await waitFor(() => expect(body).toEqual({ role: 'OWNER' }))
    expect(url).toContain('id=m-res')
  })
})
