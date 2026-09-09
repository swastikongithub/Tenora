import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  TENANT_A,
  TENANT_B,
  tenantsMeHandler,
  usersMeHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { setCurrentTenantId } from '../../../lib/tenant/current-tenant'
import { TenantProvider } from '../../../lib/tenant'
import { AppShell } from '../AppShell'

function renderShell() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/overview']}>
          <TenantProvider>
            <Routes>
              <Route path="/" element={<AppShell />}>
                <Route path="overview" element={<p>overview content</p>} />
                <Route path="members" element={<p>members content</p>} />
              </Route>
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
  server.use(tenantsMeHandler([TENANT_A, TENANT_B]), usersMeHandler())
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
})

describe('AppShell — desktop', () => {
  it('renders the primary nav, every destination, the tenant switcher, and the account menu', async () => {
    renderShell()

    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    for (const label of ['Overview', 'Workspace', 'Members', 'Subscription']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument()
    }

    // The switcher and account menu live in the bar, as siblings of the nav —
    // not inside it (navbar redesign §4.1).
    expect(
      await screen.findByRole('button', { name: new RegExp(TENANT_A.name) }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Account menu' }),
    ).toBeInTheDocument()

    expect(screen.getByText('overview content')).toBeInTheDocument()
  })

  it('navigates between route stubs via the navbar links', async () => {
    renderShell()
    const nav = await screen.findByRole('navigation', { name: 'Primary' })

    await userEvent.click(within(nav).getByRole('link', { name: 'Members' }))
    expect(await screen.findByText('members content')).toBeInTheDocument()
  })
})

describe('AppShell — narrow (<1024px)', () => {
  beforeEach(() => {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia
  })

  it('keeps the switcher and account menu in the bar and collapses the nav behind a hamburger', async () => {
    renderShell()

    // Switcher + avatar are reachable without opening anything.
    expect(
      await screen.findByRole('button', { name: new RegExp(TENANT_A.name) }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Account menu' }),
    ).toBeInTheDocument()

    // The primary nav is behind the hamburger.
    expect(
      screen.queryByRole('navigation', { name: 'Primary' }),
    ).not.toBeInTheDocument()

    const hamburger = screen.getByRole('button', { name: 'Open navigation' })
    expect(hamburger).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(hamburger)
    expect(hamburger).toHaveAttribute('aria-expanded', 'true')

    const nav = await screen.findByRole('navigation', { name: 'Primary' })
    expect(
      within(nav).getByRole('link', { name: 'Overview' }),
    ).toBeInTheDocument()

    // Following a link closes the panel.
    await userEvent.click(within(nav).getByRole('link', { name: 'Members' }))
    await waitFor(() =>
      expect(
        screen.queryByRole('navigation', { name: 'Primary' }),
      ).not.toBeInTheDocument(),
    )
    expect(await screen.findByText('members content')).toBeInTheDocument()
  })

  it('closes the nav panel on Escape', async () => {
    renderShell()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Open navigation' }),
    )
    expect(
      await screen.findByRole('navigation', { name: 'Primary' }),
    ).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(
        screen.queryByRole('navigation', { name: 'Primary' }),
      ).not.toBeInTheDocument(),
    )
  })
})
