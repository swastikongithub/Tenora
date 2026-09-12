/**
 * /admin/plans/:id — read-only detail. No edit/archive/sync controls in
 * Phase 1 (those are Phase 3).
 */

import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, DataList, Skeleton } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatMoney } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'

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

export function PlanDetailPage() {
  const { id } = useParams<{ id: string }>()

  const plan = useQuery({
    queryKey: queryKeys.platformPlanDetail(id ?? ''),
    queryFn: () => apiClient.get<PlatformPlan>(`/platform/plans/detail/?id=${id}`),
    enabled: Boolean(id),
  })

  if (plan.isPending) {
    return <Skeleton count={5} height={24} label="Loading plan" />
  }

  if (plan.isError) {
    return (
      <Alert
        variant="danger"
        action={
          <Button size="sm" variant="secondary" onClick={() => plan.refetch()}>
            Retry
          </Button>
        }
      >
        Couldn’t load this plan.
      </Alert>
    )
  }

  const data = plan.data
  if (!data) return null

  return (
    <div>
      <div className="flex items-center gap-3">
        <h2 className="text-h2 text-primary">{data.name}</h2>
        <Badge variant={data.is_active ? 'success' : 'neutral'}>
          {data.is_active ? 'Active' : 'Archived'}
        </Badge>
      </div>

      <DataList
        className="mt-6"
        rows={[
          { term: 'Code', children: <span className="font-mono">{data.code}</span> },
          { term: 'Price', children: formatMoney(data.price_cents, data.currency) },
          { term: 'Currency', children: data.currency },
          { term: 'Interval', children: data.interval },
          { term: 'Subscribers', children: data.subscriber_count },
          {
            term: 'External plan ID',
            children: data.external_plan_id ? (
              <span className="font-mono">{data.external_plan_id}</span>
            ) : (
              <span className="text-secondary">Not synced to the payment gateway yet</span>
            ),
          },
        ]}
      />
    </div>
  )
}
