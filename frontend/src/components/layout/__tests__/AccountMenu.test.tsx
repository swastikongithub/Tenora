import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
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
import { TenantProvider, useTenant } from '../../../lib/tenant'
import { AccountMenu } from '../AccountMenu'

function Harness() {
  const { switchTenant } = useTenant()
  return (
    <>
      <AccountMenu />
      <button type="button" onClick={() => switchTenant(TENANT_B.id)}>
        switch tenant
      </button>
    </>
  )
}

function renderMenu() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter>
          <TenantProvider>
            <Harness />
          </TenantProvider>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const originalMatchMedia = window.matchMedia

function stubReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('reduced-motion') ? reduce : true,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
}

beforeEach(() => {
  setCurrentTenantId(null)
  server.use(tenantsMeHandler([TENANT_A, TENANT_B]), usersMeHandler())
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
})

describe('AccountMenu', () => {
  it('opens and closes on the avatar, toggling aria-expanded', async () => {
    renderMenu()
    const avatar = screen.getByRole('button', { name: 'Account menu' })
    expect(avatar).toHaveAttribute('aria-expanded', 'false')

    await userEvent.click(avatar)
    expect(avatar).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('menu', { name: 'Account' })).toBeInTheDocument()

    await userEvent.click(avatar)
    expect(avatar).toHaveAttribute('aria-expanded', 'false')
    await waitFor(() =>
      expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
    )
  })

  it('moves focus into the panel and returns it to the avatar on Escape', async () => {
    renderMenu()
    const avatar = screen.getByRole('button', { name: 'Account menu' })
    await userEvent.click(avatar)

    const menu = screen.getByRole('menu')
    await waitFor(() =>
      expect(menu.contains(document.activeElement)).toBe(true),
    )

    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
    )
    expect(document.activeElement).toBe(avatar)
  })

  it('closes when the backdrop is clicked', async () => {
    renderMenu()
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('account-menu-backdrop'))
    await waitFor(() =>
      expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
    )
  })

  it('traps Tab focus within the panel', async () => {
    renderMenu()
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    const menu = screen.getByRole('menu')

    for (let i = 0; i < 6; i++) {
      await userEvent.tab()
      expect(menu.contains(document.activeElement)).toBe(true)
    }
    for (let i = 0; i < 6; i++) {
      await userEvent.tab({ shift: true })
      expect(menu.contains(document.activeElement)).toBe(true)
    }
  })

  it('disables the entrance motion under prefers-reduced-motion', async () => {
    stubReducedMotion(true)
    renderMenu()
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(screen.getByRole('menu')).toHaveAttribute('data-motion', 'reduced')
  })

  it('animates the entrance when reduced motion is not requested', async () => {
    stubReducedMotion(false)
    renderMenu()
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(screen.getByRole('menu')).toHaveAttribute('data-motion', 'full')
  })

  it('closes cleanly when the tenant is switched while open', async () => {
    renderMenu()
    // Let the tenant list resolve so the switch is a real id change.
    await screen.findByRole('button', { name: 'switch tenant' })
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'switch tenant' }))
    await waitFor(() =>
      expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
    )
  })
})
