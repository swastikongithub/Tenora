/**
 * Create/edit form for a plan — Phase 3 of
 * docs/operator-control-plane-spec.md §D. One component for both modes: the
 * two forms take the same fields and the same lock rule applies to both
 * (creation is simply the case where nothing is locked yet), so a second
 * near-identical component would be duplication, not clarity.
 *
 * Same division of labour as SubscriptionOverrideModal: the page owns the
 * request (it holds the query client and the plan id), this component owns the
 * form state and reports a validated payload. It stays open on failure so the
 * operator can correct and retry, and it renders whatever field errors the
 * server returned — the server is the authority on what is valid, this form
 * never decides for it.
 *
 * Money is entered as integer minor units, never a decimal: CLAUDE.md, "money
 * is `price_cents` (integer) + `currency`. Never floats." A live preview
 * renders the same value through `formatMoney`, so the operator sees the
 * currency-correct amount without a float ever existing in this file.
 *
 * The locked fields (`price_cents`, `currency`, `interval`, `code` once the
 * plan has an external plan id) render disabled with an explanation. That is
 * UX only — the real boundary is PlanManagementService server-side, which
 * rejects a locked field whatever this form sends. A server field error always
 * takes precedence over that explanation: if the backend rejected something
 * this form thought was fine, the backend's reason is the one worth reading.
 */

import { useEffect, useState } from 'react'

import { Alert, Button, Input, Modal } from '../../components'
import type { FieldErrors } from '../../lib/api-error'
import { formatMoney } from '../../lib/format'

export type PlanInterval = 'MONTHLY' | 'ANNUAL'

export interface PlanFormValues {
  name: string
  code: string
  price_cents: number
  currency: string
  interval: PlanInterval
}

interface PlanFormModalProps {
  open: boolean
  mode: 'create' | 'edit'
  /** The plan being edited; omitted when creating. */
  initial?: PlanFormValues
  /** True once the plan is provisioned at the gateway — freezes money/identity. */
  locked?: boolean
  submitting: boolean
  /** A general failure message (not attributable to one field). */
  error: string | null
  /** Per-field errors exactly as the server returned them. */
  fieldErrors?: FieldErrors
  onSubmit: (values: PlanFormValues) => void
  onClose: () => void
}

const EMPTY: PlanFormValues = {
  name: '',
  code: '',
  price_cents: 0,
  currency: 'USD',
  interval: 'MONTHLY',
}

const LOCKED_HELP =
  'Locked — this plan is provisioned at the payment gateway. A price change is a new plan, with this one archived.'

function firstError(fieldErrors: FieldErrors | undefined, key: string) {
  return fieldErrors?.[key]?.[0]
}

export function PlanFormModal({
  open,
  mode,
  initial,
  locked = false,
  submitting,
  error,
  fieldErrors,
  onSubmit,
  onClose,
}: PlanFormModalProps) {
  const [values, setValues] = useState<PlanFormValues>(initial ?? EMPTY)
  // `price_cents` is held as the raw input string so a half-typed or cleared
  // field doesn't silently become 0 while the operator is still typing.
  const [priceInput, setPriceInput] = useState(String(initial?.price_cents ?? ''))

  // Re-seed whenever the modal opens, so a cancelled edit doesn't leave stale
  // values behind for the next open.
  useEffect(() => {
    if (!open) return
    setValues(initial ?? EMPTY)
    setPriceInput(String(initial?.price_cents ?? ''))
  }, [open, initial])

  const priceCents = Number.parseInt(priceInput, 10)
  const priceValid = Number.isInteger(priceCents) && priceCents >= 0
  const canSubmit =
    values.name.trim() !== '' &&
    values.code.trim() !== '' &&
    (locked || priceValid) &&
    !submitting

  const title = mode === 'create' ? 'New plan' : 'Edit plan'

  function submit() {
    if (!canSubmit) return
    onSubmit({
      ...values,
      name: values.name.trim(),
      code: values.code.trim(),
      currency: values.currency.trim(),
      price_cents: priceValid ? priceCents : (initial?.price_cents ?? 0),
    })
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      hasUnsavedChanges
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} loading={submitting} disabled={!canSubmit}>
            {mode === 'create' ? 'Create plan' : 'Save changes'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert variant="danger">{error}</Alert>}

        {locked && (
          <Alert variant="info">
            This plan is synced to the payment gateway. Only its name and
            active state can change.
          </Alert>
        )}

        <Input
          label="Name"
          value={values.name}
          onChange={(e) => setValues({ ...values, name: e.target.value })}
          disabled={submitting}
          error={Boolean(firstError(fieldErrors, 'name'))}
          helperText={firstError(fieldErrors, 'name')}
        />

        <Input
          label="Code"
          value={values.code}
          onChange={(e) => setValues({ ...values, code: e.target.value })}
          disabled={submitting || locked}
          error={Boolean(firstError(fieldErrors, 'code'))}
          helperText={
            firstError(fieldErrors, 'code') ??
            (locked
              ? LOCKED_HELP
              : 'Uppercase letters, digits, underscores and hyphens (e.g. PRO_ANNUAL).')
          }
        />

        <Input
          label="Price (minor units)"
          inputMode="numeric"
          value={priceInput}
          onChange={(e) => setPriceInput(e.target.value)}
          disabled={submitting || locked}
          error={Boolean(firstError(fieldErrors, 'price_cents'))}
          helperText={
            firstError(fieldErrors, 'price_cents') ??
            (locked
              ? LOCKED_HELP
              : priceValid
                ? `${formatMoney(priceCents, values.currency)} per period`
                : 'Whole minor units — 2900 for 29.00.')
          }
        />

        <Input
          label="Currency"
          value={values.currency}
          onChange={(e) => setValues({ ...values, currency: e.target.value })}
          disabled={submitting || locked}
          error={Boolean(firstError(fieldErrors, 'currency'))}
          helperText={
            firstError(fieldErrors, 'currency') ??
            (locked ? LOCKED_HELP : 'Three-letter ISO 4217 code.')
          }
        />

        <div className="flex flex-col gap-1.5">
          <label htmlFor="plan-interval" className="text-label text-secondary">
            Interval
          </label>
          <select
            id="plan-interval"
            value={values.interval}
            disabled={submitting || locked}
            onChange={(e) =>
              setValues({ ...values, interval: e.target.value as PlanInterval })
            }
            className="h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            <option value="MONTHLY">Monthly</option>
            <option value="ANNUAL">Annual</option>
          </select>
          {(firstError(fieldErrors, 'interval') ?? (locked ? LOCKED_HELP : null)) && (
            <p className="text-caption text-secondary">
              {firstError(fieldErrors, 'interval') ?? LOCKED_HELP}
            </p>
          )}
        </div>

        {mode === 'create' && (
          <p className="text-caption text-secondary">
            A new plan is created active and unsynced. Provisioning it at the
            payment gateway is a separate action on the plan’s page.
          </p>
        )}
      </div>
    </Modal>
  )
}
