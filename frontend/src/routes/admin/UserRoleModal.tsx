/**
 * Confirm-before-mutate dialog for a platform role change — Phase 4 of
 * docs/operator-control-plane-spec.md §D, the Root-only half of /admin/users.
 *
 * The spec calls role management "the single highest-leverage endpoint in this
 * design", so this dialog is deliberately explicit rather than convenient: it
 * shows each flag's current value, what it would become, and — when the change
 * would remove the last Root — refuses before sending, with the same reason
 * the server would give.
 *
 * That pre-check is UX only. The authority is UserRoleService's last-root
 * invariant, checked inside a transaction under a row lock; this dialog just
 * saves a round trip and explains the rule where the operator is standing.
 *
 * Same division of labour as every other mutating control here: the page owns
 * the request, this component owns the form state and reports the change.
 */

import { useEffect, useState } from 'react'

import { Alert, Button, Modal } from '../../components'

export interface RoleFlags {
  is_staff: boolean
  is_superuser: boolean
  is_active: boolean
}

export interface RoleTarget extends RoleFlags {
  id: string
  email: string
}

interface UserRoleModalProps {
  open: boolean
  target: RoleTarget | null
  /** Whether the signed-in operator is editing their own account. */
  isSelf: boolean
  /** How many accounts currently satisfy the Root predicate. */
  activeRootCount: number
  submitting: boolean
  error: string | null
  onSubmit: (changes: Partial<RoleFlags>) => void
  onClose: () => void
}

const FLAGS: Array<{ key: keyof RoleFlags; label: string; help: string }> = [
  {
    key: 'is_staff',
    label: 'Platform staff',
    help: 'Runs the whole control plane: plans, overrides, sweeps, every read except raw payloads.',
  },
  {
    key: 'is_superuser',
    label: 'Root',
    help: 'With staff, grants the Root tier: role management, tenant suspension, raw gateway payloads.',
  },
  {
    key: 'is_active',
    label: 'Active',
    help: 'Administratively enabled. Unrelated to whether the address was ever verified.',
  },
]

function isRootFlags(flags: RoleFlags): boolean {
  return flags.is_staff && flags.is_superuser && flags.is_active
}

export function UserRoleModal({
  open,
  target,
  isSelf,
  activeRootCount,
  submitting,
  error,
  onSubmit,
  onClose,
}: UserRoleModalProps) {
  const [flags, setFlags] = useState<RoleFlags>({
    is_staff: false,
    is_superuser: false,
    is_active: true,
  })

  useEffect(() => {
    if (!open || !target) return
    setFlags({
      is_staff: target.is_staff,
      is_superuser: target.is_superuser,
      is_active: target.is_active,
    })
  }, [open, target])

  if (!target) return null

  const wasRoot = isRootFlags(target)
  const willBeRoot = isRootFlags(flags)
  const otherRoots = wasRoot ? activeRootCount - 1 : activeRootCount
  const wouldLeaveNoRoot = otherRoots < 1 && !willBeRoot

  const changed = FLAGS.filter(({ key }) => flags[key] !== target[key])
  const canSubmit = changed.length > 0 && !wouldLeaveNoRoot && !submitting

  function submit() {
    if (!canSubmit) return
    const changes: Partial<RoleFlags> = {}
    for (const { key } of changed) changes[key] = flags[key]
    onSubmit(changes)
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Change platform roles"
      hasUnsavedChanges
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} loading={submitting} disabled={!canSubmit}>
            Apply changes
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert variant="danger">{error}</Alert>}

        <p className="text-body text-secondary">
          Platform authority for{' '}
          <strong className="text-primary">{target.email}</strong>
          {isSelf && ' — your own account'}.
        </p>

        {wouldLeaveNoRoot && (
          <Alert variant="warning" assertive>
            This would leave no active root operator. Promote another root
            account first.
          </Alert>
        )}

        <fieldset className="flex flex-col gap-3">
          <legend className="sr-only">Platform roles</legend>
          {FLAGS.map(({ key, label, help }) => (
            <label key={key} className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={flags[key]}
                disabled={submitting}
                onChange={(e) => setFlags({ ...flags, [key]: e.target.checked })}
                className="mt-1 size-4 accent-[var(--color-accent-600)]"
              />
              <span>
                <span className="block text-label text-primary">{label}</span>
                <span className="block text-caption text-secondary">{help}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <p className="text-caption text-secondary">
          This changes platform authority only. Email, password and
          verification state are not reachable from here.
        </p>
      </div>
    </Modal>
  )
}
