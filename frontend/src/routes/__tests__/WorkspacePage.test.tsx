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
  TENANT_A,
  TENANT_B,
  tenantsMeHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import type { TenantMembership } from '../../lib/tenant'
import { AppRoutes } from '../AppRoutes'

function renderWorkspace() {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/workspace']}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  setCurrentTenantId(null)
  localStorage.clear()
})

describe('WorkspacePage', () => {
  it('lists the workspaces from TenantProvider without a second fetch', async () => {
    let tenantsMeCalls = 0
    server.use(
      ...authHandlers(),
      http.get(apiUrl('/tenants/me/'), () => {
        tenantsMeCalls += 1
        return HttpResponse.json([TENANT_A, TENANT_B])
      }),
    )

    renderWorkspace()

    const list = await screen.findByRole('list', { name: 'Your workspaces' })
    expect(within(list).getByText(TENANT_A.name)).toBeInTheDocument()
    expect(within(list).getByText(TENANT_B.name)).toBeInTheDocument()
    // OWNER accent / MEMBER neutral badges, both with a text label.
    expect(within(list).getByText('OWNER')).toBeInTheDocument()
    expect(within(list).getByText('MEMBER')).toBeInTheDocument()

    // The list is the provider's one query — the page adds no fetch of its own.
    expect(tenantsMeCalls).toBe(1)
  })

  it('shows the empty state when the user has no workspaces', async () => {
    server.use(...authHandlers(), tenantsMeHandler([]))

    renderWorkspace()

    expect(
      await screen.findByText(/not a member of any workspace yet/i),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Create workspace' }),
    ).toBeInTheDocument()
  })

  it('selecting a workspace switches tenant and enters the app', async () => {
    server.use(...authHandlers(), tenantsMeHandler([TENANT_A, TENANT_B]))

    renderWorkspace()

    await userEvent.click(
      await screen.findByRole('button', { name: new RegExp(TENANT_B.name) }),
    )

    expect(
      await screen.findByRole('heading', { name: 'Team' }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(localStorage.getItem('billing.last_tenant_id')).toBe(TENANT_B.id),
    )
  })

  it('creates a workspace, selects it, and enters the app', async () => {
    const created: TenantMembership = {
      id: 'tenant-new',
      name: 'Gamma Inc',
      slug: 'gamma',
      created_at: '2026-03-01T00:00:00Z',
      is_active: true,
      role: 'OWNER',
    }
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.post(apiUrl('/tenants/'), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        expect(body).toEqual({ name: 'Gamma Inc', slug: 'gamma' })
        return HttpResponse.json(created, { status: 201 })
      }),
    )

    renderWorkspace()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Create workspace' }),
    )

    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Name'), 'Gamma Inc')
    await userEvent.type(within(dialog).getByLabelText('Slug'), 'gamma')
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Create workspace' }),
    )

    expect(
      await screen.findByRole('heading', { name: 'Team' }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(localStorage.getItem('billing.last_tenant_id')).toBe('tenant-new'),
    )
  })

  it('renders a duplicate-slug error inline on the field, not as a toast', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.post(apiUrl('/tenants/'), () =>
        HttpResponse.json(
          { slug: ['A tenant with this slug already exists.'] },
          { status: 400 },
        ),
      ),
    )

    renderWorkspace()
    await userEvent.click(
      await screen.findByRole('button', { name: 'Create workspace' }),
    )

    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Name'), 'Alpha Two')
    await userEvent.type(within(dialog).getByLabelText('Slug'), 'alpha')
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Create workspace' }),
    )

    // Inline on the slug field, and the modal stays open.
    const slug = within(dialog).getByLabelText('Slug')
    await waitFor(() => expect(slug).toHaveAttribute('aria-invalid', 'true'))
    expect(
      within(dialog).getByText('A tenant with this slug already exists.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
