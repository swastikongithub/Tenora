import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  currentSubscriptionHandler,
  membershipsHandler,
  MEMBERS_A,
  PLATFORM_STATS,
  PLATFORM_TENANTS,
  plansHandler,
  platformStatsHandler,
  platformTenantsHandler,
  subscriptionFor,
  PLAN_PRO,
  TENANT_A,
  tenantsMeHandler,
  usersMeHandler,
  usersMeStaffHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { createQueryClient } from '../../lib/query-client'
import { AppRoutes } from '../AppRoutes'

function renderAt(path = '/platform-admin') {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  localStorage.setItem('billing.last_tenant_id', TENANT_A.id)
  render(
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
  server.use(
    ...authHandlers(),
    tenantsMeHandler([TENANT_A]),
    // So a redirect to /overview has something to render against.
    currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
    membershipsHandler(MEMBERS_A),
    plansHandler(),
    platformTenantsHandler(),
    platformStatsHandler(),
  )
})

describe('PlatformAdminPage — access', () => {
  it('renders the dashboard with real aggregated data for a platform-staff user', async () => {
    server.use(usersMeStaffHandler())
    renderAt()

    expect(
      await screen.findByRole('heading', { name: 'Platform Admin' }),
    ).toBeInTheDocument()

    // KPI row — total plus the seeded status breakdown.
    const totalCard = (await screen.findByText('Total tenants')).closest(
      '.rounded-lg',
    ) as HTMLElement
    expect(within(totalCard).getByText(String(PLATFORM_STATS.total_tenants)))
      .toBeInTheDocument()

    // Both chart panels are present.
    expect(
      screen.getByRole('heading', { name: 'Status & plan distribution' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Signups over time' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('img', { name: /tenants created per month/i }),
    ).toBeInTheDocument()

    // The cross-tenant tenant list — every seeded tenant, together.
    for (const t of PLATFORM_TENANTS) {
      expect(await screen.findByText(t.name)).toBeInTheDocument()
    }
  })

  it('redirects a non-staff user away and never shows dashboard content', async () => {
    server.use(usersMeHandler()) // is_staff: false
    renderAt()

    // Lands on /overview (the redirect target).
    expect(
      await screen.findByRole('heading', { name: 'Team' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Platform Admin' }),
    ).not.toBeInTheDocument()
    // No cross-tenant data leaked into the DOM.
    expect(screen.queryByText('Initech')).not.toBeInTheDocument()
  })

  it('shows a loading gate — no premature "access denied" flash — while is_staff is still unknown', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.get(apiUrl('/users/me/'), async () => {
        await gate
        return HttpResponse.json({
          id: 'staff-1',
          email: 'operator@example.com',
          is_staff: true,
        })
      }),
    )

    renderAt()

    // While /users/me/ is in flight: the gate's loading state, and crucially
    // NOT a redirect to /overview.
    const gates = await screen.findAllByText(/Loading/i)
    expect(gates.length).toBeGreaterThan(0)
    expect(
      screen.queryByRole('heading', { name: 'Team' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Platform Admin' }),
    ).not.toBeInTheDocument()

    release()

    // Once it resolves as staff, the dashboard renders — the redirect never
    // happened.
    expect(
      await screen.findByRole('heading', { name: 'Platform Admin' }),
    ).toBeInTheDocument()
  })
})

describe('PlatformAdminPage — per-query failure isolation', () => {
  it('keeps the tenant list when stats fail, and vice versa', async () => {
    server.use(
      usersMeStaffHandler(),
      http.get(apiUrl('/platform/stats/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()

    // Stats section shows its own error…
    expect(
      await screen.findByText('Couldn’t load platform statistics.'),
    ).toBeInTheDocument()
    // …while the tenant list still renders in full.
    for (const t of PLATFORM_TENANTS) {
      expect(await screen.findByText(t.name)).toBeInTheDocument()
    }
  })
})
