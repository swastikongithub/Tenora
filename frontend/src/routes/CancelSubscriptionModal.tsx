/**
 * Subscription cancellation confirmation — docs/cancellation-spec.md §4.3.
 *
 * CANCELED is the one irreversible transition in the whole product, so this is
 * deliberately higher friction than ChangePlanConfirmModal's plain confirm: a
 * type-to-confirm gate (the GitHub repo-deletion pattern). The destructive
 * button stays disabled until the user types the workspace name exactly.
 *
 * Copy honesty (§1 / §4.4): this system has no payment processor, no refund
 * logic, and no access gating tied to subscription status — so the text claims
 * none of those. It also does NOT promise "start a new one later": a CANCELED
 * row keeps the tenant's Subscription slot and POST /subscriptions/current/
 * rejects a second one, so there is genuinely no path back today.
 *
 * Like ChangePlanConfirmModal, the request is owned by the page (it holds the
 * query client and tenant key); this component only reports confirm/cancel and
 * renders whatever error the page hands back, staying open on failure.
 */

import { useEffect, useState } from 'react'

import { Alert, Button, Input, Modal } from '../components'

interface CancelSubscriptionModalProps {
  open: boolean
  /** The workspace name the user must type to enable the destructive action. */
  workspaceName: string
  submitting: boolean
  error: string | null
  onConfirm: () => void
  onClose: () => void
}

export function CancelSubscriptionModal({
  open,
  workspaceName,
  submitting,
  error,
  onConfirm,
  onClose,
}: CancelSubscriptionModalProps) {
  const [typed, setTyped] = useState('')

  // Reset the field whenever the modal is closed, so a reopen starts clean.
  useEffect(() => {
    if (!open) setTyped('')
  }, [open])

  // Trim both sides: forgives a copy-pasted name with stray whitespace, while
  // still requiring an exact (case-sensitive) match otherwise.
  const confirmed = typed.trim() === workspaceName.trim()

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Cancel subscription"
      // A half-typed confirmation shouldn't be lost to a stray backdrop click;
      // Escape / the close button / "Keep subscription" still work.
      hasUnsavedChanges={typed.length > 0}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Keep subscription
          </Button>
          <Button
            variant="danger"
            onClick={onConfirm}
            disabled={!confirmed}
            loading={submitting}
          >
            Cancel subscription
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <p className="text-body text-secondary">
          This permanently cancels{' '}
          <strong className="text-primary">{workspaceName}</strong>’s
          subscription. Its status becomes <strong>Canceled</strong> and stays
          that way — there is no reactivation, and a new subscription can’t be
          started for this workspace afterward.
        </p>

        <Input
          label={`Type “${workspaceName}” to confirm`}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          disabled={submitting}
        />
      </div>
    </Modal>
  )
}
