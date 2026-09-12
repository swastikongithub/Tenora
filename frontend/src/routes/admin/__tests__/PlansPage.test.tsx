import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
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
  platformPlanCreateErrorHandler,
  platformPlansHandler,
  TENANT_A,
  tenantsMeHandler,
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

// `tenantsMeHandler` is not decoration: without it the navbar's tenant
// switcher fails its own query and renders its own "Retry" button, so a test
// that clicks a page-level Retry by role intermittently finds two. Stubbing
// the shell's query makes that deterministic without changing what any
// assertion below claims.
beforeEach(() => {
  server.use(...authHandlers(), tenantsMeHandler([TENANT_A]), platformPlansHandler())
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

describe('PlansPage — create (Phase 3)', () => {
  it('sends nothing until the form is submitted', async () => {
    let posts = 0
    server.use(
      http.post(apiUrl('/platform/plans/'), () => {
        posts += 1
        return HttpResponse.json(PLATFORM_PLANS[0], { status: 201 })
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)

    await userEvent.click(screen.getByRole('button', { name: 'New plan' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(posts).toBe(0)

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(posts).toBe(0)
  })

  it('posts the form values and closes on success', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post(apiUrl('/platform/plans/'), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(PLATFORM_PLANS[0], { status: 201 })
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)

    await userEvent.click(screen.getByRole('button', { name: 'New plan' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Scale')
    await userEvent.type(screen.getByLabelText('Code'), 'SCALE')
    await userEvent.type(screen.getByLabelText('Price (minor units)'), '19900')
    await userEvent.click(screen.getByRole('button', { name: 'Create plan' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({
      name: 'Scale',
      code: 'SCALE',
      price_cents: 19900,
      currency: 'USD',
      interval: 'MONTHLY',
    })
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })

  it('sends price as integer minor units, never a float', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post(apiUrl('/platform/plans/'), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(PLATFORM_PLANS[0], { status: 201 })
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)

    await userEvent.click(screen.getByRole('button', { name: 'New plan' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Scale')
    await userEvent.type(screen.getByLabelText('Code'), 'SCALE')
    await userEvent.type(screen.getByLabelText('Price (minor units)'), '2900')
    await userEvent.click(screen.getByRole('button', { name: 'Create plan' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(Number.isInteger((body as Record<string, unknown>).price_cents)).toBe(
      true,
    )
  })

  it('keeps the form open and shows the field error the server returned', async () => {
    server.use(
      platformPlanCreateErrorHandler('code', 'A plan with this code already exists.'),
    )
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)

    await userEvent.click(screen.getByRole('button', { name: 'New plan' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Pro')
    await userEvent.type(screen.getByLabelText('Code'), 'PRO')
    await userEvent.type(screen.getByLabelText('Price (minor units)'), '100')
    await userEvent.click(screen.getByRole('button', { name: 'Create plan' }))

    expect(
      await screen.findByText('A plan with this code already exists.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('will not submit an incomplete form', async () => {
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)

    await userEvent.click(screen.getByRole('button', { name: 'New plan' }))
    expect(screen.getByRole('button', { name: 'Create plan' })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Name'), 'Scale')
    expect(screen.getByRole('button', { name: 'Create plan' })).toBeDisabled()
  })

  it('never sends X-Tenant-ID on the create call', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      http.post(apiUrl('/platform/plans/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json(PLATFORM_PLANS[0], { status: 201 })
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_PLANS[0].name)

    await userEvent.click(screen.getByRole('button', { name: 'New plan' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Scale')
    await userEvent.type(screen.getByLabelText('Code'), 'SCALE')
    await userEvent.type(screen.getByLabelText('Price (minor units)'), '100')
    await userEvent.click(screen.getByRole('button', { name: 'Create plan' }))

    await waitFor(() => expect(tenantHeader).toBeNull())
  })
})
