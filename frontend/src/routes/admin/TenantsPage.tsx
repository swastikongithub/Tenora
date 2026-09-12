/**
 * /admin/tenants — every tenant, with `status`/`plan`/`search` filters and a
 * link to each detail page.
 *
 * Read-only: the suspend/reactivate control is Root-tier and lives on the
 * tenant's own detail page, where the operator can see who and what they are
 * taking offline. Since Phase 5 this list does show WHICH tenants are
 * suspended — a workspace column distinct from the subscription-status one,
 * because "suspended by an operator" and "past due at the gateway" are
 * different facts and collapsing them into one badge would hide both.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Input, Skeleton, Table } from '../../components'
import type { BadgeVariant, Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import type { SubscriptionStatus } from '../SubscriptionPage'
import { toSearchParams } from './query-params'

type StatusKey = SubscriptionStatus | 'NONE'

interface PlatformTenant {
  id: string
  name: string
  slug: string
  created_at: string
  is_active: boolean
  member_count: number
  subscription: { plan_name: string; status: SubscriptionStatus } | null
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const STATUS_VARIANT: Record<StatusKey, BadgeVariant> = {
  ACTIVE: 'success',
  TRIALING: 'warning',
  PAST_DUE: 'danger',
  CANCELED: 'neutral',
  NONE: 'neutral',
}

const STATUS_LABEL: Record<StatusKey, string> = {
  ACTIVE: 'Active',
  TRIALING: 'Trialing',
  PAST_DUE: 'Past due',
  CANCELED: 'Canceled',
  NONE: 'No subscription',
}

const columns: Array<Column<PlatformTenant>> = [
  {
    key: 'name',
    header: 'Tenant',
    render: (t) => (
      <Link to={`/admin/tenants/${t.id}`} className="text-primary hover:underline">
        {t.name}
      </Link>
    ),
  },
  { key: 'slug', header: 'Slug', render: (t) => <span className="font-mono">{t.slug}</span> },
  {
    key: 'is_active',
    header: 'Workspace',
    render: (t) => (
      <Badge variant={t.is_active ? 'success' : 'danger'}>
        {t.is_active ? 'Active' : 'Suspended'}
      </Badge>
    ),
  },
  { key: 'member_count', header: 'Members', numeric: true, render: (t) => t.member_count },
  { key: 'plan', header: 'Plan', render: (t) => t.subscription?.plan_name ?? '—' },
  {
    key: 'status',
    header: 'Status',
    render: (t) =>
      t.subscription ? (
        <Badge variant={STATUS_VARIANT[t.subscription.status]}>
          {STATUS_LABEL[t.subscription.status]}
        </Badge>
      ) : (
        <Badge variant="neutral">{STATUS_LABEL.NONE}</Badge>
      ),
  },
  {
    key: 'created_at',
    header: 'Created',
    render: (t) => <span className="whitespace-nowrap">{formatDate(t.created_at)}</span>,
  },
]

export function TenantsPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'' | StatusKey>('')

  const params = { search: search || undefined, status: status || undefined }
  const tenants = useQuery({
    queryKey: queryKeys.platformTenants(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<PlatformTenant>>(
        `/platform/tenants/${toSearchParams(params)}`,
      ),
  })

  return (
    <div>
      <h2 className="text-h2 text-primary">Tenants</h2>

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <Input
          label="Search"
          placeholder="Name or slug"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-56"
        />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="tenant-status-filter" className="text-label text-secondary">
            Subscription status
          </label>
          <select
            id="tenant-status-filter"
            value={status}
            onChange={(e) => setStatus(e.target.value as '' | StatusKey)}
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            {(['ACTIVE', 'TRIALING', 'PAST_DUE', 'CANCELED', 'NONE'] as StatusKey[]).map(
              (key) => (
                <option key={key} value={key}>
                  {STATUS_LABEL[key]}
                </option>
              ),
            )}
          </select>
        </div>
      </div>

      <div className="mt-6">
        {tenants.isPending ? (
          <Skeleton count={6} height={52} label="Loading tenants" />
        ) : tenants.isError ? (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => tenants.refetch()}>
                Retry
              </Button>
            }
          >
            Couldn’t load tenants.
          </Alert>
        ) : tenants.data && tenants.data.results.length > 0 ? (
          <Table
            caption="Tenants"
            columns={columns}
            rows={tenants.data.results}
            rowKey={(t) => t.id}
            renderMobileCard={(t) => (
              <>
                <span className="block text-label text-primary">{t.name}</span>
                <span className="block font-mono text-caption text-secondary">{t.slug}</span>
              </>
            )}
          />
        ) : (
          <p className="text-body text-secondary">No tenants match these filters.</p>
        )}
      </div>
    </div>
  )
}
