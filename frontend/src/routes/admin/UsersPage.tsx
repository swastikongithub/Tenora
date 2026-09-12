/**
 * /admin/users — every user in the system.
 *
 * Phase 4 adds the Root-only operator-roster controls
 * (docs/operator-control-plane-spec.md §D: "role controls rendered only for a
 * Root-tier viewer — UX only, server enforces the real boundary"). They live
 * here rather than on a separate page because the spec is explicit that
 * surfaces are never duplicated: this list already answers "who are the
 * operators", and the controls belong next to that answer.
 *
 * A Staff-tier viewer sees exactly the Phase 1 page — no roles column, no
 * buttons. That hiding is presentation, not security: PATCH
 * /api/platform/users/detail/ is gated by IsPlatformRoot server-side and
 * answers 403 to a Staff caller who constructs the request by hand.
 */

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Alert, Badge, Button, Input, Skeleton, Table } from '../../components'
import type { Column } from '../../components'
import { useCurrentUser } from '../../components/layout/use-current-user'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-error'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { toSearchParams } from './query-params'
import { UserRoleModal } from './UserRoleModal'
import type { RoleFlags, RoleTarget } from './UserRoleModal'

interface PlatformUser {
  id: string
  email: string
  is_staff: boolean
  is_superuser: boolean
  is_active: boolean
  email_verified: boolean
  date_joined: string
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const baseColumns: Array<Column<PlatformUser>> = [
  { key: 'email', header: 'Email' },
  {
    key: 'is_staff',
    header: 'Staff',
    render: (u) => (u.is_staff ? <Badge variant="success">Staff</Badge> : '—'),
  },
  {
    key: 'is_superuser',
    header: 'Root',
    render: (u) => (u.is_superuser ? <Badge variant="warning">Root</Badge> : '—'),
  },
  {
    key: 'is_active',
    header: 'Active',
    render: (u) => (
      <Badge variant={u.is_active ? 'success' : 'neutral'}>
        {u.is_active ? 'Active' : 'Disabled'}
      </Badge>
    ),
  },
  { key: 'date_joined', header: 'Joined', render: (u) => formatDate(u.date_joined) },
]

function messageFor(cause: unknown): string {
  return cause instanceof ApiError
    ? cause.message
    : 'Something went wrong. Please try again.'
}

function isRootUser(u: {
  is_staff: boolean
  is_superuser: boolean
  is_active: boolean
}): boolean {
  return u.is_staff && u.is_superuser && u.is_active
}

export function UsersPage() {
  const queryClient = useQueryClient()
  const { isRoot, email: myEmail } = useCurrentUser()

  const [search, setSearch] = useState('')
  const [isStaff, setIsStaff] = useState<'' | 'true' | 'false'>('')
  const [target, setTarget] = useState<RoleTarget | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const params = { search: search || undefined, is_staff: isStaff || undefined }
  const users = useQuery({
    queryKey: queryKeys.platformUsers(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<PlatformUser>>(
        `/platform/users/${toSearchParams(params)}`,
      ),
  })

  const rows = users.data?.results ?? []
  // Counted from the page currently loaded, so it is a floor, not a census —
  // which is the safe direction for a UX pre-check: it can only be too
  // cautious, never too permissive, and the server's own invariant is the
  // actual guarantee either way.
  const activeRootCount = rows.filter(isRootUser).length

  async function applyRoles(changes: Partial<RoleFlags>) {
    if (!target) return
    setSubmitting(true)
    setActionError(null)
    try {
      await apiClient.patch(`/platform/users/detail/?id=${target.id}`, changes)
      setSubmitting(false)
      setTarget(null)
      void queryClient.invalidateQueries({
        queryKey: ['global', 'platform', 'users'],
      })
      // An operator who just changed their OWN flags is looking at a stale
      // identity everywhere else in the shell until this refetches.
      void queryClient.invalidateQueries({ queryKey: queryKeys.currentUser() })
    } catch (cause) {
      setSubmitting(false)
      setActionError(messageFor(cause))
    }
  }

  const columns: Array<Column<PlatformUser>> = isRoot
    ? [
        ...baseColumns,
        {
          key: 'roles',
          header: 'Roles',
          render: (u) => (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setActionError(null)
                setTarget({
                  id: u.id,
                  email: u.email,
                  is_staff: u.is_staff,
                  is_superuser: u.is_superuser,
                  is_active: u.is_active,
                })
              }}
            >
              Change roles
            </Button>
          ),
        },
      ]
    : baseColumns

  return (
    <div>
      <h2 className="text-h2 text-primary">Users</h2>

      {isRoot && (
        <p className="mt-1 max-w-[46rem] text-body text-secondary">
          Root controls. Staff runs the control plane day to day; root is
          reserved for changing who has power. No mutation may leave the
          platform without an active root operator.
        </p>
      )}

      {actionError && !target && (
        <Alert variant="danger" className="mt-4">
          {actionError}
        </Alert>
      )}

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <Input
          label="Search"
          placeholder="Email"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-56"
        />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="user-staff-filter" className="text-label text-secondary">
            Platform staff
          </label>
          <select
            id="user-staff-filter"
            value={isStaff}
            onChange={(e) => setIsStaff(e.target.value as '' | 'true' | 'false')}
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            <option value="true">Staff only</option>
            <option value="false">Non-staff only</option>
          </select>
        </div>
      </div>

      <div className="mt-6">
        {users.isPending ? (
          <Skeleton count={6} height={52} label="Loading users" />
        ) : users.isError ? (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => users.refetch()}>
                Retry
              </Button>
            }
          >
            Couldn’t load users.
          </Alert>
        ) : rows.length > 0 ? (
          <Table
            caption="Users"
            columns={columns}
            rows={rows}
            rowKey={(u) => u.id}
            renderMobileCard={(u) => (
              <>
                <span className="block text-label text-primary">{u.email}</span>
                {u.is_staff && <Badge variant="success">Staff</Badge>}
              </>
            )}
          />
        ) : (
          <p className="text-body text-secondary">No users match these filters.</p>
        )}
      </div>

      <UserRoleModal
        open={target !== null}
        target={target}
        isSelf={Boolean(target && myEmail && target.email === myEmail)}
        activeRootCount={activeRootCount}
        submitting={submitting}
        error={actionError}
        onSubmit={applyRoles}
        onClose={() => setTarget(null)}
      />
    </div>
  )
}
