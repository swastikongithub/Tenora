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

function renderAt(path = '/admin/webhooks') {
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
  server.use(...authHandlers(), platformWebhookEventsHandler())
  server.use(usersMeStaffHandler())
})

describe('WebhooksPage', () => {
  it('shows a loading state, then the normalized event list', async () => {
    renderAt()
    expect(await screen.findByText('Loading webhook events')).toBeInTheDocument()
    expect(
      await screen.findByText(PLATFORM_WEBHOOK_EVENTS[0].external_event_id),
    ).toBeInTheDocument()
    expect(screen.getByText('Northwind Trading')).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    server.use(
      http.get(apiUrl('/platform/webhook-events/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderAt()
    expect(
      await screen.findByText('Couldn’t load webhook events.'),
    ).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    server.use(platformWebhookEventsHandler([]))
    renderAt()
    expect(
      await screen.findByText('No webhook events match these filters.'),
    ).toBeInTheDocument()
  })

  it('never renders raw_payload even if the server response carried it', async () => {
    // A defensive contract test: even if a backend regression ever included
    // raw_payload in the sanitized endpoint's response, this page has no
    // code path that reads or renders that key.
    server.use(
      http.get(apiUrl('/platform/webhook-events/'), () =>
        HttpResponse.json(
          paginated([
            {
              ...PLATFORM_WEBHOOK_EVENTS[0],
              raw_payload: { contact: { email: 'leaked@example.com' } },
            },
          ]),
        ),
      ),
    )
    renderAt()
    await screen.findByText(PLATFORM_WEBHOOK_EVENTS[0].external_event_id)
    expect(screen.queryByText('leaked@example.com')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('leaked@example.com')
  })

  it('never sends X-Tenant-ID', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/webhook-events/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json(paginated(PLATFORM_WEBHOOK_EVENTS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_WEBHOOK_EVENTS[0].external_event_id)
    expect(tenantHeader).toBeNull()
  })
})
