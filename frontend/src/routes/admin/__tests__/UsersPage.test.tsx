import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  PLATFORM_USERS,
  platformUsersHandler,
  TENANT_A,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin/users') {
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
  server.use(...authHandlers(), platformUsersHandler())
  server.use(usersMeStaffHandler())
})

describe('UsersPage', () => {
  it('shows a loading state, then the user list — never a password field', async () => {
    renderAt()
    expect(await screen.findByText('Loading users')).toBeInTheDocument()
    expect(await screen.findByText(PLATFORM_USERS[0].email)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/password/i)
  })

  it('has no role-management controls in Phase 1', async () => {
    renderAt()
    await screen.findByText(PLATFORM_USERS[0].email)
    expect(
      screen.queryByRole('button', { name: /promote|demote|grant|revoke/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    server.use(platformUsersHandler([]))
    renderAt()
    expect(await screen.findByText('No users match these filters.')).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(
      http.get(apiUrl('/platform/users/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()
    expect(await screen.findByText('Couldn’t load users.')).toBeInTheDocument()
  })
})
