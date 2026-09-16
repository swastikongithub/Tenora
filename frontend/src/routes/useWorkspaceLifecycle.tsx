/**
 * Leaving / closing a workspace you are NOT currently operating as (plan §27.1).
 *
 * Both actions used to run against the active workspace only, so a user in
 * several workspaces had to switch into each one to leave it — the order was
 * forced on them. The endpoints themselves were never the problem: they resolve
 * the tenant the same way every other call does, from `X-Tenant-ID` plus the
 * caller's ACTIVE Membership. So the target is simply stated per call
 * (`apiClient`'s `tenantId` option) and the backend keeps doing its own
 * verification — an id for a workspace you don't belong to still fails there,
 * exactly as a cross-tenant read does.
 *
 * Closing asks for the workspace's name to be typed out. Acting on a row in a
 * list has none of the "I am looking at this workspace right now" context that
 * the Settings-page version relied on, and closing is irreversible.
 *
 * After either action `['global','tenants','me']` is invalidated;
 * `TenantProvider` re-picks the active workspace when the one it had selected
 * is no longer in the list, so leaving the active workspace needs no special
 * casing here, and leaving any other one leaves the selection alone.
 */

import { useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'

import { Alert, Button, Input, Modal } from '../components'
import { apiClient } from '../lib/api-client'
import { errorMessage } from '../lib/property/errors'
import { queryKeys } from '../lib/query-keys'
import { useTenant, type TenantMembership } from '../lib/tenant'

export type WorkspaceAction = 'leave' | 'close'

/** Whether this membership may be acted on at all (UX only — backend decides). */
export function canClose(tenant: TenantMembership): boolean {
  return tenant.role === 'OWNER'
}

interface Pending {
  action: WorkspaceAction
  tenant: TenantMembership
}

export interface WorkspaceLifecycle {
  /** Open the confirmation for `action` against `tenant`. */
  request: (action: WorkspaceAction, tenant: TenantMembership) => void
  /** Render this once per page; it is the confirmation dialog. */
  dialog: ReactNode
}

export function useWorkspaceLifecycle(): WorkspaceLifecycle {
  const { refetch } = useTenant()
  const queryClient = useQueryClient()
  const [pending, setPending] = useState<Pending | null>(null)
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function request(action: WorkspaceAction, tenant: TenantMembership) {
    setError(null)
    setTyped('')
    setPending({ action, tenant })
  }

  function dismiss() {
    if (busy) return
    setPending(null)
  }

  async function run() {
    if (!pending) return
    setBusy(true)
    setError(null)
    try {
      const path =
        pending.action === 'leave' ? '/memberships/leave/' : '/workspace/close/'
      // The workspace being acted on — NOT the active one.
      await apiClient.post(path, undefined, { tenantId: pending.tenant.id })
      setPending(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.tenantsMe() })
      await queryClient.invalidateQueries({ queryKey: queryKeys.accountUsage() })
      refetch()
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  const name = pending?.tenant.name ?? ''
  const confirmed = pending?.action === 'close' ? typed.trim() === name : true

  const copy =
    pending?.action === 'close'
      ? {
          title: `Close ${name}?`,
          body:
            'Only possible once no other members remain. Pending invitations are cancelled and nobody can open the workspace again. Its billing history is retained.',
          cta: 'Close workspace',
        }
      : {
          title: `Leave ${name}?`,
          body:
            'You lose access to this workspace immediately. Your Tenora account stays, and your past bills and receipts remain on record with the owner. Your other workspaces are not affected.',
          cta: 'Leave workspace',
        }

  const dialog = (
    <Modal
      open={pending !== null}
      onClose={dismiss}
      title={pending ? copy.title : ''}
      footer={
        <>
          <Button variant="ghost" onClick={dismiss} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" loading={busy} disabled={!confirmed} onClick={run}>
            {pending ? copy.cta : ''}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-body text-secondary">{copy.body}</p>
        {error && <Alert variant="danger">{error}</Alert>}
        {pending?.action === 'close' && (
          <Input
            label={`Type ${name} to confirm`}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
          />
        )}
      </div>
    </Modal>
  )

  return { request, dialog }
}
