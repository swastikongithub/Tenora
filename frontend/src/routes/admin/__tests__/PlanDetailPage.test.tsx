import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  PLATFORM_PLANS,
  platformPlanDetailHandler,
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
