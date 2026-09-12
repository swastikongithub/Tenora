/**
 * A "Fallback Sweep Control" — docs/operator-control-plane-spec.md §B/§E:
 * a manual trigger for one of the three sweep-all service entry points,
 * used because no background worker is deployed for this service. Shared
 * by the Webhooks and Reconciliation pages rather than duplicated per page.
 *
 * Confirm-before-mutate, same pattern as every other mutating control on
 * this surface: nothing runs until the modal is confirmed. The request is
 * owned by this component (it has no query-cache dependents elsewhere to
 * invalidate — a sweep's own effects show up next time the relevant list
 * page is read, same as they would after a real scheduled run).
 */

import { useState } from 'react'

import { Alert, Button, Card, Modal } from '../../components'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-error'

interface FallbackSweepControlProps {
  title: string
  path: string
  describeResult: (data: Record<string, number>) => string
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 429) {
      return 'Too many sweep runs recently — please wait before retrying.'
    }
    return cause.message
  }
  return 'Something went wrong. Please try again.'
}

export function FallbackSweepControl({
  title,
  path,
  describeResult,
}: FallbackSweepControlProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Record<string, number> | null>(null)

  async function run() {
    setSubmitting(true)
    setError(null)
    try {
      const data = await apiClient.post<Record<string, number>>(path)
      setResult(data)
      setSubmitting(false)
      setConfirmOpen(false)
    } catch (cause) {
      setSubmitting(false)
      setError(messageFor(cause))
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-label font-medium text-primary">{title}</p>
          <p className="mt-1 text-caption text-secondary">
            Fallback Sweep Control — runs manually because no production
            worker is deployed for this service.
          </p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setError(null)
            setConfirmOpen(true)
          }}
        >
          Run now
        </Button>
      </div>

      {error && (
        <Alert variant="danger" className="mt-3">
          {error}
        </Alert>
      )}
      {result && !error && (
        <p className="mt-3 text-caption text-secondary" role="status">
          {describeResult(result)}
        </p>
      )}

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title={title}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setConfirmOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button onClick={run} loading={submitting}>
              Run sweep
            </Button>
          </>
        }
      >
        <p className="text-body text-secondary">
          This runs the same sweep a scheduled background worker would run —
          manually, because no worker is currently deployed for this
          service. Safe to run at any time: it only re-checks what is
          already pending and applies no changes beyond that.
        </p>
      </Modal>
    </Card>
  )
}
