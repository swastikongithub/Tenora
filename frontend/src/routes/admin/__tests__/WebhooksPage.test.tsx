import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  paginated,
  platformProcessPendingHandler,
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

describe('WebhooksPage — fallback sweep control (Phase 2)', () => {
  beforeEach(() => {
    server.use(platformProcessPendingHandler())
  })

  it('labels the control "Fallback Sweep Control" and explains why it is manual', async () => {
    renderAt()
    expect(
      await screen.findByText(/Fallback Sweep Control/),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/no production\s+worker is deployed/),
    ).toBeInTheDocument()
  })

  it('makes no request until the confirm modal is accepted', async () => {
    let calls = 0
    server.use(
      http.post(apiUrl('/platform/webhook-events/process-pending/'), () => {
        calls += 1
        return HttpResponse.json({ total: 0, processed: 0, deferred: 0, failed: 0 })
      }),
    )
    renderAt()
    await screen.findByText(/Fallback Sweep Control/)

    await userEvent.click(screen.getByRole('button', { name: 'Run now' }))
    expect(await screen.findByRole('dialog', { name: 'Webhook retry sweep' })).toBeInTheDocument()
    expect(calls).toBe(0)
  })

  it('canceling makes no request', async () => {
    let calls = 0
    server.use(
      http.post(apiUrl('/platform/webhook-events/process-pending/'), () => {
        calls += 1
        return HttpResponse.json({ total: 0, processed: 0, deferred: 0, failed: 0 })
      }),
    )
    renderAt()
    await screen.findByText(/Fallback Sweep Control/)
    await userEvent.click(screen.getByRole('button', { name: 'Run now' }))
    await screen.findByRole('dialog', { name: 'Webhook retry sweep' })

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(calls).toBe(0)
  })

  it('confirming calls the exact process-pending endpoint and shows the result', async () => {
    let calledPath = ''
    server.use(
      http.post(apiUrl('/platform/webhook-events/process-pending/'), ({ request }) => {
        calledPath = new URL(request.url).pathname
        return HttpResponse.json({ total: 3, processed: 2, deferred: 1, failed: 0 })
      }),
    )
    renderAt()
    await screen.findByText(/Fallback Sweep Control/)
    await userEvent.click(screen.getByRole('button', { name: 'Run now' }))
    await screen.findByRole('dialog', { name: 'Webhook retry sweep' })
    await userEvent.click(screen.getByRole('button', { name: 'Run sweep' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(calledPath).toContain('/platform/webhook-events/process-pending/')
    expect(
      await screen.findByText('3 checked, 2 processed, 1 deferred, 0 failed.'),
    ).toBeInTheDocument()
  })

  it('shows a loading state on the confirm button while the sweep runs', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.post(apiUrl('/platform/webhook-events/process-pending/'), async () => {
        await gate
        return HttpResponse.json({ total: 0, processed: 0, deferred: 0, failed: 0 })
      }),
    )
    renderAt()
    await screen.findByText(/Fallback Sweep Control/)
    await userEvent.click(screen.getByRole('button', { name: 'Run now' }))
    await screen.findByRole('dialog', { name: 'Webhook retry sweep' })
    const runButton = screen.getByRole('button', { name: 'Run sweep' })
    await userEvent.click(runButton)

    await waitFor(() => expect(runButton).toBeDisabled())
    release()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('a sweep failure renders an error and does not falsely claim success', async () => {
    server.use(
      http.post(apiUrl('/platform/webhook-events/process-pending/'), () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
    )
    renderAt()
    await screen.findByText(/Fallback Sweep Control/)
    await userEvent.click(screen.getByRole('button', { name: 'Run now' }))
    await screen.findByRole('dialog', { name: 'Webhook retry sweep' })
    await userEvent.click(screen.getByRole('button', { name: 'Run sweep' }))

    expect(await screen.findByText('Internal error')).toBeInTheDocument()
    expect(screen.queryByText(/checked,/)).not.toBeInTheDocument()
  })
})
