import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  paginated,
  PLATFORM_WEBHOOK_EVENTS,
  platformWebhookEventsHandler,
  TENANT_A,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin/billing-events') {
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

const NON_BILLING_EVENT = {
  ...PLATFORM_WEBHOOK_EVENTS[0],
  id: 'evt-2',
  external_event_id: 'evt_activated_1',
  event_type: 'ACTIVATED' as const,
}

beforeEach(() => {
  server.use(...authHandlers())
  server.use(usersMeStaffHandler())
})

describe('BillingEventsPage', () => {
  it('shows only CHARGED/PAYMENT_TROUBLE events, not every event type, and no amount column', async () => {
    server.use(
      platformWebhookEventsHandler([PLATFORM_WEBHOOK_EVENTS[0], NON_BILLING_EVENT]),
    )
    renderAt()

    expect(
      await screen.findByText(PLATFORM_WEBHOOK_EVENTS[0].external_subscription_id!),
    ).toBeInTheDocument()
    expect(screen.queryByText('evt_activated_1')).not.toBeInTheDocument()

    // No fabricated amount/ledger — the page names the gap explicitly.
    expect(
      screen.getByText(/Amounts aren.t captured locally/),
    ).toBeInTheDocument()
  })

  it('shows an empty state when there is no billing activity', async () => {
    server.use(platformWebhookEventsHandler([]))
    renderAt()
    expect(await screen.findByText('No billing events yet.')).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(
      http.get(apiUrl('/platform/webhook-events/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()
    expect(await screen.findByText('Couldn’t load billing events.')).toBeInTheDocument()
  })

  it('does not render raw_payload content even if present on the wire', async () => {
    server.use(
      http.get(apiUrl('/platform/webhook-events/'), () =>
        HttpResponse.json(
          paginated([
            { ...PLATFORM_WEBHOOK_EVENTS[0], raw_payload: { contact: 'leaked@example.com' } },
          ]),
        ),
      ),
    )
    renderAt()
    await screen.findByText(PLATFORM_WEBHOOK_EVENTS[0].external_subscription_id!)
    expect(document.body.textContent).not.toContain('leaked@example.com')
  })
})
