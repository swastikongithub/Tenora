/**
 * Plan-change confirmation (§C.4 Page 4: "plan change opens a confirmation modal
 * stating the current plan, the target plan, and that billing-period effects
 * apply").
 *
 * No form fields — it confirms a decision already made by clicking a card — so
 * unlike `AddMemberModal` there is no `<form>`/form-id wiring; the footer button
 * calls the handler directly. The consequence is spelled out in text, not only
 * implied by the button label, per §C.4's accessibility note.
 *
 * The request itself is owned by the page (it holds the query client and the
 * tenant key); this component only reports confirm/cancel and renders whatever
 * error the page hands back, so the modal stays open on failure with the
 * message attached rather than closing and losing it.
 */

import { Alert, Button, Modal } from '../components'
import { formatMoney } from '../lib/format'
import type { Plan } from './SubscriptionPage'

interface ChangePlanConfirmModalProps {
  /** The plan being switched to; null closes the modal. */
  target: Plan | null
  current: Plan | null
  submitting: boolean
  error: string | null
  onConfirm: () => void
  onClose: () => void
}

export function ChangePlanConfirmModal({
  target,
  current,
  submitting,
  error,
  onConfirm,
  onClose,
}: ChangePlanConfirmModalProps) {
  return (
    <Modal
      open={target != null}
      onClose={onClose}
      title="Change plan"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={onConfirm} loading={submitting}>
            Change plan
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert variant="danger">{error}</Alert>}

        {target && (
          <>
            <p className="text-body text-secondary">
              {current ? (
                <>
                  This workspace moves from{' '}
                  <strong className="text-primary">{current.name}</strong> (
                  <span className="num">
                    {formatMoney(current.price_cents, current.currency)}
                  </span>
                  ) to{' '}
                  <strong className="text-primary">{target.name}</strong> (
                  <span className="num">
                    {formatMoney(target.price_cents, target.currency)}
                  </span>
                  ).
                </>
              ) : (
                <>
                  This workspace moves to{' '}
                  <strong className="text-primary">{target.name}</strong> (
                  <span className="num">
                    {formatMoney(target.price_cents, target.currency)}
                  </span>
                  ).
                </>
              )}
            </p>
            <p className="text-body text-secondary">
              The change applies to the current billing period.
            </p>
          </>
        )}
      </div>
    </Modal>
  )
}
