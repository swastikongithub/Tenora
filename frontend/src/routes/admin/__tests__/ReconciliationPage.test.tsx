import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  PLATFORM_DISCREPANCIES,
  platformDiscrepanciesHandler,
  TENANT_A,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin/reconciliation') {
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
  server.use(...authHandlers(), platformDiscrepanciesHandler())
  server.use(usersMeStaffHandler())
})

describe('ReconciliationPage', () => {
  it('shows a loading state, then the discrepancy list', async () => {
    renderAt()
    expect(
      await screen.findByText('Loading reconciliation discrepancies'),
    ).toBeInTheDocument()
    expect(await screen.findByText('Northwind Trading')).toBeInTheDocument()
    // Also appears as a filter <option>, hence getAllByText.
    expect(screen.getAllByText('Status mismatch').length).toBeGreaterThan(0)
  })

  it('shows an empty state when there is no drift', async () => {
    server.use(platformDiscrepanciesHandler([]))
    renderAt()
    expect(await screen.findByText('No discrepancies found.')).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(
      http.get(apiUrl('/platform/reconciliation-discrepancies/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()
    expect(
      await screen.findByText('Couldn’t load reconciliation discrepancies.'),
    ).toBeInTheDocument()
  })

  it('never sends X-Tenant-ID', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/reconciliation-discrepancies/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json({
          count: PLATFORM_DISCREPANCIES.length,
          next: null,
          previous: null,
          results: PLATFORM_DISCREPANCIES,
        })
      }),
    )
    renderAt()
    await screen.findByText('Northwind Trading')
    expect(tenantHeader).toBeNull()
  })
})
