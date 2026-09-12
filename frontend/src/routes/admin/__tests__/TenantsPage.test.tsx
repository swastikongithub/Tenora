import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  paginated,
  PLATFORM_TENANTS,
  platformTenantsHandler,
  TENANT_A,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin/tenants') {
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
  server.use(...authHandlers(), platformTenantsHandler())
  server.use(usersMeStaffHandler())
})

describe('TenantsPage', () => {
  it('shows a loading state, then every tenant, each linking to its detail page', async () => {
    renderAt()

    expect(await screen.findByText('Loading tenants')).toBeInTheDocument()

    for (const t of PLATFORM_TENANTS) {
      const link = await screen.findByRole('link', { name: t.name })
      expect(link).toHaveAttribute('href', `/admin/tenants/${t.id}`)
    }
  })

  it('shows an error state', async () => {
    server.use(
      http.get(apiUrl('/platform/tenants/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()
    expect(await screen.findByText('Couldn’t load tenants.')).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    server.use(platformTenantsHandler([]))
    renderAt()
    expect(
      await screen.findByText('No tenants match these filters.'),
    ).toBeInTheDocument()
  })

  it('reads the paginated envelope, not a bare array', async () => {
    server.use(
      http.get(apiUrl('/platform/tenants/'), () =>
        HttpResponse.json(paginated(PLATFORM_TENANTS)),
      ),
    )
    renderAt()
    expect(await screen.findByText(PLATFORM_TENANTS[0].name)).toBeInTheDocument()
  })
})
