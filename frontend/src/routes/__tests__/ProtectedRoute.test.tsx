import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../test/msw/server'
import {
  authHandlers,
  apiUrl,
  TENANT_A,
  tenantsMeHandler,
  usersMeHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import { AppRoutes } from '../AppRoutes'

function renderAt(path: string) {
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

beforeEach(() => setCurrentTenantId(null))

describe('ProtectedRoute', () => {
  it('redirects an unauthenticated visit to /login', async () => {
    renderAt('/overview')
    expect(
      await screen.findByRole('heading', { name: 'Sign in' }),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Overview — built/)).not.toBeInTheDocument()
  })

  it('renders the shell and the route content when authenticated', async () => {
    sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
    server.use(...authHandlers(), tenantsMeHandler([TENANT_A]))

    renderAt('/overview')

    expect(
      await screen.findByRole('heading', { name: 'Team' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('navigation', { name: 'Primary' }),
    ).toBeInTheDocument()
  })

  it('shows a loader (not the login page) while the silent refresh is in flight', async () => {
    sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
    server.use(
      http.post(apiUrl('/auth/refresh/'), async () => {
        await delay(120)
        return HttpResponse.json({ access: 'a', refresh: 'r2' })
      }),
      tenantsMeHandler([TENANT_A]),
      usersMeHandler(),
    )

    renderAt('/overview')

    expect(screen.getByText(/Loading/)).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Sign in' }),
    ).not.toBeInTheDocument()

    expect(
      await screen.findByRole('heading', { name: 'Team' }),
    ).toBeInTheDocument()
  })
})
