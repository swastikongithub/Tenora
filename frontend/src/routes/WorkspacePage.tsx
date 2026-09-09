/**
 * Workspace Selection & Creation — UI spec §C.4 Page 2. The bridge between
 * "authenticated" and "authenticated within a tenant".
 *
 * The list is `TenantProvider`'s existing `['global','tenants','me']` query —
 * this page reads `useTenant()`, it does NOT fetch again (§4.3 / spec).
 *
 * Selection (existing row or freshly created) always goes through
 * `TenantProvider.switchTenant` (§6) — no other mechanism sets the active
 * tenant. A stub-era note: the UI spec's §C.4 Page 2 layout is a standalone
 * centred column; here it renders inside the app shell (ProtectedRoute is
 * reused as-is per §3) constrained to `max-w-[560px]`.
 *
 * Single-workspace users still see this page — §C.4 Page 2 specifies no
 * auto-selection, and §8 says follow the spec.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { Alert, Badge, Button, Card, EmptyState, Skeleton } from '../components'
import { queryKeys } from '../lib/query-keys'
import { useTenant, type TenantMembership } from '../lib/tenant'
import { CreateWorkspaceModal } from './CreateWorkspaceModal'

export function WorkspacePage() {
  const { tenants, status, switchTenant, refetch } = useTenant()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [modalOpen, setModalOpen] = useState(false)
  const [pendingId, setPendingId] = useState<string | null>(null)

  // A just-created workspace: once TenantProvider's list actually contains it,
  // select it and go in. Doing it here (rather than calling switchTenant right
  // after the POST) sidesteps the race where switchTenant's closure hasn't yet
  // seen the new list.
  useEffect(() => {
    if (!pendingId) return
    if (tenants.some((t) => t.id === pendingId)) {
      switchTenant(pendingId)
      navigate('/overview', { replace: true })
    }
  }, [pendingId, tenants, switchTenant, navigate])

  function enter(tenantId: string) {
    switchTenant(tenantId)
    navigate('/overview', { replace: true })
  }

  function handleCreated(tenant: TenantMembership) {
    // Prime the global tenant list so it shows up immediately; the effect above
    // then selects it. (An invalidate would also work but is a round trip.)
    queryClient.setQueryData<TenantMembership[]>(queryKeys.tenantsMe(), (old) =>
      old?.some((t) => t.id === tenant.id) ? old : [...(old ?? []), tenant],
    )
    setModalOpen(false)
    setPendingId(tenant.id)
  }

  return (
    <section className="mx-auto max-w-[560px]">
      <h1 className="text-display text-primary">Workspaces</h1>
      <p className="mt-1 text-body text-secondary">
        Choose the workspace to operate as, or create a new one.
      </p>

      <div className="mt-6">
        {status === 'loading' && (
          <div className="flex flex-col gap-2">
            <Skeleton count={3} height={72} label="Loading your workspaces" />
          </div>
        )}

        {status === 'error' && (
          <Alert
            variant="danger"
            action={
              <Button size="sm" variant="secondary" onClick={refetch}>
                Retry
              </Button>
            }
          >
            Couldn’t load your workspaces.
          </Alert>
        )}

        {status === 'empty' && (
          <Card>
            <EmptyState
              headline="You’re not a member of any workspace yet"
              description="Create one to get started — you’ll be its owner."
              action={
                <Button onClick={() => setModalOpen(true)}>
                  Create workspace
                </Button>
              }
            />
          </Card>
        )}

        {status === 'ready' && (
          <>
            <ul aria-label="Your workspaces" className="flex flex-col gap-2">
              {tenants.map((tenant) => (
                <li key={tenant.id}>
                  <button
                    type="button"
                    onClick={() => enter(tenant.id)}
                    className="flex w-full items-center justify-between gap-3 rounded-md border border-subtle bg-raised p-4 text-left transition-colors hover:bg-overlay focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-label text-primary">
                        {tenant.name}
                      </span>
                      <span className="block truncate font-mono text-caption text-secondary">
                        {tenant.slug}
                      </span>
                    </span>
                    <Badge variant={tenant.role === 'OWNER' ? 'accent' : 'neutral'}>
                      {tenant.role}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
            <Button
              variant="secondary"
              className="mt-4"
              onClick={() => setModalOpen(true)}
            >
              Create workspace
            </Button>
          </>
        )}
      </div>

      <CreateWorkspaceModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={handleCreated}
      />
    </section>
  )
}
