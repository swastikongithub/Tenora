/**
 * §4.5 / §9: the C1 dev showcase is gone — proven at the route table, not just
 * "the folder was deleted". `/dev/showcase` must not resolve to anything; it
 * falls through the `*` catch-all like any other unknown path.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AuthProvider } from '../../lib/auth'
import { createQueryClient } from '../../lib/query-client'
import { setCurrentTenantId } from '../../lib/tenant'
import { AppRoutes } from '../AppRoutes'

beforeEach(() => setCurrentTenantId(null))

describe('the dev showcase route', () => {
  it('does not exist — /dev/showcase falls through to the catch-all', async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/dev/showcase']}>
            <AppRoutes />
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )

    // catch-all → "/" → ProtectedRoute (unauthenticated) → /login
    expect(
      await screen.findByRole('heading', { name: 'Sign in' }),
    ).toBeInTheDocument()
    expect(screen.queryByText(/component showcase/i)).not.toBeInTheDocument()
  })
})
