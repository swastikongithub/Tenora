/**
 * The notification center (plan §25, §43.6) and the invitation control point:
 * an invitation is accepted or declined HERE, by the invited user. Global data
 * (the caller's own notifications), so no X-Tenant-ID and global cache keys.
 *
 * Accepting refreshes the workspace list, so the new workspace appears in the
 * switcher with the resident navigation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert, Badge, Button, EmptyState } from '../components'
import { apiClient } from '../lib/api-client'
import { formatDay } from '../lib/property/format'
import type { AppNotification, Invitation, Paginated } from '../lib/property/types'
import { queryKeys } from '../lib/query-keys'
import { useTenant } from '../lib/tenant'
import { PageHeader, QueryState, Section } from './property/ui'
import { errorMessage } from '../lib/property/errors'

function destination(n: AppNotification): string | null {
  if (n.data.bill_id) return `/bills/${n.data.bill_id}`
  if (n.data.receipt_id) return `/receipts/${n.data.receipt_id}`
  if (n.kind === 'OVERDUE_SUMMARY') return '/billing/aging'
  if (n.kind === 'CYCLE_INCOMPLETE') return '/billing'
  if (n.kind === 'INVITATION_ACCEPTED' || n.kind === 'MEMBER_LEFT') return '/residents'
  return null
}

export function NotificationsPage() {
  const queryClient = useQueryClient()
  const { switchTenant, tenants } = useTenant()
  const [justAccepted, setJustAccepted] = useState<string | null>(null)
  const notifications = useQuery({
    queryKey: queryKeys.notifications(),
    queryFn: () => apiClient.get<Paginated<AppNotification>>('/notifications/'),
  })
  const invitations = useQuery({
    queryKey: queryKeys.myInvitations(),
    queryFn: () => apiClient.get<Invitation[]>('/invitations/mine/'),
  })
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['global', 'notifications'] })
    queryClient.invalidateQueries({ queryKey: queryKeys.myInvitations() })
  }
  const respond = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'accept' | 'decline' }) =>
      apiClient.post<Invitation>('/invitations/respond/', { id, action }),
    onSuccess: (invitation) => {
      refresh()
      if (invitation.status === 'ACCEPTED') {
        setJustAccepted(invitation.tenant_id)
        queryClient.invalidateQueries({ queryKey: queryKeys.tenantsMe() })
      }
    },
  })
  const markAll = useMutation({
    mutationFn: () => apiClient.post('/notifications/read/', { all: true }),
    onSuccess: refresh,
  })
  const markOne = useMutation({
    mutationFn: (id: string) => apiClient.post('/notifications/read/', { ids: [id] }),
    onSuccess: refresh,
  })
  const pending = invitations.data?.filter((i) => i.status === 'PENDING') ?? []
  const answered = invitations.data?.filter((i) => i.status !== 'PENDING') ?? []
  const acceptedTenantReady = justAccepted && tenants.some((t) => t.id === justAccepted)

  return (
    <div className="max-w-[760px]">
      <PageHeader
        title="Notifications"
        actions={
          <Button size="sm" variant="secondary" onClick={() => markAll.mutate()} loading={markAll.isPending}>
            Mark all as read
          </Button>
        }
      />

      <Section title="Invitations">
        <QueryState isLoading={invitations.isLoading} error={invitations.error} onRetry={() => invitations.refetch()} label="invitations" />
        {respond.error && <Alert variant="danger" className="mb-3">{errorMessage(respond.error)}</Alert>}
        {acceptedTenantReady && (
          <Alert
            variant="success"
            className="mb-3"
            action={
              <Button size="sm" onClick={() => switchTenant(justAccepted)}>
                Open workspace
              </Button>
            }
          >
            You joined the workspace as a resident.
          </Alert>
        )}
        {pending.length === 0 && invitations.data && <p className="text-body text-secondary">No pending invitations.</p>}
        <ul className="flex flex-col gap-3">
          {pending.map((inv) => (
            <li key={inv.id} className="rounded-lg border border-accent-600 bg-raised p-4" aria-label={`Invitation from ${inv.tenant_name}`}>
              <p className="text-label font-medium text-primary">{inv.tenant_name} invited you to join as a resident</p>
              <p className="mt-1 text-caption text-secondary">
                {inv.unit_identifier ? `Unit ${inv.unit_identifier}, ${inv.property_name} · ` : ''}
                Sent {formatDay(inv.created_at)}
                {inv.invited_by_email ? ` by ${inv.invited_by_email}` : ''} · Expires {formatDay(inv.expires_at)}
              </p>
              {inv.message && <p className="mt-2 text-body text-primary">“{inv.message}”</p>}
              <p className="mt-2 text-caption text-secondary">Nothing changes until you accept. You can leave the workspace later from Settings.</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" loading={respond.isPending} onClick={() => respond.mutate({ id: inv.id, action: 'accept' })}>
                  Accept
                </Button>
                <Button size="sm" variant="secondary" onClick={() => respond.mutate({ id: inv.id, action: 'decline' })}>
                  Decline
                </Button>
              </div>
            </li>
          ))}
        </ul>
        {answered.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1 text-caption text-secondary">
            {answered.slice(0, 10).map((inv) => (
              <li key={inv.id}>
                {inv.tenant_name} · <Badge variant={inv.status === 'ACCEPTED' ? 'success' : 'neutral'}>{inv.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="All notifications">
        <QueryState isLoading={notifications.isLoading} error={notifications.error} onRetry={() => notifications.refetch()} label="notifications" />
        {notifications.data?.results.length === 0 && <EmptyState headline="You’re all caught up" description="Billing, payment and membership events appear here." />}
        <ul className="flex flex-col gap-2">
          {notifications.data?.results.map((n) => {
            const href = destination(n)
            return (
              <li key={n.id} className={`rounded-md border p-3 ${n.read_at ? 'border-subtle' : 'border-strong bg-raised'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-label text-primary">
                      {!n.read_at && <span className="mr-2 inline-block size-2 rounded-full bg-accent-600" aria-label="Unread" />}
                      {n.title}
                    </p>
                    {n.body && <p className="text-caption text-secondary">{n.body}</p>}
                    <p className="text-caption text-secondary">
                      {n.tenant_name ? `${n.tenant_name} · ` : ''}
                      {formatDay(n.created_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {href && n.tenant_id && tenants.some((t) => t.id === n.tenant_id) && (
                      <Link
                        to={href}
                        onClick={() => {
                          if (n.tenant_id) switchTenant(n.tenant_id)
                          if (!n.read_at) markOne.mutate(n.id)
                        }}
                        className="text-label text-accent-500 underline"
                      >
                        Open
                      </Link>
                    )}
                    {!n.read_at && (
                      <Button size="sm" variant="ghost" onClick={() => markOne.mutate(n.id)}>
                        Mark read
                      </Button>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      </Section>
    </div>
  )
}
