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
  PLATFORM_PLANS,
  platformPlanDetailHandler,
  platformPlanPatchErrorHandler,
  platformPlanSyncErrorHandler,
  platformPlanSyncHandler,
  TENANT_A,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
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

beforeEach(() => {
  server.use(...authHandlers())
  server.use(usersMeStaffHandler())
})

describe('PlanDetailPage', () => {
  it('shows the plan, including external_plan_id, not shown on the tenant-facing plan list', async () => {
    server.use(platformPlanDetailHandler(PLATFORM_PLANS[0]))
    renderAt(`/admin/plans/${PLATFORM_PLANS[0].id}`)

    expect(await screen.findByRole('heading', { name: 'Pro' })).toBeInTheDocument()
    expect(screen.getByText('ext_plan_pro')).toBeInTheDocument()
  })

  it('shows a not-synced message when external_plan_id is null', async () => {
    server.use(platformPlanDetailHandler(PLATFORM_PLANS[1]))
    renderAt(`/admin/plans/${PLATFORM_PLANS[1].id}`)

    expect(
      await screen.findByText('Not synced to the payment gateway yet'),
    ).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(
      http.get(apiUrl('/platform/plans/detail/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt(`/admin/plans/${PLATFORM_PLANS[0].id}`)
    expect(await screen.findByText('Couldn’t load this plan.')).toBeInTheDocument()
  })
})

describe('PlanDetailPage — operator actions (Phase 3)', () => {
  const SYNCED = PLATFORM_PLANS[0] // external_plan_id: 'ext_plan_pro'
  const UNSYNCED = PLATFORM_PLANS[1] // external_plan_id: null

  it('offers edit, sync and archive for an unsynced plan', async () => {
    server.use(platformPlanDetailHandler(UNSYNCED))
    renderAt(`/admin/plans/${UNSYNCED.id}`)
    await screen.findByRole('heading', { name: UNSYNCED.name })

    expect(screen.getByRole('button', { name: 'Edit plan' })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Sync to gateway' }),
    ).toBeInTheDocument()
    // This fixture is already archived, so the toggle offers the reverse.
    expect(
      screen.getByRole('button', { name: 'Restore plan' }),
    ).toBeInTheDocument()
  })

  it('does not offer sync once the plan already has an external plan id', async () => {
    server.use(platformPlanDetailHandler(SYNCED))
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    expect(
      screen.queryByRole('button', { name: 'Sync to gateway' }),
    ).not.toBeInTheDocument()
  })

  it('disables the locked fields in the edit form for a synced plan', async () => {
    server.use(platformPlanDetailHandler(SYNCED))
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Edit plan' }))
    await screen.findByRole('dialog')

    expect(screen.getByLabelText('Name')).toBeEnabled()
    expect(screen.getByLabelText('Code')).toBeDisabled()
    expect(screen.getByLabelText('Price (minor units)')).toBeDisabled()
    expect(screen.getByLabelText('Currency')).toBeDisabled()
    expect(screen.getByLabelText('Interval')).toBeDisabled()
  })

  it('leaves every field editable for an unsynced plan', async () => {
    server.use(platformPlanDetailHandler(UNSYNCED))
    renderAt(`/admin/plans/${UNSYNCED.id}`)
    await screen.findByRole('heading', { name: UNSYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Edit plan' }))
    await screen.findByRole('dialog')

    expect(screen.getByLabelText('Code')).toBeEnabled()
    expect(screen.getByLabelText('Price (minor units)')).toBeEnabled()
    expect(screen.getByLabelText('Currency')).toBeEnabled()
    expect(screen.getByLabelText('Interval')).toBeEnabled()
  })

  it('saves an edit and closes the form', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      platformPlanDetailHandler(SYNCED),
      http.patch(apiUrl('/platform/plans/detail/'), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...SYNCED, name: 'Pro (renamed)' })
      }),
    )
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Edit plan' }))
    const nameInput = await screen.findByLabelText('Name')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'Pro (renamed)')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ name: 'Pro (renamed)' })
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })

  it('shows the server error for a locked field and keeps the form open', async () => {
    server.use(
      platformPlanDetailHandler(SYNCED),
      platformPlanPatchErrorHandler(
        'price_cents',
        'These fields are locked once the plan is synced to the payment gateway: price_cents.',
      ),
    )
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Edit plan' }))
    const nameInput = await screen.findByLabelText('Name')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'Anything')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText(/locked once the plan is synced/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('archives only after the confirm dialog is accepted', async () => {
    let patches = 0
    server.use(
      platformPlanDetailHandler(SYNCED),
      http.patch(apiUrl('/platform/plans/detail/'), () => {
        patches += 1
        return HttpResponse.json({ ...SYNCED, is_active: false })
      }),
    )
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Archive plan' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(patches).toBe(0)

    await userEvent.click(screen.getByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(patches).toBe(1))
  })

  it('does not archive when the confirm dialog is cancelled', async () => {
    let patches = 0
    server.use(
      platformPlanDetailHandler(SYNCED),
      http.patch(apiUrl('/platform/plans/detail/'), () => {
        patches += 1
        return HttpResponse.json(SYNCED)
      }),
    )
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Archive plan' }))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(patches).toBe(0)
  })

  it('syncs only after the confirm dialog is accepted, and reports the result', async () => {
    let syncs = 0
    server.use(
      platformPlanDetailHandler(UNSYNCED),
      http.post(apiUrl('/platform/plans/sync/'), () => {
        syncs += 1
        return HttpResponse.json({
          ...UNSYNCED,
          external_plan_id: 'ext_plan_legacy',
          created: true,
        })
      }),
    )
    renderAt(`/admin/plans/${UNSYNCED.id}`)
    await screen.findByRole('heading', { name: UNSYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Sync to gateway' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(syncs).toBe(0)

    await userEvent.click(screen.getByRole('button', { name: 'Sync now' }))
    await waitFor(() => expect(syncs).toBe(1))
    expect(
      await screen.findByText(/Synced — gateway plan ext_plan_legacy\./),
    ).toBeInTheDocument()
  })

  it('reports an already-synced no-op honestly', async () => {
    server.use(
      platformPlanDetailHandler(UNSYNCED),
      platformPlanSyncHandler({ ...UNSYNCED, external_plan_id: 'ext_x' }, false),
    )
    renderAt(`/admin/plans/${UNSYNCED.id}`)
    await screen.findByRole('heading', { name: UNSYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Sync to gateway' }))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Sync now' }))

    expect(
      await screen.findByText('Already synced — no change was made at the gateway.'),
    ).toBeInTheDocument()
  })

  it('surfaces a gateway failure without exposing provider detail', async () => {
    server.use(
      platformPlanDetailHandler(UNSYNCED),
      platformPlanSyncErrorHandler(),
    )
    renderAt(`/admin/plans/${UNSYNCED.id}`)
    await screen.findByRole('heading', { name: UNSYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Sync to gateway' }))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Sync now' }))

    expect(
      await screen.findByText(/payment gateway could not complete this sync/),
    ).toBeInTheDocument()
    // Still open, so the operator can retry or cancel.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('explains the lock on a synced plan', async () => {
    server.use(platformPlanDetailHandler(SYNCED))
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    expect(
      screen.getByText(/price, currency, interval and code are locked/),
    ).toBeInTheDocument()
  })

  it('offers no delete control anywhere on the page', async () => {
    server.use(platformPlanDetailHandler(SYNCED))
    renderAt(`/admin/plans/${SYNCED.id}`)
    await screen.findByRole('heading', { name: SYNCED.name })

    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
  })

  it('never sends X-Tenant-ID on a mutation', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      platformPlanDetailHandler(UNSYNCED),
      http.post(apiUrl('/platform/plans/sync/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json({
          ...UNSYNCED,
          external_plan_id: 'ext_x',
          created: true,
        })
      }),
    )
    renderAt(`/admin/plans/${UNSYNCED.id}`)
    await screen.findByRole('heading', { name: UNSYNCED.name })

    await userEvent.click(screen.getByRole('button', { name: 'Sync to gateway' }))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: 'Sync now' }))

    await waitFor(() => expect(tenantHeader).toBeNull())
  })
})
