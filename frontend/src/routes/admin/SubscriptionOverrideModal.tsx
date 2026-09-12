/**
 * Confirm-before-mutate modal for an operator subscription override — docs
 * /operator-control-plane-spec.md §E "Subscription controls... reuse the
 * existing confirm-before-mutate UX pattern." Same shape as the tenant-facing
 * CancelSubscriptionModal/ChangePlanConfirmModal: the request is owned by the
 * page (it holds the query client and tenant id), this component only
 * reports confirm/cancel and renders whatever error the page hands back,
 * staying open on failure so the operator can retry or cancel.
 *
 * No business logic here: the legal-transition table lives only in
 * SubscriptionService server-side — this modal shows whatever from/to the
 * page tells it to and lets the backend accept or reject it.
 */

import { Alert, Button, Modal } from '../../components'

interface SubscriptionOverrideModalProps {
  open: boolean
  kind: 'plan' | 'status'
  tenantName: string
  fromLabel: string
  toLabel: string
  submitting: boolean
  error: string | null
  onConfirm: () => void
  onClose: () => void
}

export function SubscriptionOverrideModal({
  open,
  kind,
  tenantName,
  fromLabel,
  toLabel,
  submitting,
  error,
  onConfirm,
  onClose,
}: SubscriptionOverrideModalProps) {
  const title = kind === 'plan' ? 'Change plan' : 'Transition status'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={onConfirm} loading={submitting}>
            Confirm
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <p className="text-body text-secondary">
          {kind === 'plan' ? 'Change the plan' : 'Transition the status'} for{' '}
          <strong className="text-primary">{tenantName}</strong>’s subscription:
        </p>

        <div className="flex items-center gap-3 rounded-md border border-subtle bg-raised px-4 py-3 text-body">
          <span className="text-secondary line-through">{fromLabel}</span>
          <span aria-hidden="true" className="text-muted">
            →
          </span>
          <span className="font-medium text-primary">{toLabel}</span>
        </div>

        <p className="text-caption text-secondary">
          This calls the same subscription service the tenant-facing app
          uses — an illegal transition will be rejected, not silently
          applied.
        </p>
      </div>
    </Modal>
  )
}
