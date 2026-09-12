import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  PLATFORM_TENANT_DETAIL,
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
