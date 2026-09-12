/**
 * Phase 5 — the Root-only tenant suspend / reactivate control
 * (docs/operator-control-plane-spec.md §D, master plan §5.5).
 *
 * The same two claims as the other Root surfaces, kept apart on purpose: a
 * Staff-tier viewer sees no control (presentation), and a refusal from the
 * server is rendered as a refusal (security).
 *
 * Plus one claim specific to this phase: the UI must never suggest that
 * suspending a workspace changes billing, because it does not.
 */

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
  PLATFORM_TENANT_DETAIL,
  PLATFORM_TENANTS,
  platformPlansHandler,
  platformTenantDetailHandler,
  platformTenantPatchErrorHandler,
  platformTenantsHandler,
  TENANT_A,
  usersMeRootHandler,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

const SUSPENDED_DETAIL = { ...PLATFORM_TENANT_DETAIL, is_active: false }

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

const DETAIL_PATH = `/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`

beforeEach(() => {
  server.use(...authHandlers(), platformPlansHandler())
})

describe('/admin/tenants — workspace status column', () => {
  it('distinguishes a suspended workspace from a subscription status', async () => {
    server.use(usersMeStaffHandler(), platformTenantsHandler())
    renderAt('/admin/tenants')
    await screen.findByText(PLATFORM_TENANTS[0].name)

    // PLATFORM_TENANTS[2] is suspended and has no subscription: both facts
    // render, neither collapses into the other. ("No subscription" also
    // appears as a filter <option>, hence getAllByText.)
    expect(screen.getByText('Suspended')).toBeInTheDocument()
    expect(screen.getAllByText('No subscription').length).toBeGreaterThan(0)
    // Exactly one row is suspended, and it is the one whose fixture says so —
    // the badge reads `is_active`, not the subscription column beside it.
    expect(screen.getAllByText('Suspended')).toHaveLength(1)
  })
})

describe('/admin/tenants/:id — suspend control (Root tier)', () => {
  it('offers no suspend control to a Staff-tier viewer', async () => {
    server.use(usersMeStaffHandler(), platformTenantDetailHandler())
    renderAt(DETAIL_PATH)
    await screen.findByRole('heading', { name: PLATFORM_TENANT_DETAIL.name })

    expect(
      screen.queryByRole('button', { name: 'Suspend workspace' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/Workspace access/)).not.toBeInTheDocument()
  })

  it('offers the control to a Root viewer', async () => {
    server.use(usersMeRootHandler(), platformTenantDetailHandler())
    renderAt(DETAIL_PATH)
    await screen.findByRole('heading', { name: PLATFORM_TENANT_DETAIL.name })

    expect(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    ).toBeInTheDocument()
  })

  it('offers reactivate, not suspend, for an already-suspended tenant', async () => {
    server.use(usersMeRootHandler(), platformTenantDetailHandler(SUSPENDED_DETAIL))
    renderAt(DETAIL_PATH)
    await screen.findByRole('heading', { name: PLATFORM_TENANT_DETAIL.name })

    expect(
      await screen.findByRole('button', { name: 'Reactivate workspace' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Suspend workspace' }),
    ).not.toBeInTheDocument()
  })

  it('shows a suspended tenant as suspended, with an explanation', async () => {
    server.use(usersMeStaffHandler(), platformTenantDetailHandler(SUSPENDED_DETAIL))
    renderAt(DETAIL_PATH)
    await screen.findByRole('heading', { name: PLATFORM_TENANT_DETAIL.name })

    expect(screen.getByText('Suspended')).toBeInTheDocument()
    expect(
      screen.getByText(/billing is untouched and the subscription is unchanged/),
    ).toBeInTheDocument()
  })

  it('sends nothing until the confirm dialog is accepted', async () => {
    let patches = 0
    server.use(
      usersMeRootHandler(),
      platformTenantDetailHandler(),
      http.patch(apiUrl('/platform/tenants/detail/'), () => {
        patches += 1
        return HttpResponse.json(SUSPENDED_DETAIL)
      }),
    )
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    )

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(patches).toBe(0)

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(patches).toBe(0)
  })

  it('sends is_active false when confirmed, and nothing else', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      usersMeRootHandler(),
      platformTenantDetailHandler(),
      http.patch(apiUrl('/platform/tenants/detail/'), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(SUSPENDED_DETAIL)
      }),
    )
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Suspend' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ is_active: false })
  })

  it('sends is_active true when reactivating', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      usersMeRootHandler(),
      platformTenantDetailHandler(SUSPENDED_DETAIL),
      http.patch(apiUrl('/platform/tenants/detail/'), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(PLATFORM_TENANT_DETAIL)
      }),
    )
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Reactivate workspace' }),
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Reactivate' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ is_active: true })
  })

  it('names how many accounts a suspension affects', async () => {
    server.use(usersMeRootHandler(), platformTenantDetailHandler())
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    )
    const dialog = await screen.findByRole('dialog')

    const count = PLATFORM_TENANT_DETAIL.memberships.length
    const phrase = count === 1 ? '1 account' : `${count} accounts`
    expect(dialog.textContent).toContain(phrase)
  })

  it('states plainly that no billing state changes', async () => {
    server.use(usersMeRootHandler(), platformTenantDetailHandler())
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    )
    const dialog = await screen.findByRole('dialog')

    expect(dialog.textContent).toMatch(
      /No subscription, invoice or gateway state changes/,
    )
  })

  it('renders a 403 from the server as a refusal and stays open', async () => {
    server.use(
      usersMeRootHandler(),
      platformTenantDetailHandler(),
      platformTenantPatchErrorHandler(),
    )
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Suspend' }))

    expect(
      await screen.findByText('This action is restricted to root operators.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('closes the dialog on success', async () => {
    server.use(
      usersMeRootHandler(),
      platformTenantDetailHandler(),
      http.patch(apiUrl('/platform/tenants/detail/'), () =>
        HttpResponse.json(SUSPENDED_DETAIL),
      ),
    )
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Suspend' }))

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })

  it('never sends X-Tenant-ID on the suspension call', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      usersMeRootHandler(),
      platformTenantDetailHandler(),
      http.patch(apiUrl('/platform/tenants/detail/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json(SUSPENDED_DETAIL)
      }),
    )
    renderAt(DETAIL_PATH)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Suspend workspace' }),
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Suspend' }))

    await waitFor(() => expect(tenantHeader).toBeNull())
  })
})
