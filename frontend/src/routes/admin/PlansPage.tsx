/**
 * /admin/plans — docs/operator-control-plane-spec.md §D: every plan (active or
 * not, unlike the tenant-facing plan list), with `is_active`/search filters
 * and a link to each detail page.
 *
 * Phase 3 adds the one mutation that belongs on a list page — creating a plan.
 * Edit, archive and gateway sync act on a specific plan and live on its detail
 * page. Creation is confirm-before-mutate in the same sense every other
 * mutating control here is: nothing is sent until the form is submitted, and
 * the modal stays open showing the server's own field errors on failure.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Alert, Badge, Button, Input, Skeleton, Table } from '../../components'
import type { Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-error'
import type { FieldErrors } from '../../lib/api-error'
import { formatMoney } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { PlanFormModal } from './PlanFormModal'
import type { PlanFormValues } from './PlanFormModal'
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
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [isActive, setIsActive] = useState<'' | 'true' | 'false'>('')
  const [createOpen, setCreateOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  const params = { search: search || undefined, is_active: isActive || undefined }
  const plans = useQuery({
    queryKey: queryKeys.platformPlans(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<PlatformPlan>>(
        `/platform/plans/${toSearchParams(params)}`,
      ),
  })

  async function createPlan(values: PlanFormValues) {
    setSubmitting(true)
    setCreateError(null)
    setFieldErrors({})
    try {
      await apiClient.post('/platform/plans/', values)
      setSubmitting(false)
      setCreateOpen(false)
      // Every cached plan list, under whatever filters — a new plan may or may
      // not match the filters currently on screen, and the tenant-facing
      // catalogue is a different key entirely (it is not affected: a new plan
      // is created active, and that list refetches on its own schedule).
      void queryClient.invalidateQueries({ queryKey: ['global', 'platform', 'plans'] })
    } catch (cause) {
      setSubmitting(false)
      if (cause instanceof ApiError) {
        setFieldErrors(cause.fieldErrors)
        setCreateError(
          Object.keys(cause.fieldErrors).length > 0 ? null : cause.message,
        )
      } else {
        setCreateError('Something went wrong. Please try again.')
      }
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-h2 text-primary">Plans</h2>
        <Button
          size="sm"
          onClick={() => {
            setCreateError(null)
            setFieldErrors({})
            setCreateOpen(true)
          }}
        >
          New plan
        </Button>
      </div>

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

      <PlanFormModal
        open={createOpen}
        mode="create"
        submitting={submitting}
        error={createError}
        fieldErrors={fieldErrors}
        onSubmit={createPlan}
        onClose={() => setCreateOpen(false)}
      />
    </div>
  )
}
