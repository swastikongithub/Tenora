/**
 * /admin/users — every user in the system, read-only. No role-management
 * controls in Phase 1 — docs/operator-control-plane-spec.md reserves role
 * management for the Root tier, a later phase.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Input, Skeleton, Table } from '../../components'
import type { Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { toSearchParams } from './query-params'

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

const columns: Array<Column<PlatformUser>> = [
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

export function UsersPage() {
  const [search, setSearch] = useState('')
  const [isStaff, setIsStaff] = useState<'' | 'true' | 'false'>('')

  const params = { search: search || undefined, is_staff: isStaff || undefined }
  const users = useQuery({
    queryKey: queryKeys.platformUsers(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<PlatformUser>>(
        `/platform/users/${toSearchParams(params)}`,
      ),
  })

  return (
    <div>
      <h2 className="text-h2 text-primary">Users</h2>

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
        ) : users.data && users.data.results.length > 0 ? (
          <Table
            caption="Users"
            columns={columns}
            rows={users.data.results}
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
    </div>
  )
}
