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
import { getCurrentTenantId, setCurrentTenantId } from '../../lib/tenant'
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

    // TENANT_B is a MEMBER (resident) workspace: since property billing a
    // resident enters on their own dashboard, not the owner's overview.
    expect(
      await screen.findByRole('heading', { name: /^Welcome/ }),
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

describe('WorkspacePage — leaving and closing without switching first', () => {
  it('leaves the workspace whose row was clicked, not the active one', async () => {
    // Active workspace is A; the user leaves B from B's own row.
    setCurrentTenantId(TENANT_A.id)
    let leaveTarget: string | null = null
    let remaining = [TENANT_A, TENANT_B]
    server.use(
      ...authHandlers(),
      http.get(apiUrl('/tenants/me/'), () => HttpResponse.json(remaining)),
      http.post(apiUrl('/memberships/leave/'), ({ request }) => {
        leaveTarget = request.headers.get('X-Tenant-ID')
        remaining = [TENANT_A]
        return new HttpResponse(null, { status: 200 })
      }),
    )

    renderWorkspace()
    const list = await screen.findByRole('list', { name: 'Your workspaces' })
    const betaRow = within(list).getByText('Beta LLC').closest('li')!
    await userEvent.click(within(betaRow).getByRole('button', { name: 'Leave' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Leave Beta LLC?')
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Leave workspace' }),
    )

    await waitFor(() => expect(leaveTarget).toBe(TENANT_B.id))
    // The active workspace is untouched and the list drops only Beta.
    expect(getCurrentTenantId()).toBe(TENANT_A.id)
    await waitFor(() =>
      expect(within(list).queryByText('Beta LLC')).not.toBeInTheDocument(),
    )
    expect(within(list).getByText('Alpha Corp')).toBeInTheDocument()
  })

  it('offers Close only for owned workspaces and requires the name typed', async () => {
    setCurrentTenantId(TENANT_B.id)
    let closeTarget: string | null = null
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A, TENANT_B]),
      http.post(apiUrl('/workspace/close/'), ({ request }) => {
        closeTarget = request.headers.get('X-Tenant-ID')
        return new HttpResponse(null, { status: 200 })
      }),
    )

    renderWorkspace()
    const alphaRow = (await screen.findByText('Alpha Corp')).closest('li')!
    const list = await screen.findByRole('list', { name: 'Your workspaces' })
    const betaRow = within(list).getByText('Beta LLC').closest('li')!
    // Beta is a MEMBER row — no Close offered there.
    expect(within(betaRow).queryByRole('button', { name: 'Close' })).toBeNull()

    await userEvent.click(within(alphaRow).getByRole('button', { name: 'Close' }))
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Close workspace' })
    expect(confirm).toBeDisabled()

    await userEvent.type(
      within(dialog).getByLabelText('Type Alpha Corp to confirm'),
      'Alpha Corp',
    )
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)
    await waitFor(() => expect(closeTarget).toBe(TENANT_A.id))
  })

  it('surfaces a refused leave and keeps the membership listed', async () => {
    setCurrentTenantId(TENANT_A.id)
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A, TENANT_B]),
      http.post(apiUrl('/memberships/leave/'), () =>
        HttpResponse.json(
          {
            detail:
              "You are this workspace's only owner. Transfer ownership to a resident, or close the workspace, before leaving.",
            code: 'last_owner',
          },
          { status: 409 },
        ),
      ),
    )

    renderWorkspace()
    const list = await screen.findByRole('list', { name: 'Your workspaces' })
    const alphaRow = within(list).getByText('Alpha Corp').closest('li')!
    await userEvent.click(within(alphaRow).getByRole('button', { name: 'Leave' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Leave workspace' }),
    )

    expect(await within(dialog).findByText(/only owner/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(within(list).getByText('Alpha Corp')).toBeInTheDocument()
  })
})
