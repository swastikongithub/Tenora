import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  PLATFORM_DISCREPANCIES,
  platformDiscrepanciesHandler,
  platformReconciliationRunHandler,
  platformUsageRunHandler,
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

describe('ReconciliationPage — fallback sweep controls (Phase 2)', () => {
  beforeEach(() => {
    server.use(platformReconciliationRunHandler(), platformUsageRunHandler())
  })

  it('shows two labeled Fallback Sweep Controls: reconciliation and usage', async () => {
    renderAt()
    const labels = await screen.findAllByText(/Fallback Sweep Control/)
    expect(labels.length).toBe(2)
    expect(screen.getByText('Reconciliation sweep')).toBeInTheDocument()
    expect(screen.getByText('Usage snapshot sweep')).toBeInTheDocument()
  })

  it('running the reconciliation sweep calls the exact endpoint and shows the result', async () => {
    let calledPath = ''
    server.use(
      http.post(apiUrl('/platform/reconciliation/run/'), ({ request }) => {
        calledPath = new URL(request.url).pathname
        return HttpResponse.json({
          total: 2,
          matched: 2,
          discrepancies: 0,
          unavailable: 0,
          skipped: 0,
          errors: 0,
        })
      }),
    )
    renderAt()
    const card = (await screen.findByText('Reconciliation sweep')).closest(
      '.rounded-lg',
    ) as HTMLElement

    await userEvent.click(within(card).getByRole('button', { name: 'Run now' }))
    await screen.findByRole('dialog', { name: 'Reconciliation sweep' })
    await userEvent.click(screen.getByRole('button', { name: 'Run sweep' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(calledPath).toContain('/platform/reconciliation/run/')
    expect(
      await within(card).findByText('2 checked, 2 matched, 0 discrepancies, 0 unavailable.'),
    ).toBeInTheDocument()
  })

  it('running the usage sweep calls the exact endpoint, independent of the reconciliation one', async () => {
    let reconciliationCalls = 0
    let usageCalls = 0
    server.use(
      http.post(apiUrl('/platform/reconciliation/run/'), () => {
        reconciliationCalls += 1
        return HttpResponse.json({
          total: 0, matched: 0, discrepancies: 0, unavailable: 0, skipped: 0, errors: 0,
        })
      }),
      http.post(apiUrl('/platform/usage/run/'), () => {
        usageCalls += 1
        return HttpResponse.json({ total: 4, created: 4, existing: 0, skipped: 0 })
      }),
    )
    renderAt()
    const card = (await screen.findByText('Usage snapshot sweep')).closest(
      '.rounded-lg',
    ) as HTMLElement

    await userEvent.click(within(card).getByRole('button', { name: 'Run now' }))
    await screen.findByRole('dialog', { name: 'Usage snapshot sweep' })
    await userEvent.click(screen.getByRole('button', { name: 'Run sweep' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(usageCalls).toBe(1)
    expect(reconciliationCalls).toBe(0)
    expect(
      await within(card).findByText('4 tenants, 4 new snapshots, 0 already existed, 0 skipped.'),
    ).toBeInTheDocument()
  })

  it('makes no request until confirmed, for either sweep', async () => {
    let calls = 0
    server.use(
      http.post(apiUrl('/platform/reconciliation/run/'), () => {
        calls += 1
        return HttpResponse.json({
          total: 0, matched: 0, discrepancies: 0, unavailable: 0, skipped: 0, errors: 0,
        })
      }),
    )
    renderAt()
    await screen.findByText('Reconciliation sweep')
    await userEvent.click(
      within(
        (await screen.findByText('Reconciliation sweep')).closest('.rounded-lg') as HTMLElement,
      ).getByRole('button', { name: 'Run now' }),
    )
    await screen.findByRole('dialog', { name: 'Reconciliation sweep' })
    expect(calls).toBe(0)
  })

  it('a sweep failure renders an error inside its own card', async () => {
    server.use(
      http.post(apiUrl('/platform/reconciliation/run/'), () =>
        HttpResponse.json({ detail: 'Service unavailable' }, { status: 500 }),
      ),
    )
    renderAt()
    const card = (await screen.findByText('Reconciliation sweep')).closest(
      '.rounded-lg',
    ) as HTMLElement
    await userEvent.click(within(card).getByRole('button', { name: 'Run now' }))
    await screen.findByRole('dialog', { name: 'Reconciliation sweep' })
    await userEvent.click(screen.getByRole('button', { name: 'Run sweep' }))

    expect(await within(card).findByText('Service unavailable')).toBeInTheDocument()
  })
})
