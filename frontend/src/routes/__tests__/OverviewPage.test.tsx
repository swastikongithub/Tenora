import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../../test/msw/server'
import {
  authHandlers,
  apiUrl,
  currentSubscriptionByTenantHandler,
  currentSubscriptionHandler,
  logoutHandler,
  MEMBERS_A,
  MEMBERS_B,
  membershipsByTenantHandler,
  membershipsHandler,
  PLAN_PRO,
  PLAN_TEAM,
  subscriptionFor,
  TENANT_A,
  TENANT_B,
  tenantsMeHandler,
  usersMeHandler,
} from '../../test/fixtures'
import { AuthProvider } from '../../lib/auth'
import { setCurrentTenantId } from '../../lib/tenant'
import { createQueryClient } from '../../lib/query-client'
import { AppRoutes } from '../AppRoutes'

/** Render the app at /overview. `asTenant` picks the active tenant (and so the
 *  caller's role): TENANT_A → OWNER, TENANT_B → MEMBER. */
function renderOverview(asTenant = TENANT_A) {
  sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
  localStorage.setItem('billing.last_tenant_id', asTenant.id)
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/overview']}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

/**
 * The redesigned Overview is an editorial document: an `<h1>` masthead
 * statement, a machine `<Readout>` line, then three numbered `<Section>`s
 * (`<h2>` Team / Plan / Workspace). Scope assertions to a section by its
 * heading — the nav repeats some of these words as link text, so match by
 * heading role, not bare text.
 */
async function sectionFor(name: string | RegExp): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { level: 2, name })
  const section = heading.closest('section')
  if (!section) throw new Error(`No <section> for heading "${name}"`)
  return section as HTMLElement
}

/** The masthead lives above the sections — find it via the page's single h1. */
async function masthead(): Promise<HTMLElement> {
  const h1 = await screen.findByRole('heading', { level: 1 })
  const header = h1.closest('header')
  if (!header) throw new Error('No masthead <header>')
  return header as HTMLElement
}

beforeEach(() => {
  setCurrentTenantId(null)
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('OverviewPage — masthead + readout', () => {
  it('states the subscription status, and the readout carries plan price + renewal + team size', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      membershipsHandler(MEMBERS_A),
    )
    renderOverview(TENANT_A)

    // The machine readout: status label + price + renewal.
    expect(await screen.findByText('Active')).toBeInTheDocument()
    expect(screen.getByText(/29\.00 \/ month/)).toBeInTheDocument()
    expect(screen.getByText(/Renews .*2026/)).toBeInTheDocument()

    // The stated primary fact, with the plan name and the semantic status word.
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1).toHaveTextContent('Pro')
    expect(h1).toHaveTextContent(/active/i)
    // The status explanation (STATUS_EXPLANATION) renders as the lede.
    expect(
      within(await masthead()).getByText(/renews automatically/),
    ).toBeInTheDocument()

    // Team size lives in the Team section's aside.
    const team = await sectionFor('Team')
    expect(within(team).getByText('2')).toBeInTheDocument()
  })

  it('uses no decorative emphasis — no featured gradient or accent glow in the content', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      membershipsHandler(MEMBERS_A),
    )
    const { container } = renderOverview(TENANT_A)

    await screen.findByText('Active')
    const main = container.querySelector('main') as HTMLElement
    expect(
      main.querySelectorAll('.shadow-accent-glow, .bg-featured'),
    ).toHaveLength(0)
    // The one place semantic colour enters the masthead: the status word.
    expect(main.querySelector('h1 .text-success')).not.toBeNull()
  })

  it('reads a CANCELED subscription as ended, never as an upcoming renewal', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'CANCELED')),
      membershipsHandler(MEMBERS_A),
    )
    renderOverview(TENANT_A)

    expect(await screen.findByText('Canceled')).toBeInTheDocument()
    expect(
      screen.getByText(/subscription has ended and can.t be restarted/),
    ).toBeInTheDocument()
    // No "renews" language anywhere.
    expect(screen.queryByText(/renew/i)).not.toBeInTheDocument()
    // The readout and the Plan section frame the period as ended.
    expect(screen.getByText(/^Ended /)).toBeInTheDocument()
    const plan = await sectionFor('Plan')
    expect(within(plan).getByText('Period ended')).toBeInTheDocument()
  })
})

describe('OverviewPage — 404 empty state', () => {
  it('OWNER sees "No subscription yet" with a Choose-a-plan link; Team is unaffected', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(null),
      membershipsHandler(MEMBERS_A),
    )
    renderOverview(TENANT_A)

    expect(await screen.findByText('No subscription yet.')).toBeInTheDocument()
    expect(
      screen.getAllByRole('link', { name: 'Choose a plan' })[0],
    ).toHaveAttribute('href', '/subscription')
    // No subscription-derived detail.
    expect(screen.queryByText(/29\.00/)).not.toBeInTheDocument()
    expect(screen.queryByText('Current period')).not.toBeInTheDocument()
    // Team (membership-derived) is unaffected — no subscription does not mean
    // no team (§8).
    const team = await sectionFor('Team')
    expect(within(team).getByText('2')).toBeInTheDocument()
  })

  it('MEMBER sees an informational message with no action', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_B]),
      currentSubscriptionHandler(null),
      membershipsHandler(MEMBERS_B),
    )
    renderOverview(TENANT_B)

    expect(await screen.findByText('No subscription yet.')).toBeInTheDocument()
    expect(
      screen.getByText(/An owner of this workspace can start one\./),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'Choose a plan' }),
    ).not.toBeInTheDocument()
  })
})

describe('OverviewPage — Team section', () => {
  it('shows up to 5 members with role badges and a working "View all" link', async () => {
    const many = Array.from({ length: 7 }, (_, i) => ({
      id: `m-${i}`,
      email: `person${i}@alpha.test`,
      role: (i === 0 ? 'OWNER' : 'MEMBER') as 'OWNER' | 'MEMBER',
      created_at: '2026-01-05T00:00:00Z',
    }))
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      membershipsHandler(many),
    )
    renderOverview(TENANT_A)

    const team = await sectionFor('Team')
    expect(
      await within(team).findByText('person0@alpha.test'),
    ).toBeInTheDocument()
    expect(within(team).getByText('person4@alpha.test')).toBeInTheDocument()
    expect(
      within(team).queryByText('person5@alpha.test'),
    ).not.toBeInTheDocument()
    expect(
      within(team).getByRole('link', { name: 'View all' }),
    ).toHaveAttribute('href', '/members')
  })

  it('treats an empty membership list as a fault, not a friendly empty state', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      membershipsHandler([]),
    )
    renderOverview(TENANT_A)

    expect(
      await screen.findByText(
        'No members came back for this workspace — that shouldn’t happen. Try reloading.',
      ),
    ).toBeInTheDocument()
  })
})

describe('OverviewPage — Plan section', () => {
  it('shows the current plan and a Change plan link for OWNER only', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      membershipsHandler(MEMBERS_A),
    )
    renderOverview(TENANT_A)

    const plan = await sectionFor('Plan')
    await waitFor(() =>
      expect(within(plan).getByText(/billed monthly/)).toBeInTheDocument(),
    )
    expect(within(plan).getByText('Pro')).toBeInTheDocument()
    expect(
      within(plan).getByRole('link', { name: 'Change plan' }),
    ).toHaveAttribute('href', '/subscription')
  })

  it('hides Change plan for a MEMBER', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_B]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      membershipsHandler(MEMBERS_B),
    )
    renderOverview(TENANT_B)

    const plan = await sectionFor('Plan')
    await waitFor(() =>
      expect(within(plan).getByText(/billed monthly/)).toBeInTheDocument(),
    )
    expect(
      within(plan).queryByRole('link', { name: 'Change plan' }),
    ).not.toBeInTheDocument()
  })
})

describe('OverviewPage — Workspace section', () => {
  it('shows name, slug, created date, role + role explanation, and membership-derived "Member since"', async () => {
    server.use(
      http.post(apiUrl('/auth/login/'), () =>
        HttpResponse.json({ access: 'test-access', refresh: 'test-refresh' }),
      ),
      http.post(apiUrl('/auth/refresh/'), () =>
        HttpResponse.json({ access: 'test-access-2', refresh: 'test-refresh-2' }),
      ),
      usersMeHandler({ id: 'm-a1', email: 'owner@alpha.test' }),
      logoutHandler(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      membershipsHandler(MEMBERS_A),
    )
    renderOverview(TENANT_A)

    const ws = await sectionFor('Workspace')
    expect(await within(ws).findByText('Alpha Corp')).toBeInTheDocument()
    expect(within(ws).getByText('alpha')).toBeInTheDocument()
    expect(within(ws).getByText('OWNER')).toBeInTheDocument()
    expect(
      within(ws).getByText(/Can add members and manage/),
    ).toBeInTheDocument()
    // MEMBERS_A's first row (owner@alpha.test) matches the viewer's own email
    // from /users/me/ — a real Membership.created_at.
    await waitFor(() =>
      expect(within(ws).getByText('Member since')).toBeInTheDocument(),
    )
    expect(
      within(ws).getAllByText((t) => /\bJan\b/.test(t) && t.includes('2026'))
        .length,
    ).toBeGreaterThanOrEqual(1)
  })

  it('omits "Member since" (rather than showing a wrong date) when memberships fails to load', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO)),
      http.get(apiUrl('/memberships/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderOverview(TENANT_A)

    await screen.findByText('Active')
    const ws = await sectionFor('Workspace')
    expect(within(ws).queryByText('Member since')).not.toBeInTheDocument()
  })
})

describe('OverviewPage — per-query failure isolation (signature test)', () => {
  it('a subscription failure affects only subscription-derived content', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      http.get(apiUrl('/subscriptions/current/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
      membershipsHandler(MEMBERS_A),
    )
    renderOverview(TENANT_A)

    // The Masthead carries the primary error + the Retry.
    expect(
      await screen.findByText('Couldn’t load this workspace’s subscription.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    // The Plan section fails with it (same query) — quietly, no second Retry.
    const plan = await sectionFor('Plan')
    expect(within(plan).getByText(/Unavailable — retry above/)).toBeInTheDocument()
    expect(
      within(plan).queryByRole('button', { name: 'Retry' }),
    ).not.toBeInTheDocument()

    // Membership-derived content is unaffected: real count and real rows.
    const team = await sectionFor('Team')
    expect(within(team).getByText('2')).toBeInTheDocument()
    expect(within(team).getByText('owner@alpha.test')).toBeInTheDocument()
    expect(within(team).getByText('ada@alpha.test')).toBeInTheDocument()
    // Tenant-context content is unaffected.
    const ws = await sectionFor('Workspace')
    expect(within(ws).getByText('Alpha Corp')).toBeInTheDocument()
  })

  it('a membership failure affects only membership-derived content', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(PLAN_PRO, 'ACTIVE')),
      http.get(apiUrl('/memberships/'), () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderOverview(TENANT_A)

    // Subscription-derived content shows real data.
    expect(await screen.findByText('Active')).toBeInTheDocument()
    expect(screen.getByText(/29\.00 \/ month/)).toBeInTheDocument()
    const plan = await sectionFor('Plan')
    expect(within(plan).getByText('Pro')).toBeInTheDocument()

    // The Team section shows its own isolated failure.
    const team = await sectionFor('Team')
    expect(
      within(team).getByText('Couldn’t load this workspace’s members.'),
    ).toBeInTheDocument()
  })
})

describe('OverviewPage — tenant switch', () => {
  it('every section refetches and reflects the new tenant, with no old-tenant value left behind', async () => {
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A, TENANT_B]),
      currentSubscriptionByTenantHandler({
        [TENANT_A.id]: subscriptionFor(PLAN_PRO, 'ACTIVE'),
        [TENANT_B.id]: subscriptionFor(PLAN_TEAM, 'TRIALING'),
      }),
      membershipsByTenantHandler({
        [TENANT_A.id]: MEMBERS_A,
        [TENANT_B.id]: MEMBERS_B,
      }),
    )
    renderOverview(TENANT_A)

    expect(await screen.findByText('Active')).toBeInTheDocument()
    expect(within(await sectionFor('Team')).getByText('2')).toBeInTheDocument()
    expect(within(await sectionFor('Plan')).getByText('Pro')).toBeInTheDocument()

    await userEvent.click(
      screen.getByRole('button', { name: new RegExp(TENANT_A.name) }),
    )
    await userEvent.click(
      await screen.findByRole('menuitemradio', {
        name: new RegExp(TENANT_B.name),
      }),
    )

    await waitFor(async () => {
      expect(
        within(await sectionFor('Team')).getByText('1'),
      ).toBeInTheDocument()
    })
    expect(await screen.findByText('Trialing')).toBeInTheDocument()
    expect(within(await sectionFor('Plan')).getByText('Team')).toBeInTheDocument()

    // No stale Tenant A value survives under Tenant B.
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
    expect(screen.queryByText('owner@alpha.test')).not.toBeInTheDocument()
    expect(screen.getByText('owner@beta.test')).toBeInTheDocument()
  })
})

describe('OverviewPage — long names', () => {
  it('presents a very long plan name gracefully (truncated where shown in a row, no overflow)', async () => {
    const longPlan = {
      ...PLAN_PRO,
      name: 'An Extremely Long Plan Name That Should Never Wrap Or Overflow Its Row',
    }
    server.use(
      ...authHandlers(),
      tenantsMeHandler([TENANT_A]),
      currentSubscriptionHandler(subscriptionFor(longPlan, 'ACTIVE')),
      membershipsHandler(MEMBERS_A),
    )
    renderOverview(TENANT_A)

    await screen.findByText('Active')

    // In the Plan spec-sheet the name is truncated with a title attribute so it
    // can never shove the layout.
    const plan = await sectionFor('Plan')
    const nameCell = await within(plan).findByTitle(longPlan.name)
    expect(nameCell).toHaveClass('truncate')
    // The masthead statement still contains the name (a headline wraps, it does
    // not overflow).
    expect(screen.getByRole('heading', { level: 1 }).textContent).toContain(
      longPlan.name,
    )
  })
})
