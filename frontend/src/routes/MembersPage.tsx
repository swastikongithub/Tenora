/**
 * Members — UI spec §C.4 Page 3. The page that makes RBAC visible: an OWNER sees
 * an "Add member" action a MEMBER does not, and the server enforces that
 * regardless of what renders here.
 *
 * The list is `GET /api/memberships/`, tenant-scoped under
 * `queryKeys.members(currentTenantId)` (the C2 §4.3 key convention) — so
 * switching tenant swaps to a different cache entry and refetches, never showing
 * the previous tenant's members. The add-member modal calls
 * `POST /api/memberships/` (OWNER only) and on success invalidates that key.
 *
 * "Empty" is treated as an error, not a cheerful empty state: a tenant always
 * has at least its creating OWNER, so a zero-length list means something is
 * wrong (§4.1).
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Alert, Badge, Button, Skeleton, Table } from '../components'
import type { Column } from '../components'
import { apiClient } from '../lib/api-client'
import { queryKeys } from '../lib/query-keys'
import { useTenant, type TenantRole } from '../lib/tenant'
import { AddMemberModal } from './AddMemberModal'

export interface Member {
  id: string
  email: string
  role: TenantRole
  created_at: string
}

function formatJoined(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
}

function roleBadge(role: TenantRole) {
  return (
    <Badge variant={role === 'OWNER' ? 'accent' : 'neutral'}>{role}</Badge>
  )
}

const columns: Array<Column<Member>> = [
  {
    key: 'email',
    header: 'Email',
    // Cap the width so a very long address ellipsizes instead of shoving the
    // Role / Joined columns off the row (§8).
    render: (m) => (
      <span className="block max-w-[22rem] truncate text-primary" title={m.email}>
        {m.email}
      </span>
    ),
  },
  {
    key: 'role',
    header: 'Role',
    render: (m) => roleBadge(m.role),
  },
  {
    key: 'joined',
    header: 'Joined',
    render: (m) => (
      <span className="whitespace-nowrap">{formatJoined(m.created_at)}</span>
    ),
  },
]

export function MembersPage() {
  const { currentTenant, currentTenantId } = useTenant()
  // Client-side gating of "Add member" is UX only — the server's IsTenantOwner
  // is the real boundary and rejects a MEMBER's POST regardless of what renders.
  const isOwner = currentTenant?.role === 'OWNER'

  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: queryKeys.members(currentTenantId ?? '∅'),
    queryFn: () => apiClient.get<Member[]>('/memberships/'),
    enabled: currentTenantId != null,
  })

  const isEmpty = data != null && data.length === 0

  function handleAdded() {
    // A refetch, not an optimistic insert: an infrequent action, and this keeps
    // the row order / shape authoritative from the server.
    void queryClient.invalidateQueries({
      queryKey: queryKeys.members(currentTenantId ?? '∅'),
    })
    setModalOpen(false)
  }

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-display text-primary">Members</h1>
        {isOwner && currentTenantId && (
          <Button onClick={() => setModalOpen(true)}>Add member</Button>
        )}
      </div>
      <p className="mt-1 text-body text-secondary">
        Everyone who belongs to this workspace.
      </p>

      <div className="mt-6">
        {!currentTenantId ? (
          <Alert variant="info">
            <Link
              to="/workspace"
              className="font-medium text-accent-500 underline-offset-2 hover:underline"
            >
              Choose a workspace
            </Link>{' '}
            to see its members.
          </Alert>
        ) : isPending ? (
          <Skeleton count={5} height={52} label="Loading members" />
        ) : isError || isEmpty ? (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => refetch()}>
                Retry
              </Button>
            }
          >
            {isEmpty
              ? 'No members came back for this workspace — that shouldn’t happen. Try reloading.'
              : 'Couldn’t load this workspace’s members.'}
          </Alert>
        ) : (
          <Table
            caption="Workspace members"
            columns={columns}
            rows={data}
            rowKey={(m) => m.id}
            renderMobileCard={(m) => (
              <>
                <span className="block truncate text-label text-primary">
                  {m.email}
                </span>
                <span className="mt-2 flex items-center gap-2 text-caption text-secondary">
                  {roleBadge(m.role)}
                  <span>Joined {formatJoined(m.created_at)}</span>
                </span>
              </>
            )}
          />
        )}
      </div>

      {currentTenantId && (
        <AddMemberModal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          onAdded={handleAdded}
        />
      )}
    </section>
  )
}
