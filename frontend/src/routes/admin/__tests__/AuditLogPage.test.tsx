import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import { authHandlers, TENANT_A, usersMeStaffHandler } from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin/audit-log') {
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
  // A separate, later .use() call — MSW resolves the first-matching handler
  // among ones added together, and authHandlers() already bundles a
  // non-staff /users/me/ handler; this later call must win.
  server.use(usersMeStaffHandler())
})

describe('AuditLogPage', () => {
  it('exists in the canonical /admin route tree and is honest that Phase 1 has no data for it', async () => {
    renderAt()
    expect(await screen.findByRole('heading', { name: 'Audit Log' })).toBeInTheDocument()
    expect(
      screen.getByText(/isn.t available yet/i),
    ).toBeInTheDocument()
  })

  it('makes no backend request', async () => {
    // No /api/platform/audit-log/ handler is registered in this suite at
    // all (see beforeEach) — MSW's onUnhandledRequest: 'bypass' means an
    // accidental request here would surface as a network failure the page
    // would have to render, not a silent pass. (Other role="status" regions
    // exist in the app shell itself — e.g. the tenant switcher's own
    // loading state — so this checks for an error, not global silence.)
    renderAt()
    expect(await screen.findByRole('heading', { name: 'Audit Log' })).toBeInTheDocument()
    expect(screen.queryByText(/Couldn.t load/i)).not.toBeInTheDocument()
  })
})
