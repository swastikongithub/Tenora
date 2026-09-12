import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  currentSubscriptionHandler,
  membershipsHandler,
  MEMBERS_A,
  PLATFORM_HEALTH,
  PLATFORM_STATS,
  PLATFORM_TENANTS,
  plansHandler,
  platformHealthHandler,
  platformStatsHandler,
  platformTenantsHandler,
  subscriptionFor,
  PLAN_PRO,
  TENANT_A,
  tenantsMeHandler,
  usersMeHandler,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin') {
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
    currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
    membershipsHandler(MEMBERS_A),
    plansHandler(),
    platformTenantsHandler(),
    platformStatsHandler(),
    platformHealthHandler(),
  )
})

describe('/admin — access (docs/operator-control-plane-spec.md)', () => {
  it('renders the operator overview with real aggregated data for platform staff', async () => {
    server.use(usersMeStaffHandler())
    renderAt()

    expect(
      await screen.findByRole('heading', { name: 'Platform Admin' }),
    ).toBeInTheDocument()

    const totalCard = (await screen.findByText('Total tenants')).closest(
      '.rounded-lg',
    ) as HTMLElement
    expect(within(totalCard).getByText(String(PLATFORM_STATS.total_tenants)))
      .toBeInTheDocument()

    expect(
      screen.getByRole('heading', { name: 'Status & plan distribution' }),
    ).toBeInTheDocument()

    // The system-health row (new in Phase 1).
    const webhookCard = (await screen.findByText('Unprocessed webhooks')).closest(
      '.rounded-lg',
    ) as HTMLElement
    expect(
      within(webhookCard).getByText(String(PLATFORM_HEALTH.unprocessed_webhook_events)),
    ).toBeInTheDocument()
    expect(screen.getByText(PLATFORM_HEALTH.payment_gateway)).toBeInTheDocument()

    // The cross-tenant tenant list — every seeded tenant, together.
    for (const t of PLATFORM_TENANTS) {
      expect(await screen.findByText(t.name)).toBeInTheDocument()
    }

    // The section tab strip (AdminLayout).
    expect(screen.getByRole('link', { name: 'Plans' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Billing Events' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Audit Log' })).toBeInTheDocument()
  })

  it('redirects a non-staff user away and never shows operator content', async () => {
    server.use(usersMeHandler()) // is_staff: false
    renderAt()

    expect(await screen.findByRole('heading', { name: 'Team' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Platform Admin' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Initech')).not.toBeInTheDocument()
  })

  it('also redirects a non-staff user from a nested /admin route — one shared gate', async () => {
    server.use(usersMeHandler())
    renderAt('/admin/plans')

    expect(await screen.findByRole('heading', { name: 'Team' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Platform Admin' }),
    ).not.toBeInTheDocument()
  })

  it('shows a loading gate — no premature "access denied" flash — while is_staff is unknown', async () => {
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

    const gates = await screen.findAllByText(/Loading/i)
    expect(gates.length).toBeGreaterThan(0)
    expect(screen.queryByRole('heading', { name: 'Team' })).not.toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Platform Admin' }),
    ).not.toBeInTheDocument()

    release()

    expect(
      await screen.findByRole('heading', { name: 'Platform Admin' }),
    ).toBeInTheDocument()
  })
})

describe('/admin — per-query failure isolation', () => {
  it('keeps the tenant list when stats fail, and vice versa', async () => {
    server.use(
      usersMeStaffHandler(),
      http.get(apiUrl('/platform/stats/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()

    expect(
      await screen.findByText('Couldn’t load platform statistics.'),
    ).toBeInTheDocument()
    for (const t of PLATFORM_TENANTS) {
      expect(await screen.findByText(t.name)).toBeInTheDocument()
    }
  })

  it('keeps everything else when health fails', async () => {
    server.use(
      usersMeStaffHandler(),
      http.get(apiUrl('/platform/health/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()

    expect(await screen.findByText('Couldn’t load system health.')).toBeInTheDocument()
    const totalCard = (await screen.findByText('Total tenants')).closest(
      '.rounded-lg',
    ) as HTMLElement
    expect(within(totalCard).getByText(String(PLATFORM_STATS.total_tenants)))
      .toBeInTheDocument()
  })
})

describe('/platform-admin — compatibility redirect', () => {
  it('lands on the canonical /admin surface with real content, not a second page', async () => {
    server.use(usersMeStaffHandler())
    renderAt('/platform-admin')

    expect(
      await screen.findByRole('heading', { name: 'Platform Admin' }),
    ).toBeInTheDocument()
    for (const t of PLATFORM_TENANTS) {
      expect(await screen.findByText(t.name)).toBeInTheDocument()
    }
  })

  it('redirects a non-staff user exactly like /admin does', async () => {
    server.use(usersMeHandler())
    renderAt('/platform-admin')

    expect(await screen.findByRole('heading', { name: 'Team' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Platform Admin' }),
    ).not.toBeInTheDocument()
  })
})
