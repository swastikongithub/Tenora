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
  PLATFORM_TENANT_DETAIL,
  platformPlansHandler,
  platformSubscriptionPatchErrorHandler,
  platformTenantDetailHandler,
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

describe('TenantDetailPage', () => {
  it('shows the tenant, its members, and its subscription', async () => {
    server.use(platformTenantDetailHandler())
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)

    expect(
      await screen.findByRole('heading', { name: 'Northwind Trading' }),
    ).toBeInTheDocument()
    expect(screen.getByText('owner@northwind.test')).toBeInTheDocument()
    expect(screen.getByText('Pro')).toBeInTheDocument()
  })

  it('shows "No members." and no-subscription state when absent', async () => {
    server.use(
      platformTenantDetailHandler({
        ...PLATFORM_TENANT_DETAIL,
        memberships: [],
        subscription: null,
      }),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)

    expect(await screen.findByText('No members.')).toBeInTheDocument()
    expect(screen.getByText('No subscription')).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(
      http.get(apiUrl('/platform/tenants/detail/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    expect(await screen.findByText('Couldn’t load this tenant.')).toBeInTheDocument()
  })
})

const TEAM_PLAN = { ...PLATFORM_PLANS[0], id: 'plan-team', name: 'Team', code: 'TEAM' }

describe('TenantDetailPage — subscription override controls (Phase 2)', () => {
  beforeEach(() => {
    server.use(platformTenantDetailHandler())
    server.use(platformPlansHandler([PLATFORM_PLANS[0], TEAM_PLAN]))
  })

  it('renders operator override controls for a staff viewer, excluding the current plan/status', async () => {
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    await screen.findByRole('heading', { name: 'Northwind Trading' })

    expect(screen.getByText('Operator overrides')).toBeInTheDocument()
    const planSelect = screen.getByLabelText('Change plan')
    expect(await screen.findByRole('option', { name: 'Team' })).toBeInTheDocument()
    // The current plan (Pro) is not offered as a target.
    expect(
      Array.from(planSelect.querySelectorAll('option')).map((o) => o.textContent),
    ).not.toContain('Pro')

    const statusSelect = screen.getByLabelText('Transition status')
    // Subscription is ACTIVE — not offered as its own target.
    expect(
      Array.from(statusSelect.querySelectorAll('option')).map((o) => o.textContent),
    ).not.toContain('ACTIVE')
  })

  it('no mutation happens before the confirm modal is accepted', async () => {
    let patchCalls = 0
    server.use(
      http.patch(apiUrl('/platform/subscriptions/detail/'), () => {
        patchCalls += 1
        return HttpResponse.json(PLATFORM_TENANT_DETAIL.subscription)
      }),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    await screen.findByRole('heading', { name: 'Northwind Trading' })

    await screen.findByRole('option', { name: 'Team' })
    await userEvent.selectOptions(screen.getByLabelText('Change plan'), 'plan-team')
    await userEvent.click(screen.getAllByRole('button', { name: 'Apply' })[0])

    expect(await screen.findByRole('dialog', { name: 'Change plan' })).toBeInTheDocument()
    expect(patchCalls).toBe(0)
  })

  it('canceling the confirm modal makes no request', async () => {
    let patchCalls = 0
    server.use(
      http.patch(apiUrl('/platform/subscriptions/detail/'), () => {
        patchCalls += 1
        return HttpResponse.json(PLATFORM_TENANT_DETAIL.subscription)
      }),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    await screen.findByRole('heading', { name: 'Northwind Trading' })

    await screen.findByRole('option', { name: 'Team' })
    await userEvent.selectOptions(screen.getByLabelText('Change plan'), 'plan-team')
    await userEvent.click(screen.getAllByRole('button', { name: 'Apply' })[0])
    await screen.findByRole('dialog', { name: 'Change plan' })

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(patchCalls).toBe(0)
  })

  it('confirming a plan change PATCHes the endpoint with plan_id and refetches the tenant', async () => {
    let body: unknown
    let getCalls = 0
    server.use(
      http.get(apiUrl('/platform/tenants/detail/'), () => {
        getCalls += 1
        return HttpResponse.json(PLATFORM_TENANT_DETAIL)
      }),
      http.patch(apiUrl('/platform/subscriptions/detail/'), async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          ...PLATFORM_TENANT_DETAIL.subscription,
          plan: TEAM_PLAN,
        })
      }),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    await screen.findByRole('heading', { name: 'Northwind Trading' })
    await screen.findByRole('option', { name: 'Team' })
    const callsBeforeConfirm = getCalls

    await userEvent.selectOptions(screen.getByLabelText('Change plan'), 'plan-team')
    await userEvent.click(screen.getAllByRole('button', { name: 'Apply' })[0])
    await screen.findByRole('dialog', { name: 'Change plan' })
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(body).toEqual({ plan_id: 'plan-team' })
    await waitFor(() => expect(getCalls).toBeGreaterThan(callsBeforeConfirm))
  })

  it('a server error renders safely inside the modal, which stays open', async () => {
    server.use(
      platformSubscriptionPatchErrorHandler(
        'plan_id',
        'Cannot change the plan of a CANCELED subscription.',
      ),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    await screen.findByRole('heading', { name: 'Northwind Trading' })

    await screen.findByRole('option', { name: 'Team' })
    await userEvent.selectOptions(screen.getByLabelText('Change plan'), 'plan-team')
    await userEvent.click(screen.getAllByRole('button', { name: 'Apply' })[0])
    await screen.findByRole('dialog', { name: 'Change plan' })
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(
      await screen.findByText('Cannot change the plan of a CANCELED subscription.'),
    ).toBeInTheDocument()
    // Stays open — the operator can see the error and retry or cancel.
    expect(screen.getByRole('dialog', { name: 'Change plan' })).toBeInTheDocument()
  })

  it('a status transition follows the identical confirm-then-mutate flow', async () => {
    let body: unknown
    server.use(
      http.patch(apiUrl('/platform/subscriptions/detail/'), async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          ...PLATFORM_TENANT_DETAIL.subscription,
          status: 'PAST_DUE',
        })
      }),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    await screen.findByRole('heading', { name: 'Northwind Trading' })

    await userEvent.selectOptions(screen.getByLabelText('Transition status'), 'PAST_DUE')
    await userEvent.click(screen.getAllByRole('button', { name: 'Apply' })[1])
    await screen.findByRole('dialog', { name: 'Transition status' })
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(body).toEqual({ status: 'PAST_DUE' })
  })

  it('does not render override controls when the tenant has no subscription', async () => {
    server.use(
      platformTenantDetailHandler({ ...PLATFORM_TENANT_DETAIL, subscription: null }),
    )
    renderAt(`/admin/tenants/${PLATFORM_TENANT_DETAIL.id}`)
    await screen.findByRole('heading', { name: 'Northwind Trading' })
    expect(screen.queryByText('Operator overrides')).not.toBeInTheDocument()
  })
})
