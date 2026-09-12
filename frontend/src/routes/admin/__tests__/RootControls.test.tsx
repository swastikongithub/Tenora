/**
 * Phase 4 — the Root-only operator surfaces
 * (docs/operator-control-plane-spec.md §D).
 *
 * Two things are asserted throughout, and they are different claims:
 *   - a Staff-tier viewer sees none of these controls (presentation), and
 *   - the server is the boundary — a 403 is rendered as a refusal, never
 *     worked around client-side (security).
 *
 * The existing "has no role-management controls" test in UsersPage.test.tsx
 * is left exactly as written: its viewer is Staff-tier, so it keeps passing
 * and now asserts the Phase 4 rule rather than a Phase 1 absence.
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
  PLATFORM_USERS,
  PLATFORM_WEBHOOK_EVENTS,
  RAW_WEBHOOK_PAYLOAD,
  platformProcessPendingHandler,
  platformUserRolePatchErrorHandler,
  platformUserRolePatchHandler,
  platformUsersHandler,
  platformWebhookEventsHandler,
  platformWebhookRawErrorHandler,
  platformWebhookRawHandler,
  TENANT_A,
  usersMeRootHandler,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

const ROOT_USER = {
  id: 'root-1',
  email: 'root@example.com',
  is_staff: true,
  is_superuser: true,
  is_active: true,
  email_verified: true,
  date_joined: '2026-01-01T00:00:00Z',
}

const SECOND_ROOT = { ...ROOT_USER, id: 'root-2', email: 'root2@example.com' }

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

beforeEach(() => {
  server.use(...authHandlers())
})

describe('/admin/users — role controls (Root tier)', () => {
  it('renders no role controls for a Staff-tier viewer', async () => {
    server.use(usersMeStaffHandler(), platformUsersHandler())
    renderAt('/admin/users')
    await screen.findByText(PLATFORM_USERS[0].email)

    expect(
      screen.queryByRole('button', { name: 'Change roles' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/Root controls\./)).not.toBeInTheDocument()
  })

  it('renders a role control per row for a Root viewer', async () => {
    server.use(usersMeRootHandler(), platformUsersHandler([ROOT_USER, SECOND_ROOT]))
    renderAt('/admin/users')
    await screen.findByText(ROOT_USER.email)

    expect(
      await screen.findAllByRole('button', { name: 'Change roles' }),
    ).toHaveLength(2)
  })

  it('sends nothing until the dialog is confirmed', async () => {
    let patches = 0
    server.use(
      usersMeRootHandler(),
      platformUsersHandler([ROOT_USER, SECOND_ROOT]),
      http.patch(apiUrl('/platform/users/detail/'), () => {
        patches += 1
        return HttpResponse.json(SECOND_ROOT)
      }),
    )
    renderAt('/admin/users')
    const buttons = await screen.findAllByRole('button', { name: 'Change roles' })

    await userEvent.click(buttons[1])
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(patches).toBe(0)

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(patches).toBe(0)
  })

  it('sends only the flags that actually changed', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      usersMeRootHandler(),
      platformUsersHandler([ROOT_USER, SECOND_ROOT]),
      http.patch(apiUrl('/platform/users/detail/'), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...SECOND_ROOT, is_superuser: false })
      }),
    )
    renderAt('/admin/users')
    const buttons = await screen.findAllByRole('button', { name: 'Change roles' })
    await userEvent.click(buttons[1])
    await screen.findByRole('dialog')

    await userEvent.click(screen.getByRole('checkbox', { name: /Root/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Apply changes' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ is_superuser: false })
  })

  it('cannot submit with nothing changed', async () => {
    server.use(usersMeRootHandler(), platformUsersHandler([ROOT_USER, SECOND_ROOT]))
    renderAt('/admin/users')
    const buttons = await screen.findAllByRole('button', { name: 'Change roles' })
    await userEvent.click(buttons[1])
    await screen.findByRole('dialog')

    expect(screen.getByRole('button', { name: 'Apply changes' })).toBeDisabled()
  })

  it('refuses, in the dialog, a change that would remove the last root', async () => {
    let patches = 0
    server.use(
      usersMeRootHandler(),
      // One root on the page, and it is the account being edited.
      platformUsersHandler([ROOT_USER]),
      http.patch(apiUrl('/platform/users/detail/'), () => {
        patches += 1
        return HttpResponse.json(ROOT_USER)
      }),
    )
    renderAt('/admin/users')
    await userEvent.click(
      (await screen.findAllByRole('button', { name: 'Change roles' }))[0],
    )
    await screen.findByRole('dialog')

    await userEvent.click(screen.getByRole('checkbox', { name: /Root/ }))

    expect(
      await screen.findByText(/would leave no active root operator/),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply changes' })).toBeDisabled()
    expect(patches).toBe(0)
  })

  it('renders the server refusal when the backend rejects the change', async () => {
    server.use(
      usersMeRootHandler(),
      platformUsersHandler([ROOT_USER, SECOND_ROOT]),
      platformUserRolePatchErrorHandler(),
    )
    renderAt('/admin/users')
    await userEvent.click(
      (await screen.findAllByRole('button', { name: 'Change roles' }))[1],
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('checkbox', { name: /Root/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Apply changes' }))

    expect(
      await screen.findByText(/no active root operator/),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders a 403 from the server as a refusal, not a success', async () => {
    server.use(
      usersMeRootHandler(),
      platformUsersHandler([ROOT_USER, SECOND_ROOT]),
      platformUserRolePatchErrorHandler(
        'This action is restricted to root operators.',
        403,
      ),
    )
    renderAt('/admin/users')
    await userEvent.click(
      (await screen.findAllByRole('button', { name: 'Change roles' }))[1],
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('checkbox', { name: /Root/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Apply changes' }))

    expect(
      await screen.findByText('This action is restricted to root operators.'),
    ).toBeInTheDocument()
  })

  it('closes the dialog on success', async () => {
    server.use(
      usersMeRootHandler(),
      platformUsersHandler([ROOT_USER, SECOND_ROOT]),
      platformUserRolePatchHandler({ ...SECOND_ROOT, is_superuser: false }),
    )
    renderAt('/admin/users')
    await userEvent.click(
      (await screen.findAllByRole('button', { name: 'Change roles' }))[1],
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('checkbox', { name: /Root/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Apply changes' }))

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })

  it('never offers email, password or verification controls', async () => {
    server.use(usersMeRootHandler(), platformUsersHandler([ROOT_USER, SECOND_ROOT]))
    renderAt('/admin/users')
    await userEvent.click(
      (await screen.findAllByRole('button', { name: 'Change roles' }))[1],
    )
    const dialog = await screen.findByRole('dialog')

    expect(dialog.textContent).not.toMatch(/reset password/i)
    expect(
      screen.queryByRole('textbox', { name: /email/i }),
    ).not.toBeInTheDocument()
    // Exactly three toggles, and they are the three platform flags — nothing
    // touching identity or verification state is reachable from here.
    const toggles = screen.getAllByRole('checkbox')
    expect(toggles).toHaveLength(3)
    expect(
      toggles.map((t) => t.closest('label')?.querySelector('span span')?.textContent),
    ).toEqual(['Platform staff', 'Root', 'Active'])
  })

  it('never sends X-Tenant-ID on the role mutation', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      usersMeRootHandler(),
      platformUsersHandler([ROOT_USER, SECOND_ROOT]),
      http.patch(apiUrl('/platform/users/detail/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json(SECOND_ROOT)
      }),
    )
    renderAt('/admin/users')
    await userEvent.click(
      (await screen.findAllByRole('button', { name: 'Change roles' }))[1],
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('checkbox', { name: /Root/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Apply changes' }))

    await waitFor(() => expect(tenantHeader).toBeNull())
  })
})

describe('/admin/webhooks — raw payload (Root tier)', () => {
  beforeEach(() => {
    server.use(platformWebhookEventsHandler(), platformProcessPendingHandler())
  })

  it('offers no raw-payload control to a Staff-tier viewer', async () => {
    server.use(usersMeStaffHandler())
    renderAt('/admin/webhooks')
    await screen.findByText(PLATFORM_WEBHOOK_EVENTS[0].external_event_id)

    expect(screen.queryByRole('button', { name: 'View raw' })).not.toBeInTheDocument()
  })

  it('never requests the raw payload alongside the list', async () => {
    let rawRequests = 0
    server.use(
      usersMeRootHandler(),
      http.get(apiUrl('/platform/webhook-events/raw/'), () => {
        rawRequests += 1
        return HttpResponse.json({
          ...PLATFORM_WEBHOOK_EVENTS[0],
          raw_payload: RAW_WEBHOOK_PAYLOAD,
        })
      }),
    )
    renderAt('/admin/webhooks')
    await screen.findByRole('button', { name: 'View raw' })

    expect(rawRequests).toBe(0)
  })

  it('fetches and shows the payload only when a Root operator asks', async () => {
    server.use(usersMeRootHandler(), platformWebhookRawHandler())
    renderAt('/admin/webhooks')

    await userEvent.click(await screen.findByRole('button', { name: 'View raw' }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(
      await screen.findByText(/customer@example\.com/),
    ).toBeInTheDocument()
  })

  it('warns that opening the payload is recorded', async () => {
    server.use(usersMeRootHandler(), platformWebhookRawHandler())
    renderAt('/admin/webhooks')
    await userEvent.click(await screen.findByRole('button', { name: 'View raw' }))

    expect(
      await screen.findByText(/recorded in the audit log/),
    ).toBeInTheDocument()
  })

  it('shows no payload anywhere on the list itself', async () => {
    server.use(usersMeRootHandler())
    renderAt('/admin/webhooks')
    await screen.findByRole('button', { name: 'View raw' })

    expect(document.body.textContent).not.toMatch(/customer@example\.com/)
    expect(document.body.textContent).not.toMatch(/4242/)
  })

  it('renders a 403 from the raw endpoint as an error, never as content', async () => {
    server.use(usersMeRootHandler(), platformWebhookRawErrorHandler(403))
    renderAt('/admin/webhooks')
    await userEvent.click(await screen.findByRole('button', { name: 'View raw' }))

    expect(
      await screen.findByText('Couldn’t load the raw payload.'),
    ).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/customer@example\.com/)
  })

  it('never sends X-Tenant-ID on the raw read', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      usersMeRootHandler(),
      http.get(apiUrl('/platform/webhook-events/raw/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json({
          ...PLATFORM_WEBHOOK_EVENTS[0],
          raw_payload: RAW_WEBHOOK_PAYLOAD,
        })
      }),
    )
    renderAt('/admin/webhooks')
    await userEvent.click(await screen.findByRole('button', { name: 'View raw' }))

    await waitFor(() => expect(tenantHeader).toBeNull())
  })
})
