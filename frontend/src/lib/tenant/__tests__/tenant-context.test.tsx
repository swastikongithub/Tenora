import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  TENANT_A,
  TENANT_B,
  apiUrl,
  tenantsMeHandler,
} from '../../../test/fixtures'
import { createQueryClient } from '../../query-client'
import { getCurrentTenantId, setCurrentTenantId } from '../current-tenant'
import { TenantProvider } from '../TenantProvider'
import { useTenant } from '../tenant-context'

function Probe() {
  const { currentTenantId, currentTenant, tenants, status, switchTenant } =
    useTenant()
  return (
    <div>
      <output data-testid="status">{status}</output>
      <output data-testid="current">{currentTenantId ?? 'none'}</output>
      <output data-testid="current-name">
        {currentTenant?.name ?? 'none'}
      </output>
      <output data-testid="count">{tenants.length}</output>
      <button onClick={() => switchTenant(TENANT_B.id)}>switch B</button>
      <button onClick={() => switchTenant('ghost-tenant')}>switch ghost</button>
    </div>
  )
}

function renderTenant() {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <Probe />
      </TenantProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  setCurrentTenantId(null)
})

describe('TenantProvider', () => {
  it('loads the tenant list and selects the first tenant by default', async () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderTenant()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('ready'),
    )
    expect(screen.getByTestId('count')).toHaveTextContent('2')
    expect(screen.getByTestId('current')).toHaveTextContent(TENANT_A.id)
    // The header accessor is synced by an effect — poll for it.
    await waitFor(() => expect(getCurrentTenantId()).toBe(TENANT_A.id))
  })

  it('restores a valid last-selected tenant from localStorage', async () => {
    localStorage.setItem('billing.last_tenant_id', TENANT_B.id)
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderTenant()

    await waitFor(() =>
      expect(screen.getByTestId('current')).toHaveTextContent(TENANT_B.id),
    )
  })

  it('falls back to the first tenant (not an error) when the stored id is gone', async () => {
    localStorage.setItem('billing.last_tenant_id', 'removed-last-session')
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderTenant()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('ready'),
    )
    expect(screen.getByTestId('current')).toHaveTextContent(TENANT_A.id)
  })

  it('switchTenant updates the selection, the header accessor, and localStorage', async () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderTenant()
    await waitFor(() =>
      expect(screen.getByTestId('current')).toHaveTextContent(TENANT_A.id),
    )

    await userEvent.click(screen.getByRole('button', { name: 'switch B' }))

    expect(screen.getByTestId('current')).toHaveTextContent(TENANT_B.id)
    expect(screen.getByTestId('current-name')).toHaveTextContent(TENANT_B.name)
    expect(getCurrentTenantId()).toBe(TENANT_B.id)
    expect(localStorage.getItem('billing.last_tenant_id')).toBe(TENANT_B.id)
  })

  it('switchTenant ignores an id that is not one of the user’s tenants', async () => {
    server.use(tenantsMeHandler([TENANT_A, TENANT_B]))
    renderTenant()
    await waitFor(() =>
      expect(screen.getByTestId('current')).toHaveTextContent(TENANT_A.id),
    )

    await userEvent.click(screen.getByRole('button', { name: 'switch ghost' }))
    expect(screen.getByTestId('current')).toHaveTextContent(TENANT_A.id)
  })

  it('reports status "empty" when the user belongs to no tenant', async () => {
    server.use(tenantsMeHandler([]))
    renderTenant()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('empty'),
    )
    expect(screen.getByTestId('current')).toHaveTextContent('none')
  })

  it('reports status "error" when /api/tenants/me/ fails', async () => {
    server.use(
      http.get(apiUrl('/tenants/me/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderTenant()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('error'),
    )
  })
})
