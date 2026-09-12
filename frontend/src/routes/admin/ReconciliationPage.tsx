/**
 * /admin/reconciliation — the immutable, detection-only
 * ReconciliationDiscrepancy audit trail. Phase 2 adds two Fallback Sweep
 * Controls (docs/operator-control-plane-spec.md §B): reconciliation
 * (ReconciliationService.reconcile_all) and usage snapshotting
 * (UsageMeteringService.snapshot_all_subscribed) — the approved IA has no
 * separate "usage" page, so its sweep lives here alongside reconciliation's.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { Alert, Badge, Button, Skeleton, Table } from '../../components'
import type { BadgeVariant, Column } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDate } from '../../lib/format'
import { queryKeys } from '../../lib/query-keys'
import { FallbackSweepControl } from './FallbackSweepControl'
import { toSearchParams } from './query-params'

type Category = 'STATUS_MISMATCH' | 'LOCAL_CANCELED_PROVIDER_ACTIVE' | 'PROVIDER_NOT_FOUND'

interface DiscrepancyRow {
  id: string
  tenant: { id: string; name: string; slug: string }
  subscription_id: string
  external_subscription_id: string
  category: Category
  local_status: string
  provider_status: string
  detail: string
  detected_at: string
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const CATEGORIES: Category[] = [
  'STATUS_MISMATCH',
  'LOCAL_CANCELED_PROVIDER_ACTIVE',
  'PROVIDER_NOT_FOUND',
]

const CATEGORY_LABEL: Record<Category, string> = {
  STATUS_MISMATCH: 'Status mismatch',
  LOCAL_CANCELED_PROVIDER_ACTIVE: 'Canceled locally, still live at gateway',
  PROVIDER_NOT_FOUND: 'Gateway has no record',
}

const CATEGORY_VARIANT: Record<Category, BadgeVariant> = {
  STATUS_MISMATCH: 'warning',
  LOCAL_CANCELED_PROVIDER_ACTIVE: 'danger',
  PROVIDER_NOT_FOUND: 'danger',
}

const columns: Array<Column<DiscrepancyRow>> = [
  { key: 'tenant', header: 'Tenant', render: (d) => d.tenant.name },
  {
    key: 'category',
    header: 'Category',
    render: (d) => (
      <Badge variant={CATEGORY_VARIANT[d.category]}>{CATEGORY_LABEL[d.category]}</Badge>
    ),
  },
  { key: 'local_status', header: 'Local status' },
  { key: 'provider_status', header: 'Gateway status', render: (d) => d.provider_status || '—' },
  { key: 'detected_at', header: 'Detected', render: (d) => formatDate(d.detected_at) },
]

export function ReconciliationPage() {
  const [category, setCategory] = useState<'' | Category>('')

  const params = { category: category || undefined }
  const discrepancies = useQuery({
    queryKey: queryKeys.platformReconciliationDiscrepancies(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<DiscrepancyRow>>(
        `/platform/reconciliation-discrepancies/${toSearchParams(params)}`,
      ),
  })

  return (
    <div>
      <h2 className="text-h2 text-primary">Reconciliation</h2>
      <p className="mt-1 text-body text-secondary">
        Detection-only: local subscription status compared against the payment gateway.
        Nothing here is corrected automatically.
      </p>

      <div className="mt-4 flex flex-col gap-4 sm:flex-row">
        <div className="flex-1">
          <FallbackSweepControl
            title="Reconciliation sweep"
            path="/platform/reconciliation/run/"
            describeResult={(r) =>
              `${r.total} checked, ${r.matched} matched, ${r.discrepancies} discrepancies, ${r.unavailable} unavailable.`
            }
          />
        </div>
        <div className="flex-1">
          <FallbackSweepControl
            title="Usage snapshot sweep"
            path="/platform/usage/run/"
            describeResult={(r) =>
              `${r.total} tenants, ${r.created} new snapshots, ${r.existing} already existed, ${r.skipped} skipped.`
            }
          />
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-1.5" style={{ maxWidth: '20rem' }}>
        <label htmlFor="discrepancy-category-filter" className="text-label text-secondary">
          Category
        </label>
        <select
          id="discrepancy-category-filter"
          value={category}
          onChange={(e) => setCategory(e.target.value as '' | Category)}
          className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary"
        >
          <option value="">All</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABEL[c]}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-6">
        {discrepancies.isPending ? (
          <Skeleton count={5} height={52} label="Loading reconciliation discrepancies" />
        ) : discrepancies.isError ? (
          <Alert
            variant="danger"
            action={
              <Button
                size="sm"
                variant="secondary"
                onClick={() => discrepancies.refetch()}
              >
                Retry
              </Button>
            }
          >
            Couldn’t load reconciliation discrepancies.
          </Alert>
        ) : discrepancies.data && discrepancies.data.results.length > 0 ? (
          <Table
            caption="Reconciliation discrepancies"
            columns={columns}
            rows={discrepancies.data.results}
            rowKey={(d) => d.id}
            renderMobileCard={(d) => (
              <>
                <span className="block text-label text-primary">{d.tenant.name}</span>
                <Badge variant={CATEGORY_VARIANT[d.category]}>
                  {CATEGORY_LABEL[d.category]}
                </Badge>
              </>
            )}
          />
        ) : (
          <p className="text-body text-secondary">No discrepancies found.</p>
        )}
      </div>
    </div>
  )
}
