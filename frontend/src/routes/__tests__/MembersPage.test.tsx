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
  MEMBERS_A,
  MEMBERS_B,
  membershipsByTenantHandler,
  membershipsHandler,
  TENANT_A,
  TENANT_B,
  tenantsMeHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import { AppRoutes } from '../AppRoutes'

/** Render the app at /members. `asTenant` picks which tenant is active (and so
 *  the caller's role): TENANT_A → OWNER, TENANT_B → MEMBER. */
function renderMembers(asTenant = TENANT_A) {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  localStorage.setItem('billing.last_tenant_id', asTenant.id)
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/members']}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  setCurrentTenantId(null)
  localStorage.clear()
  sessionStorage.clear()
})

describe('MembersPage — list', () => {
  it('renders every member with role badge and joined date (OWNER sees Add member)', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A, TENANT_B]),
      membershipsHandler(MEMBERS_A),
    )
    renderMembers(TENANT_A)

    await screen.findByText('owner@alpha.test')
    const table = screen.getByRole('table', { name: 'Workspace members' })
    expect(within(table).getByText('ada@alpha.test')).toBeInTheDocument()
    expect(within(table).getByText('OWNER')).toBeInTheDocument()
    expect(within(table).getByText('MEMBER')).toBeInTheDocument()
    // A human-formatted joined date (locale-dependent ordering), not raw ISO.
    expect(within(table).queryByText(/2026-01/)).not.toBeInTheDocument()
    expect(
      within(table).getAllByText(
        (t) => /\bJan\b/.test(t) && t.includes('2026'),
      ),
    ).toHaveLength(2)

    expect(
      screen.getByRole('button', { name: 'Add member' }),
    ).toBeInTheDocument()
  })

  it('hides Add member for a MEMBER but still shows the list', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A, TENANT_B]),
      membershipsHandler(MEMBERS_B),
    )
    renderMembers(TENANT_B)

    expect(await screen.findByText('owner@beta.test')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Add member' }),
    ).not.toBeInTheDocument()
  })

  it('shows a skeleton while loading', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/memberships/'), async () => {
        await new Promise((r) => setTimeout(r, 40))
        return HttpResponse.json(MEMBERS_A)
      }),
    )
    renderMembers(TENANT_A)

    expect(await screen.findByText('Loading members')).toBeInTheDocument()
    expect(await screen.findByText('owner@alpha.test')).toBeInTheDocument()
  })

  it('shows a retry panel on error and recovers', async () => {
    let attempts = 0
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/memberships/'), () => {
        attempts += 1
        return attempts === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(MEMBERS_A)
      }),
    )
    renderMembers(TENANT_A)

    await userEvent.click(await screen.findByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('owner@alpha.test')).toBeInTheDocument()
  })

  it('treats an empty list as an error, not a cheerful empty state', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      membershipsHandler([]),
    )
    renderMembers(TENANT_A)

    expect(
      await screen.findByText(/that shouldn.t happen/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})

describe('MembersPage — add member', () => {
  async function openModal() {
    await userEvent.click(
      await screen.findByRole('button', { name: 'Add member' }),
    )
    return screen.findByRole('dialog', { name: 'Add member' })
  }

  it('has no role field anywhere in the form', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      membershipsHandler(MEMBERS_A),
    )
    renderMembers(TENANT_A)
    const dialog = await openModal()

    expect(within(dialog).queryByLabelText(/role/i)).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('combobox')).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText('Email')).toBeInTheDocument()
  })

  it('adds a member, closes the modal, and the new member appears', async () => {
    let listCall = 0
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/memberships/'), () => {
        listCall += 1
        return HttpResponse.json(
          listCall === 1
            ? MEMBERS_A
            : [
                ...MEMBERS_A,
                {
                  id: 'm-a3',
                  email: 'new@alpha.test',
                  role: 'MEMBER',
                  created_at: '2026-03-01T00:00:00Z',
                },
              ],
        )
      }),
      http.post(apiUrl('/memberships/'), async ({ request }) => {
        expect(await request.json()).toEqual({ email: 'new@alpha.test' })
        return HttpResponse.json(
          {
            id: 'm-a3',
            email: 'new@alpha.test',
            role: 'MEMBER',
            created_at: '2026-03-01T00:00:00Z',
          },
          { status: 201 },
        )
      }),
    )
    renderMembers(TENANT_A)
    const dialog = await openModal()

    await userEvent.type(
      within(dialog).getByLabelText('Email'),
      'new@alpha.test',
    )
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Add member' }),
    )

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(await screen.findByText('new@alpha.test')).toBeInTheDocument()
  })

  it('shows a duplicate error inline on the email field and keeps the modal open', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      membershipsHandler(MEMBERS_A),
      http.post(apiUrl('/memberships/'), () =>
        HttpResponse.json(
          { email: ['This user is already a member of this tenant.'] },
          { status: 400 },
        ),
      ),
    )
    renderMembers(TENANT_A)
    const dialog = await openModal()

    const email = within(dialog).getByLabelText('Email')
    await userEvent.type(email, 'ada@alpha.test')
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Add member' }),
    )

    await waitFor(() => expect(email).toHaveAttribute('aria-invalid', 'true'))
    expect(
      within(dialog).getByText(
        'This user is already a member of this tenant.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(email).toHaveValue('ada@alpha.test')
  })

  it('shows the unknown-email 404 message inline on the field', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      membershipsHandler(MEMBERS_A),
      http.post(apiUrl('/memberships/'), () =>
        HttpResponse.json(
          { detail: 'No user with this email exists.' },
          { status: 404 },
        ),
      ),
    )
    renderMembers(TENANT_A)
    const dialog = await openModal()

    await userEvent.type(
      within(dialog).getByLabelText('Email'),
      'nobody@nowhere.test',
    )
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Add member' }),
    )

    expect(
      await within(dialog).findByText('No user with this email exists.'),
    ).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Email')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  })

  it('handles a 403 (stale MEMBER render) with a form-level alert, not a crash', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      membershipsHandler(MEMBERS_A),
      http.post(apiUrl('/memberships/'), () =>
        HttpResponse.json(
          { detail: 'You do not have permission to perform this action.' },
          { status: 403 },
        ),
      ),
    )
    renderMembers(TENANT_A)
    const dialog = await openModal()

    await userEvent.type(
      within(dialog).getByLabelText('Email'),
      'someone@alpha.test',
    )
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Add member' }),
    )

    expect(
      await within(dialog).findByText(/don.t have permission to add members/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('MembersPage — tenant isolation', () => {
  it('switching tenant refetches the new tenant’s members', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A, TENANT_B]),
      membershipsByTenantHandler({
        [TENANT_A.id]: MEMBERS_A,
        [TENANT_B.id]: MEMBERS_B,
      }),
    )
    renderMembers(TENANT_A)

    expect(await screen.findByText('ada@alpha.test')).toBeInTheDocument()

    // Switch via the real navbar switcher.
    await userEvent.click(
      screen.getByRole('button', { name: new RegExp(TENANT_A.name) }),
    )
    await userEvent.click(
      await screen.findByRole('menuitemradio', {
        name: new RegExp(TENANT_B.name),
      }),
    )

    expect(await screen.findByText('owner@beta.test')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByText('ada@alpha.test')).not.toBeInTheDocument(),
    )
  })
})
