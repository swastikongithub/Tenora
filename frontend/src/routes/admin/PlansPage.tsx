/**
 * /admin/plans — docs/operator-control-plane-spec.md §D. Read-only in Phase
 * 1: every plan (active or not, unlike the tenant-facing plan list), with
 * `is_active`/search filters and a link to each detail page. No create/
 * edit/archive controls here — those are Phase 3.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Input, Skeleton, Table } from '../../components'
import type { Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatMoney } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { toSearchParams } from './query-params'

interface PlatformPlan {
  id: string
  name: string
  code: string
  price_cents: number
  currency: string
  interval: 'MONTHLY' | 'ANNUAL'
  is_active: boolean
  external_plan_id: string | null
  subscriber_count: number
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const columns: Array<Column<PlatformPlan>> = [
  {
    key: 'name',
    header: 'Plan',
    render: (p) => (
      <Link to={`/admin/plans/${p.id}`} className="text-primary hover:underline">
        {p.name}
      </Link>
    ),
  },
  { key: 'code', header: 'Code', render: (p) => <span className="font-mono">{p.code}</span> },
  {
    key: 'price',
    header: 'Price',
    numeric: true,
    render: (p) => formatMoney(p.price_cents, p.currency),
  },
  { key: 'interval', header: 'Interval', render: (p) => p.interval },
  {
    key: 'is_active',
    header: 'Status',
    render: (p) => (
      <Badge variant={p.is_active ? 'success' : 'neutral'}>
        {p.is_active ? 'Active' : 'Archived'}
      </Badge>
    ),
  },
  {
    key: 'external_plan_id',
    header: 'Gateway sync',
    render: (p) => (
      <Badge variant={p.external_plan_id ? 'success' : 'warning'}>
        {p.external_plan_id ? 'Synced' : 'Not synced'}
      </Badge>
    ),
  },
  {
    key: 'subscriber_count',
    header: 'Subscribers',
    numeric: true,
    render: (p) => p.subscriber_count,
  },
]

export function PlansPage() {
  const [search, setSearch] = useState('')
  const [isActive, setIsActive] = useState<'' | 'true' | 'false'>('')

  const params = { search: search || undefined, is_active: isActive || undefined }
  const plans = useQuery({
    queryKey: queryKeys.platformPlans(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<PlatformPlan>>(
        `/platform/plans/${toSearchParams(params)}`,
      ),
  })

  return (
    <div>
      <h2 className="text-h2 text-primary">Plans</h2>

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <Input
          label="Search"
          placeholder="Name or code"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-56"
        />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="plan-status-filter" className="text-label text-secondary">
            Status
          </label>
          <select
            id="plan-status-filter"
            value={isActive}
            onChange={(e) => setIsActive(e.target.value as '' | 'true' | 'false')}
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Archived</option>
          </select>
        </div>
      </div>

      <div className="mt-6">
        {plans.isPending ? (
          <Skeleton count={5} height={52} label="Loading plans" />
        ) : plans.isError ? (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={() => plans.refetch()}>
                Retry
              </Button>
            }
          >
            Couldn’t load plans.
          </Alert>
        ) : plans.data && plans.data.results.length > 0 ? (
          <Table
            caption="Plans"
            columns={columns}
            rows={plans.data.results}
            rowKey={(p) => p.id}
            renderMobileCard={(p) => (
              <>
                <span className="block text-label text-primary">{p.name}</span>
                <span className="block font-mono text-caption text-secondary">{p.code}</span>
                <span className="mt-2 flex flex-wrap items-center gap-2 text-caption text-secondary">
                  <Badge variant={p.is_active ? 'success' : 'neutral'}>
                    {p.is_active ? 'Active' : 'Archived'}
                  </Badge>
                  <span>{formatMoney(p.price_cents, p.currency)}</span>
                </span>
              </>
            )}
          />
        ) : (
          <p className="text-body text-secondary">No plans match these filters.</p>
        )}
      </div>
    </div>
  )
}
