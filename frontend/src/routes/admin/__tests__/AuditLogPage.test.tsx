import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  apiUrl,
  authHandlers,
  paginated,
  PLATFORM_AUDIT_EVENTS,
  platformAuditLogHandler,
  TENANT_A,
  tenantsMeHandler,
  usersMeStaffHandler,
} from '../../../test/fixtures'
import { AuthProvider } from '../../../lib/auth'
import { createQueryClient } from '../../../lib/query-client'
import { AppRoutes } from '../../AppRoutes'

function renderAt(path = '/admin/audit-log') {
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

// `tenantsMeHandler` is not decoration: without it the navbar's tenant
// switcher fails its own query and renders its own "Retry" button, so a test
// that clicks a page-level Retry by role intermittently finds two. Stubbing
// the shell's query makes that deterministic without changing what any
// assertion below claims.
beforeEach(() => {
  server.use(
    ...authHandlers(),
    tenantsMeHandler([TENANT_A]),
    platformAuditLogHandler(),
  )
  // A separate, later .use() call — MSW resolves the first-matching handler
  // among ones added together, and authHandlers() already bundles a
  // non-staff /users/me/ handler; this later call must win.
  server.use(usersMeStaffHandler())
})

describe('AuditLogPage', () => {
  it('shows a loading state, then the audit log', async () => {
    renderAt()
    expect(await screen.findByText('Loading audit log')).toBeInTheDocument()

    expect(
      await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary),
    ).toBeInTheDocument()
    // Both fixture rows share the same actor — assert at least one shows.
    expect(screen.getAllByText('operator@example.com').length).toBeGreaterThan(0)
  })

  it('shows an empty state', async () => {
    server.use(platformAuditLogHandler([]))
    renderAt()
    expect(
      await screen.findByText('No audit events match these filters.'),
    ).toBeInTheDocument()
  })

  it('shows an error state with a working retry', async () => {
    let calls = 0
    server.use(
      http.get(apiUrl('/platform/audit-log/'), () => {
        calls += 1
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(paginated(PLATFORM_AUDIT_EVENTS))
      }),
    )
    renderAt()
    expect(await screen.findByText('Couldn’t load the audit log.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)).toBeInTheDocument()
  })

  it('shows a Critical badge for a critical row and Observational for the other', async () => {
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)
    expect(screen.getByText('Critical')).toBeInTheDocument()
    expect(screen.getByText('Observational')).toBeInTheDocument()
  })

  it('shows the human-readable summary, actor, action, and target for each row', async () => {
    renderAt()
    const row = PLATFORM_AUDIT_EVENTS[0]
    const summaryCell = await screen.findByText(row.summary)
    const tableRow = summaryCell.closest('tr') as HTMLElement
    expect(within(tableRow).getByText(row.actor!.email)).toBeInTheDocument()
    expect(within(tableRow).getByText(row.action)).toBeInTheDocument()
    expect(
      within(tableRow).getByText(`${row.target_type}:${row.target_id}`),
    ).toBeInTheDocument()
  })

  it('never renders a password, secret, or raw_payload even if present on the wire', async () => {
    server.use(
      http.get(apiUrl('/platform/audit-log/'), () =>
        HttpResponse.json(
          paginated([
            {
              ...PLATFORM_AUDIT_EVENTS[0],
              metadata: { ...PLATFORM_AUDIT_EVENTS[0].metadata, password: 'hunter2' },
            },
          ]),
        ),
      ),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)
    expect(document.body.textContent).not.toContain('hunter2')
  })

  it('Next is disabled with no further page, enabled once one exists, and requests it', async () => {
    let seenPage: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/audit-log/'), ({ request }) => {
        seenPage = new URL(request.url).searchParams.get('page')
        return HttpResponse.json({
          count: 30,
          next: seenPage ? null : 'http://testserver/api/platform/audit-log/?page=2',
          previous: seenPage ? 'http://testserver/api/platform/audit-log/?page=1' : null,
          results: PLATFORM_AUDIT_EVENTS,
        })
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)

    const nextButton = screen.getByRole('button', { name: 'Next' })
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(nextButton).toBeEnabled()

    await userEvent.click(nextButton)
    expect(seenPage).toBe('2')
    expect(await screen.findByText('Page 2 · 30 total')).toBeInTheDocument()
  })

  it('changing a filter resets to page 1', async () => {
    let seenPage: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/audit-log/'), ({ request }) => {
        seenPage = new URL(request.url).searchParams.get('page')
        return HttpResponse.json({
          count: 30,
          next: 'http://testserver/api/platform/audit-log/?page=2',
          previous: null,
          results: PLATFORM_AUDIT_EVENTS,
        })
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Page 2 · 30 total')

    await userEvent.selectOptions(screen.getByLabelText('Target type'), 'Subscription')
    await screen.findByText('Page 1 · 30 total')
    expect(seenPage).toBeNull()
  })

  it('filters by action', async () => {
    let seenAction: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/audit-log/'), ({ request }) => {
        seenAction = new URL(request.url).searchParams.get('action')
        return HttpResponse.json(paginated(PLATFORM_AUDIT_EVENTS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)

    await userEvent.selectOptions(
      screen.getByLabelText('Action'),
      'webhook.sweep_triggered',
    )
    expect(seenAction).toBe('webhook.sweep_triggered')
  })

  it('filters by target type', async () => {
    let seenTargetType: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/audit-log/'), ({ request }) => {
        seenTargetType = new URL(request.url).searchParams.get('target_type')
        return HttpResponse.json(paginated(PLATFORM_AUDIT_EVENTS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)

    await userEvent.selectOptions(screen.getByLabelText('Target type'), 'Subscription')
    expect(seenTargetType).toBe('Subscription')
  })

  it('filters by critical severity', async () => {
    let seenCritical: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/audit-log/'), ({ request }) => {
        seenCritical = new URL(request.url).searchParams.get('is_critical')
        return HttpResponse.json(paginated(PLATFORM_AUDIT_EVENTS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)

    await userEvent.selectOptions(screen.getByLabelText('Severity'), 'true')
    expect(seenCritical).toBe('true')
  })

  it('filters by actor id', async () => {
    let seenActor: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/audit-log/'), ({ request }) => {
        seenActor = new URL(request.url).searchParams.get('actor')
        return HttpResponse.json(paginated(PLATFORM_AUDIT_EVENTS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)

    await userEvent.type(screen.getByLabelText('Actor id'), 'staff-1')
    expect(seenActor).toBe('staff-1')
  })

  it('never sends X-Tenant-ID', async () => {
    let tenantHeader: string | null = 'unset'
    server.use(
      http.get(apiUrl('/platform/audit-log/'), ({ request }) => {
        tenantHeader = request.headers.get('x-tenant-id')
        return HttpResponse.json(paginated(PLATFORM_AUDIT_EVENTS))
      }),
    )
    renderAt()
    await screen.findByText(PLATFORM_AUDIT_EVENTS[0].summary)
    expect(tenantHeader).toBeNull()
  })
})

describe('AuditLogPage — scheduled runs (Phase 6)', () => {
  it('labels a machine-run entry rather than showing a bare dash', async () => {
    server.use(
      platformAuditLogHandler([
        {
          id: 'ae-sched',
          actor: null,
          action: 'scheduled.webhook_sweep',
          target_type: 'ScheduledTask',
          target_id: 'scheduled.webhook_sweep',
          summary: 'Scheduled webhook sweep: 3 checked, 2 processed',
          metadata: { total: 3, processed: 2, deferred: 1, failed: 0 },
          is_critical: false,
          created_at: '2026-03-05T00:00:00Z',
        },
      ]),
    )
    renderAt()

    expect(
      await screen.findByText('Scheduled webhook sweep: 3 checked, 2 processed'),
    ).toBeInTheDocument()
    // "Scheduled", not "—": a null actor on a scheduled run means no human was
    // involved, which is a different fact from a deleted account.
    expect(screen.getAllByText('Scheduled').length).toBeGreaterThan(0)
  })

  it('still shows a dash for a row whose actor account is gone', async () => {
    server.use(
      platformAuditLogHandler([
        {
          id: 'ae-orphan',
          actor: null,
          action: 'plan.created',
          target_type: 'Plan',
          target_id: 'plan-1',
          summary: 'Created plan SCALE (Scale)',
          metadata: {},
          is_critical: true,
          created_at: '2026-03-05T00:00:00Z',
        },
      ]),
    )
    renderAt()

    await screen.findByText('Created plan SCALE (Scale)')
    expect(screen.queryByText('Scheduled')).not.toBeInTheDocument()
  })
})
