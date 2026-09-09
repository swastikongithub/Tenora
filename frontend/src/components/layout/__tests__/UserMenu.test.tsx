import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import { apiUrl, usersMeHandler } from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { setCurrentTenantId } from '../../../lib/tenant/current-tenant'
import { UserMenu } from '../UserMenu'

function renderMenu() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter>
          <UserMenu />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => setCurrentTenantId(null))

describe('UserMenu — §4.4 current-user wiring', () => {
  it('shows the email fetched from /api/users/me/, not the C2 fallback', async () => {
    server.use(usersMeHandler({ id: 'u9', email: 'reloaded@example.com' }))

    renderMenu()

    expect(
      await screen.findByText('reloaded@example.com'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Signed in')).not.toBeInTheDocument()
  })

  it('shows a loading skeleton first — never flashes "Signed in" then swaps', async () => {
    server.use(
      http.get(apiUrl('/users/me/'), async () => {
        await delay(40)
        return HttpResponse.json({ id: 'u9', email: 'slow@example.com' })
      }),
    )

    renderMenu()

    // While /me/ is in flight: a skeleton, not the fallback label.
    expect(screen.queryByText('Signed in')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()

    expect(await screen.findByText('slow@example.com')).toBeInTheDocument()
  })

  it('falls back to a neutral label if /me/ fails, without crashing the menu', async () => {
    server.use(http.get(apiUrl('/users/me/'), () => HttpResponse.error()))

    renderMenu()

    expect(await screen.findByText('Signed in')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Log out' }),
    ).toBeInTheDocument()
  })
})
