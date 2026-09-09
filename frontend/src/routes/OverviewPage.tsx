/**
 * Overview — UI spec §C.4 Page 5, re-composed for the Tenora redesign
 * (design-reference-analysis §4–§10; the approved UI-03 editorial prototype).
 *
 * The DATA and its behaviour are unchanged from the card-grid version:
 *   1. Per-query failure isolation — a failure in one query must not blank
 *      sections driven by the other. There is deliberately no combined
 *      pending/error boolean; every branch reads only its own query's state
 *      (stage-c6-spec.md §1). The subscription query drives the Masthead + the
 *      Plan section; the memberships query drives the Team section; tenant
 *      context drives the Workspace section.
 *   2. Every tenant-scoped query refetches together on tenant switch, via the
 *      key shapes (`queryKeys.currentSubscription` / `queryKeys.members`)
 *      SubscriptionPage and MembersPage established — no new keys.
 *   3. A 404 from `/subscriptions/current/` is the empty state, not an error.
 *   4. The status → semantic-colour mapping is the fixed one (redesign §7):
 *      restyled, never remapped.
 *
 * What changed is the COMPOSITION: no KPI-card row, no card grid. The page
 * STATES its primary fact once (`<Masthead>`, composed `text-edge` register,
 * with the status word carrying semantic colour), a machine `<Readout>` line
 * for the figures, then three numbered `<Section>`s on the bare page ground —
 * Team (the dense `<Table>`), Plan and Workspace (borderless `<DataList>`s).
 * The editorial content (`max-w-[1080px]`) is LEFT-ALIGNED inside AppShell's
 * centred outer frame — its left edge lines up with the navbar wordmark.
 *
 * No fabricated data: every value traces to a real field from
 * GET /subscriptions/current/, GET /memberships/, GET /tenants/me/ (via
 * useTenant()), or GET /users/me/ (via useCurrentUser()).
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import {
  Alert,
  Badge,
  Button,
  DataList,
  Masthead,
  Overline,
  Readout,
  Section,
  Skeleton,
  Table,
} from '../components'
import type { Column, ReadoutTone } from '../components'
import { apiClient } from '../lib/api-client'
import { ApiError } from '../lib/api-error'
import { formatDate, formatMoney, formatRelativeDate } from '../lib/format'
import { queryKeys } from '../lib/query-keys'
import { useTenant } from '../lib/tenant'
import { useCurrentUser } from '../components/layout/use-current-user'
import type { Member } from './MembersPage'
import type { Subscription, SubscriptionStatus } from './SubscriptionPage'

// Copied from SubscriptionPage.tsx (source of truth) rather than imported —
// stage-c6-spec.md §11 forbids modifying that file, and its maps are
// module-private. Keep in sync with SubscriptionPage.tsx if its status
// vocabulary ever changes (redesign §7: restyle, never remap — `STATUS_TONE`
// below is the SubscriptionPage `STATUS_VARIANT` mapping minus the unused
// `accent`).
const STATUS_LABEL: Record<SubscriptionStatus, string> = {
  ACTIVE: 'Active',
  TRIALING: 'Trialing',
  PAST_DUE: 'Past due',
  CANCELED: 'Canceled',
}

/** One plain-English line per status — what the state means, not the label. */
const STATUS_EXPLANATION: Record<SubscriptionStatus, string> = {
  TRIALING: 'Free trial — billing hasn’t started yet.',
  ACTIVE: 'Billing is current; the plan renews automatically.',
  PAST_DUE: 'Payment is overdue — billing needs attention.',
  CANCELED: 'This subscription has ended and can’t be restarted.',
}

const INTERVAL_LABEL: Record<Subscription['plan']['interval'], string> = {
  MONTHLY: 'Billed monthly',
  ANNUAL: 'Billed annually',
}

const INTERVAL_SHORT: Record<Subscription['plan']['interval'], string> = {
  MONTHLY: 'month',
  ANNUAL: 'year',
}

const ROLE_EXPLANATION: Record<'OWNER' | 'MEMBER', string> = {
  OWNER: 'Can add members and manage this workspace’s subscription.',
  MEMBER: 'Can view this workspace, its members and its plan.',
}

/** Status → the pulse/readout tone vocabulary (a subset of the Badge variants —
 *  the same mapping, never a remap: redesign §7). */
const STATUS_TONE: Record<SubscriptionStatus, ReadoutTone> = {
  ACTIVE: 'success',
  TRIALING: 'warning',
  PAST_DUE: 'danger',
  CANCELED: 'neutral',
}

/** Semantic status colour as a text utility — the one place semantic colour
 *  enters the editorial masthead (design-ref §8.3). */
const STATUS_TEXT: Record<ReadoutTone, string> = {
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
  neutral: 'text-neutral',
}

function StatusWord({
  status,
  children,
}: {
  status: SubscriptionStatus
  children: string
}) {
  return <span className={STATUS_TEXT[STATUS_TONE[status]]}>{children}</span>
}

/** The stated primary fact. The status word carries semantic colour; the plan
 *  name is real data and simply flows into the sentence (a long name wraps —
 *  the headline is `text-balance` + width-capped, it cannot overflow). */
function statementFor(status: SubscriptionStatus, planName: string): ReactNode {
  switch (status) {
    case 'ACTIVE':
      return (
        <>
          Billing is <StatusWord status={status}>active</StatusWord> on the{' '}
          {planName} plan.
        </>
      )
    case 'TRIALING':
      return (
        <>
          The {planName} plan is on a{' '}
          <StatusWord status={status}>free trial</StatusWord>.
        </>
      )
    case 'PAST_DUE':
      return (
        <>
          Payment on the {planName} plan is{' '}
          <StatusWord status={status}>past due</StatusWord>.
        </>
      )
    case 'CANCELED':
      return (
        <>
          The {planName} plan has been{' '}
          <StatusWord status={status}>canceled</StatusWord>.
        </>
      )
  }
}

function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono">{children}</span>
}

const memberColumns: Array<Column<Member>> = [
  {
    key: 'email',
    header: 'Member',
    render: (m) => (
      <span
        className="block max-w-[30rem] truncate text-primary"
        title={m.email}
      >
        {m.email}
      </span>
    ),
  },
  {
    key: 'role',
    header: 'Role',
    render: (m) => (
      <Badge variant={m.role === 'OWNER' ? 'accent' : 'neutral'}>{m.role}</Badge>
    ),
  },
  {
    key: 'joined',
    header: 'Joined',
    render: (m) => (
      <span className="whitespace-nowrap font-mono text-caption text-secondary">
        {formatDate(m.created_at)}
      </span>
    ),
  },
]

export function OverviewPage() {
  const { currentTenant, currentTenantId } = useTenant()
  const { email: viewerEmail } = useCurrentUser()
  const isOwner = currentTenant?.role === 'OWNER'

  const {
    data: subscription,
    isPending: subPending,
    isError: subIsError,
    error: subError,
    refetch: refetchSubscription,
  } = useQuery({
    queryKey: queryKeys.currentSubscription(currentTenantId ?? '∅'),
    queryFn: () => apiClient.get<Subscription>('/subscriptions/current/'),
    enabled: currentTenantId != null,
  })

  const {
    data: members,
    isPending: membersPending,
    isError: membersIsError,
    refetch: refetchMembers,
  } = useQuery({
    queryKey: queryKeys.members(currentTenantId ?? '∅'),
    queryFn: () => apiClient.get<Member[]>('/memberships/'),
    enabled: currentTenantId != null,
  })

  // A 404 means "no subscription yet" — an empty state, not a failure. Same
  // rule as SubscriptionPage.tsx, applied independently here so a subscription
  // failure can never be confused with a memberships failure.
  const noSubscription =
    subIsError && subError instanceof ApiError && subError.status === 404
  const subFailed = subIsError && !noSubscription
  const membersEmpty = members != null && members.length === 0
  const membersFailed = membersIsError || membersEmpty

  const viewerMembership = members?.find((m) => m.email === viewerEmail)

  if (!currentTenantId) {
    return (
      <section className="max-w-[1080px]">
        <header className="pt-14 sm:pt-20">
          <Overline as="p" tone="accent">
            Overview
          </Overline>
          <h1 className="mt-4 text-display tracking-edge text-primary sm:text-edge">
            No workspace selected.
          </h1>
          <p className="mt-4 max-w-[38rem] text-body text-secondary">
            <Link
              to="/workspace"
              className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
            >
              Choose a workspace
            </Link>{' '}
            to see its overview.
          </p>
        </header>
      </section>
    )
  }

  return (
    <section className="max-w-[1080px]">
      {/* ---- Masthead — driven by the subscription query ---- */}
      {subPending ? (
        <header className="pt-14 sm:pt-20">
          <Overline as="p" tone="accent">
            Overview
          </Overline>
          <div className="mt-4">
            <Skeleton
              count={1}
              height={40}
              width="80%"
              label="Loading subscription"
            />
          </div>
          <div className="mt-7">
            <Skeleton count={1} height={18} width="55%" />
          </div>
        </header>
      ) : subFailed ? (
        <Masthead
          overline="Overview"
          statement="Subscription details didn’t load."
          lede="Plan, cost and renewal are unavailable until this loads — the rest of the page below is current."
          readout={
            <div className="border-t border-subtle pt-3">
              <Alert
                variant="danger"
                action={
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => refetchSubscription()}
                  >
                    Retry
                  </Button>
                }
              >
                Couldn’t load this workspace’s subscription.
              </Alert>
            </div>
          }
        />
      ) : noSubscription ? (
        <Masthead
          overline="Overview"
          statement="No subscription yet."
          lede={
            isOwner ? (
              <>
                <Link
                  to="/subscription"
                  className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
                >
                  Choose a plan
                </Link>{' '}
                to start billing for this workspace. Nothing is charged before
                then, and the workspace stays fully usable until it is.
              </>
            ) : (
              'An owner of this workspace can start one. Nothing is charged before then, and the workspace stays fully usable.'
            )
          }
        />
      ) : subscription ? (
        <Masthead
          overline="Overview"
          statement={statementFor(subscription.status, subscription.plan.name)}
          lede={STATUS_EXPLANATION[subscription.status]}
          readout={
            <Readout
              items={[
                {
                  value: STATUS_LABEL[subscription.status],
                  tone: STATUS_TONE[subscription.status],
                },
                {
                  value: `${formatMoney(
                    subscription.plan.price_cents,
                    subscription.plan.currency,
                  )} / ${INTERVAL_SHORT[subscription.plan.interval] ?? subscription.plan.interval}`,
                },
                {
                  value:
                    subscription.status === 'CANCELED'
                      ? `Ended ${formatDate(subscription.current_period_end)}`
                      : `Renews ${formatDate(subscription.current_period_end)}`,
                },
              ]}
            />
          }
        />
      ) : null}

      {/* ---- Sections ---- */}
      <div className="mt-14 flex flex-col gap-14">
        {/* 01 — Team. Driven by the memberships query. */}
        <Section
          index="01"
          title="Team"
          aside={
            members && !membersEmpty ? (
              <span className="flex items-center gap-3">
                <span>
                  <span className="num font-mono text-primary">
                    {members.length}
                  </span>{' '}
                  {members.length === 1 ? 'member' : 'members'}
                </span>
                <Link
                  to="/members"
                  className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
                >
                  View all
                </Link>
              </span>
            ) : undefined
          }
        >
          {membersPending ? (
            <Skeleton count={5} height={44} label="Loading members" />
          ) : membersFailed ? (
            <Alert
              variant="danger"
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => refetchMembers()}
                >
                  Retry
                </Button>
              }
            >
              {membersEmpty
                ? 'No members came back for this workspace — that shouldn’t happen. Try reloading.'
                : 'Couldn’t load this workspace’s members.'}
            </Alert>
          ) : (
            <Table
              caption="Workspace members"
              columns={memberColumns}
              rows={members.slice(0, 5)}
              rowKey={(m) => m.id}
              selectedRowKey={viewerMembership?.id}
              renderMobileCard={(m) => (
                <>
                  <span className="block truncate text-label text-primary">
                    {m.email}
                  </span>
                  <span className="mt-1.5 flex items-center gap-2 text-caption text-secondary">
                    <Badge variant={m.role === 'OWNER' ? 'accent' : 'neutral'}>
                      {m.role}
                    </Badge>
                    <span className="font-mono">
                      Joined {formatDate(m.created_at)}
                    </span>
                  </span>
                </>
              )}
            />
          )}
        </Section>

        {/* 02 — Plan. Same subscription query as the Masthead — fails with it. */}
        <Section
          index="02"
          title="Plan"
          aside={
            isOwner && subscription ? (
              <Link
                to="/subscription"
                className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
              >
                Change plan
              </Link>
            ) : undefined
          }
        >
          {subPending ? (
            <Skeleton count={3} height={18} label="Loading plan" />
          ) : subFailed ? (
            // Same query as the Masthead — it fails with it. The Masthead
            // carries the primary error + the Retry; this stays quiet.
            <p className="text-body text-secondary">Unavailable — retry above.</p>
          ) : noSubscription ? (
            <p className="text-body text-secondary">
              No plan yet — an owner can choose one from{' '}
              <Link
                to="/subscription"
                className="rounded-sm font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
              >
                Subscription
              </Link>
              .
            </p>
          ) : subscription ? (
            <DataList
              className="max-w-[42rem]"
              rows={[
                {
                  term: 'Plan',
                  children: (
                    <span
                      className="block max-w-full truncate"
                      title={subscription.plan.name}
                    >
                      {subscription.plan.name}
                    </span>
                  ),
                },
                {
                  term: 'Price',
                  children: (
                    <>
                      <span className="num">
                        {formatMoney(
                          subscription.plan.price_cents,
                          subscription.plan.currency,
                        )}
                      </span>{' '}
                      ·{' '}
                      {(
                        INTERVAL_LABEL[subscription.plan.interval] ??
                        subscription.plan.interval
                      ).toLowerCase()}
                    </>
                  ),
                },
                {
                  term:
                    subscription.status === 'CANCELED'
                      ? 'Period ended'
                      : 'Current period',
                  children: (
                    <span className="font-mono text-caption">
                      {formatDate(subscription.current_period_start)} —{' '}
                      {formatDate(subscription.current_period_end)}
                    </span>
                  ),
                },
              ]}
            />
          ) : null}
        </Section>

        {/* 03 — Workspace. Tenant context — always live. */}
        <Section index="03" title="Workspace">
          <DataList
            className="max-w-[42rem]"
            rows={[
              {
                term: 'Name',
                children: (
                  <span
                    className="block max-w-full truncate"
                    title={currentTenant?.name}
                  >
                    {currentTenant?.name}
                  </span>
                ),
              },
              {
                term: 'Slug',
                children: <Mono>{currentTenant?.slug}</Mono>,
              },
              {
                term: 'Workspace created',
                children: currentTenant ? (
                  <>
                    <span className="font-mono text-caption">
                      {formatDate(currentTenant.created_at)}
                    </span>{' '}
                    <span className="text-secondary">
                      ({formatRelativeDate(currentTenant.created_at)})
                    </span>
                  </>
                ) : (
                  '—'
                ),
              },
              ...(viewerMembership
                ? [
                    {
                      term: 'Member since',
                      children: (
                        <span className="font-mono text-caption">
                          {formatDate(viewerMembership.created_at)}
                        </span>
                      ),
                    },
                  ]
                : []),
              {
                term: 'Your role',
                children: currentTenant ? (
                  <span className="flex flex-col gap-1">
                    <span>
                      <Badge
                        variant={
                          currentTenant.role === 'OWNER' ? 'accent' : 'neutral'
                        }
                      >
                        {currentTenant.role}
                      </Badge>
                    </span>
                    <span className="max-w-prose text-caption text-secondary">
                      {ROLE_EXPLANATION[currentTenant.role]}
                    </span>
                  </span>
                ) : (
                  '—'
                ),
              },
            ]}
          />
        </Section>
      </div>
    </section>
  )
}
