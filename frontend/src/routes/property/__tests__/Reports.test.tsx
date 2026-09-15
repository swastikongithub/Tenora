/**
 * Plan §16 reports: the owner Reports page and the platform-admin roll-up show
 * the server's monthly metrics, including collections by charge type, and
 * electricity by unit. Numbers are the fixtures' — nothing is recomputed here.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AuthProvider } from '../../../lib/auth'
import type { MonthlyReportRow } from '../../../lib/property/types'
import { createQueryClient } from '../../../lib/query-client'
import { server } from '../../../test/msw/server'
import { apiUrl, authHandlers, TENANT_A, tenantsMeHandler, usersMeStaffHandler } from '../../../test/fixtures'
import { OVERVIEW, json, page, shellHandlers } from '../../../test/property-fixtures'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path: string) {
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

const MARCH: MonthlyReportRow = {
  period: '2026-03',
  billed_cents: 2644000,
  collected_cents: 1878000,
  outstanding_cents: 766000,
  rent_billed_cents: 2400000,
  electricity_billed_cents: 200000,
  other_billed_cents: 44000,
  rent_collected_cents: 1200000,
  electricity_collected_cents: 128000,
  other_collected_cents: 50000,
  collected_unallocated_cents: 500000,
  electricity_units: '250.000',
  cash_received_cents: 1878000,
}

const UNIT_ROWS = [
  { tenant_id: 'tenant-a', tenant_name: 'Alpha Corp', property_name: 'Building A', unit_identifier: '203', units: '160.000', amount_cents: 128000 },
  { tenant_id: 'tenant-c', tenant_name: 'Gamma Homes', property_name: 'Building A', unit_identifier: '203', units: '90.000', amount_cents: 72000 },
]

beforeEach(() => {
  server.use(...authHandlers(), ...shellHandlers(), tenantsMeHandler([TENANT_A]))
})

describe('owner reports', () => {
  it('splits collections by charge and shows part-payments separately', async () => {
    server.use(json('/billing/reports/', { period: '2026-03', monthly: [MARCH], electricity_by_unit: [UNIT_ROWS[0]] }))
    renderAt('/billing/reports')
    const collections = await screen.findByRole('table', { name: 'Collections by charge' })
    expect(within(collections).getByText('₹12,000.00')).toBeInTheDocument()
    expect(within(collections).getByText('₹1,280.00')).toBeInTheDocument()
    expect(within(collections).getByText('₹5,000.00')).toBeInTheDocument()
    expect(within(collections).getByText('₹18,780.00')).toBeInTheDocument()
    const units = screen.getByRole('table', { name: 'Electricity by unit' })
    expect(within(units).getByText('203 · Building A')).toBeInTheDocument()
    expect(within(units).queryByText('Alpha Corp')).not.toBeInTheDocument()
  })
})

describe('platform-admin reports', () => {
  it('shows the same metrics across workspaces, naming each unit’s workspace', async () => {
    const summaryQueries: string[] = []
    server.use(
      usersMeStaffHandler(),
      http.get(apiUrl('/platform/property-billing/summary/'), ({ request }) => {
        summaryQueries.push(new URL(request.url).search)
        return HttpResponse.json({
          workspaces: 2, active_subscriptions: 1, properties: 2, residents: 2, total_bills: 2, total_billed_cents: 2644000,
          total_collected_cents: 1878000, total_outstanding_cents: 766000, total_overdue_cents: 766000, total_payments: 2,
          total_payments_cents: 1878000, electricity_units: '250.000', current_period: OVERVIEW.current_month,
          period: '2026-03', monthly: [MARCH], electricity_by_unit: UNIT_ROWS,
        })
      }),
      json('/platform/property-billing/workspaces/', page([])),
      json('/platform/property-billing/bills/', page([])),
    )
    renderAt('/admin/property-billing')
    expect(await screen.findByRole('heading', { name: 'Last 12 months · all workspaces' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Collections by charge' })).toBeInTheDocument()
    const units = screen.getByRole('table', { name: 'Electricity by unit' })
    expect(within(units).getByText('Alpha Corp')).toBeInTheDocument()
    expect(within(units).getByText('Gamma Homes')).toBeInTheDocument()
    expect(summaryQueries[0]).toBe('')
  })
})
