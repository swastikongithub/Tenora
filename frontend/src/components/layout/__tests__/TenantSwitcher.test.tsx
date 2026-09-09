import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  TENANT_A,
  TENANT_B,
  apiUrl,
  tenantsMeHandler,
} from '../../../test/fixtures'
import { createQueryClient } from '../../../lib/query-client'
import {
  getCurrentTenantId,
  setCurrentTenantId,
} from '../../../lib/tenant/current-tenant'
import { TenantProvider } from '../../../lib/tenant'
import { TenantSwitcher } from '../TenantSwitcher'

function renderSwitcher() {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TenantProvider>
          <TenantSwitcher />
        </TenantProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => setCurrentTenantId(null))

describe('TenantSwitcher', () => {
  it('shows a skeleton while the tenant list loads', () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderSwitcher()
    expect(screen.getByText('Loading workspaces')).toBeInTheDocument()
  })

  it('shows the empty state with a link to the workspace page', async () => {
    server.use(tenantsMeHandler([]))
    renderSwitcher()
    expect(
      await screen.findByText('No workspace selected'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Choose or create one' }),
    ).toHaveAttribute('href', '/workspace')
  })

  it('shows a blocking retry on error and recovers when retried', async () => {
    let attempts = 0
    server.use(
      http.get(apiUrl('/tenants/me/'), () => {
        attempts += 1
        return attempts === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json([TENANT_A])
      }),
    )
    renderSwitcher()

    const retry = await screen.findByRole('button', { name: 'Retry' })
    await userEvent.click(retry)

    expect(await screen.findByText(TENANT_A.name)).toBeInTheDocument()
  })

  it('opens the menu, lists every tenant with its role, and switches on select', async () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderSwitcher()

    const trigger = await screen.findByRole('button', {
      name: new RegExp(TENANT_A.name),
    })
    await userEvent.click(trigger)

    const menu = screen.getByRole('menu', { name: 'Switch workspace' })
    expect(within(menu).getByText('OWNER')).toBeInTheDocument()
    expect(within(menu).getByText('MEMBER')).toBeInTheDocument()

    await userEvent.click(
      within(menu).getByRole('menuitemradio', {
        name: new RegExp(TENANT_B.name),
      }),
    )

    expect(getCurrentTenantId()).toBe(TENANT_B.id)
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: new RegExp(TENANT_B.name) }),
      ).toBeInTheDocument(),
    )
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('closes the menu on Escape', async () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderSwitcher()

    const trigger = await screen.findByRole('button', {
      name: new RegExp(TENANT_A.name),
    })
    await userEvent.click(trigger)
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('opens over a blurred backdrop that closes the menu on click', async () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderSwitcher()

    await userEvent.click(
      await screen.findByRole('button', { name: new RegExp(TENANT_A.name) }),
    )
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('tenant-switcher-backdrop'))
    await waitFor(() =>
      expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
    )
  })

  it('disables the entrance motion under prefers-reduced-motion', async () => {
    // setup.ts stubs matchMedia to match every query, so reduced motion is the
    // default in the test env — assert the menu reflects that.
    server.use(tenantsMeHandler([TENANT_A]))
    renderSwitcher()
    await userEvent.click(
      await screen.findByRole('button', { name: new RegExp(TENANT_A.name) }),
    )
    expect(screen.getByRole('menu')).toHaveAttribute('data-motion', 'reduced')
  })

  it('traps focus in the open menu and returns it to the trigger on close', async () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderSwitcher()

    const trigger = await screen.findByRole('button', {
      name: new RegExp(TENANT_A.name),
    })
    await userEvent.click(trigger)
    const menu = screen.getByRole('menu')

    // Focus moved onto the first workspace, not left on the trigger.
    await waitFor(() => expect(menu.contains(document.activeElement)).toBe(true))

    // Tab stays within the list.
    for (let i = 0; i < 4; i++) {
      await userEvent.tab()
      expect(menu.contains(document.activeElement)).toBe(true)
    }
    for (let i = 0; i < 4; i++) {
      await userEvent.tab({ shift: true })
      expect(menu.contains(document.activeElement)).toBe(true)
    }

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(trigger)
  })
})
