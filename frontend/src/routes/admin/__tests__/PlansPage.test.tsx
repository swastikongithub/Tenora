import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  paginated,
  PLATFORM_PLANS,
  platformPlansHandler,
  TENANT_A,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin/plans') {
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

beforeEach(() => {
  server.use(...authHandlers(), platformPlansHandler())
  server.use(usersMeStaffHandler())
})

describe('PlansPage', () => {
  it('shows a loading state, then every plan including archived ones', async () => {
    renderAt()

    expect(await screen.findByText('Loading plans')).toBeInTheDocument()

    for (const p of PLATFORM_PLANS) {
      expect(await screen.findByText(p.name)).toBeInTheDocument()
    }
    // Archived — unlike the tenant-facing plan list, which never shows this
    // (also appears as a filter <option>, hence getAllByText).
    expect(screen.getAllByText('Archived').length).toBeGreaterThan(0)
  })

  it('shows an error state with a working retry', async () => {
    let calls = 0
    server.use(
      http.get(apiUrl('/platform/plans/'), () => {
        calls += 1
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(paginated(PLATFORM_PLANS))
      }),
    )
    renderAt()

    expect(await screen.findByText('Couldn’t load plans.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(PLATFORM_PLANS[0].name)).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    server.use(platformPlansHandler([]))
    renderAt()

    expect(
      await screen.findByText('No plans match these filters.'),
    ).toBeInTheDocument()
  })

  it('filters by search', async () => {
    let seenSearch: string | null = null
    server.use(
      http.get(apiUrl('/platform/plans/'), ({ request }) => {
        seenSearch = new URL(request.url).searchParams.get('search')
        return HttpResponse.json(paginated(PLATFORM_PLANS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)

    await userEvent.type(screen.getByLabelText('Search'), 'legacy')
    expect(seenSearch).toBe('legacy')
  })

  it('never sends X-Tenant-ID', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/plans/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json(paginated(PLATFORM_PLANS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)
    expect(tenantHeader).toBeNull()
  })
})
