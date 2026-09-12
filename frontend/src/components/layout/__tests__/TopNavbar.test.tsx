import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  TENANT_A,
  tenantsMeHandler,
  usersMeHandler,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { setCurrentTenantId } from '../../../lib/tenant/current-tenant'
import { TenantProvider } from '../../../lib/tenant'
import { TopNavbar } from '../TopNavbar'

function renderNavbar(path = '/overview') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <TenantProvider>
            <Routes>
              <Route path="*" element={<TopNavbar />} />
            </Routes>
          </TenantProvider>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const originalMatchMedia = window.matchMedia

beforeEach(() => {
  setCurrentTenantId(null)
  server.use(tenantsMeHandler([TENANT_A]), usersMeHandler())
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
})

describe('TopNavbar', () => {
  it('renders the wordmark linking to /overview and all four nav items', async () => {
    renderNavbar()

    expect(screen.getByRole('link', { name: /tenora/i })).toHaveAttribute(
      'href',
      '/overview',
    )

    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    for (const label of ['Overview', 'Workspace', 'Members', 'Subscription']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument()
    }
  })

  it('marks the active route with aria-current and no other', async () => {
    renderNavbar('/members')

    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('link', { name: 'Members' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(
      within(nav).getByRole('link', { name: 'Overview' }),
    ).not.toHaveAttribute('aria-current')
  })

  it('renders the desktop nav links as text only (icons stay in the mobile panel)', async () => {
    renderNavbar()
    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    expect(nav.querySelector('svg')).toBeNull()
  })

  it('does not show the Platform Admin link for a non-staff user', async () => {
    renderNavbar()
    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    // The four ordinary items are there…
    expect(within(nav).getByRole('link', { name: 'Overview' })).toBeInTheDocument()
    // …and the staff-only one is not.
    expect(
      within(nav).queryByRole('link', { name: 'Platform Admin' }),
    ).not.toBeInTheDocument()
  })

  it('shows the Platform Admin link for a platform-staff user', async () => {
    server.use(usersMeStaffHandler())
    renderNavbar()
    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    expect(
      await within(nav).findByRole('link', { name: 'Platform Admin' }),
    ).toHaveAttribute('href', '/admin')
  })

  it('keeps the tenant switcher and account menu as siblings of the nav, always visible', async () => {
    renderNavbar()
    expect(
      await screen.findByRole('button', { name: new RegExp(TENANT_A.name) }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Account menu' }),
    ).toBeInTheDocument()
  })
})
