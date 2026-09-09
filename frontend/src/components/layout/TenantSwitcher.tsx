/**
 * UI spec §C.2 — "the single most important UI element in the product." Sets
 * the tenant the whole app operates as (the `X-Tenant-ID` the client sends).
 *
 * States mirror §C.2: skeleton pill while loading; an empty state linking to
 * the workspace page (C3); a blocking inline retry on error (the rest of the
 * app is unusable without tenant context). The selected tenant and each option
 * show the user's role, so OWNER-only actions elsewhere are predictable.
 *
 * Navbar redesign §4.1: the switcher now lives in a ~190–230px slot in the top
 * bar rather than a dedicated sidebar block. Behaviour, handlers and the
 * user-visible strings are unchanged — only the container width and the
 * compact error form differ.
 *
 * Its open dropdown gets the full account-menu overlay treatment: a blurred
 * `--color-scrim` backdrop, a Framer Motion fade/slide entrance (disabled under
 * prefers-reduced-motion, `data-motion` reflects the path), a focus trap that
 * moves focus onto the first workspace and cycles Tab within the list, focus
 * returned to the trigger on close, and body scroll locked while open. Escape +
 * outside press are handled by `useDisclosure`. Backdrop and panel are portaled
 * to <body> so the sticky `z-30` header's stacking context can't bury them; the
 * panel is positioned against the trigger's measured rect (the switcher is not
 * at the bar's edge, so it can't lean on geometry the way the account menu does).
 */

import { useLayoutEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Link } from 'react-router-dom'

import { Badge, Button, Skeleton } from '../index'
import type { TenantMembership, TenantRole } from '../../lib/tenant'
import { useTenant } from '../../lib/tenant'
import { cn } from '../../lib/cn'
import { useDisclosure } from './use-disclosure'
import { useFocusTrap } from './use-focus-trap'
import { useMediaQuery } from '../use-media-query'

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  const letters = (parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')
  return letters.toUpperCase() || '?'
}

function roleBadge(role: TenantRole) {
  return <Badge variant={role === 'OWNER' ? 'accent' : 'neutral'}>{role}</Badge>
}

export function TenantSwitcher() {
  const { tenants, currentTenant, status, switchTenant, refetch } = useTenant()
  const { open, close, toggle, triggerRef, panelRef } = useDisclosure()
  const reduce = useMediaQuery('(prefers-reduced-motion: reduce)')
  const [anchor, setAnchor] = useState<{ top: number; right: number } | null>(
    null,
  )

  useFocusTrap(open, panelRef)

  // Position the portaled panel against the trigger's viewport rect (the header
  // is `sticky top-0`, so the rect is stable under vertical scroll; re-measure
  // on resize). Runs before paint, so the panel never shows at the wrong spot.
  useLayoutEffect(() => {
    if (!open) {
      setAnchor(null)
      return
    }
    const measure = () => {
      const el = triggerRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      setAnchor({
        top: r.bottom + 6,
        right: Math.max(window.innerWidth - r.right, 8),
      })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [open, triggerRef])

  if (status === 'loading') {
    return <Skeleton height={44} radius="md" label="Loading workspaces" />
  }

  if (status === 'error') {
    return (
      <div className="flex items-center gap-2 rounded-md border border-danger/40 bg-base px-2 py-1.5">
        <span className="min-w-0 flex-1 truncate text-caption text-danger">
          Couldn&rsquo;t load your workspaces.
        </span>
        <Button size="sm" variant="secondary" onClick={refetch}>
          Retry
        </Button>
      </div>
    )
  }

  if (status === 'empty' || !currentTenant) {
    return (
      <div className="rounded-md border border-subtle p-3">
        <p className="text-label text-primary">No workspace selected</p>
        <Link
          to="/workspace"
          className="mt-1 inline-block rounded-sm text-caption font-medium text-accent-500 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
        >
          Choose or create one
        </Link>
      </div>
    )
  }

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="tenant-switcher-menu"
        onClick={toggle}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-md border border-subtle bg-transparent p-1.5 text-left',
          'transition-colors hover:bg-overlay focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
        )}
      >
        <span
          aria-hidden="true"
          className="grid size-7 shrink-0 place-items-center rounded-sm bg-accent-subtle text-caption font-medium text-accent-500"
        >
          {initials(currentTenant.name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-label text-primary">
            {currentTenant.name}
          </span>
          <span className="block truncate text-caption text-secondary">
            {currentTenant.role}
          </span>
        </span>
        <Chevron className="shrink-0 text-secondary" />
      </button>

      {createPortal(
        <AnimatePresence>
          {open && (
            <div key="tenant-switcher-overlay">
              <motion.div
                className="fixed inset-0 z-40 bg-[var(--color-scrim)] backdrop-blur-sm"
                data-testid="tenant-switcher-backdrop"
                onClick={close}
                initial={reduce ? undefined : { opacity: 0 }}
                animate={reduce ? undefined : { opacity: 1 }}
                exit={reduce ? undefined : { opacity: 0 }}
                transition={{ duration: 0.16 }}
              />
              <motion.div
                ref={panelRef}
                id="tenant-switcher-menu"
                role="menu"
                aria-label="Switch workspace"
                data-motion={reduce ? 'reduced' : 'full'}
                style={
                  anchor
                    ? { top: anchor.top, right: anchor.right }
                    : { top: -9999, right: 0 }
                }
                className="fixed z-50 w-[280px] max-w-[calc(100vw-1rem)] overflow-hidden rounded-md border border-strong bg-overlay shadow-overlay outline-none"
                initial={reduce ? undefined : { opacity: 0, y: -8, scale: 0.98 }}
                animate={reduce ? undefined : { opacity: 1, y: 0, scale: 1 }}
                exit={reduce ? undefined : { opacity: 0, y: -8, scale: 0.98 }}
                transition={{ duration: 0.18, ease: 'easeOut' }}
              >
                <ul className="max-h-72 overflow-y-auto py-1">
                  {tenants.map((tenant) => (
                    <li key={tenant.id}>
                      <TenantOption
                        tenant={tenant}
                        active={tenant.id === currentTenant.id}
                        onSelect={() => {
                          switchTenant(tenant.id)
                          close()
                          triggerRef.current?.focus()
                        }}
                      />
                    </li>
                  ))}
                </ul>
              </motion.div>
            </div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  )
}

function TenantOption({
  tenant,
  active,
  onSelect,
}: {
  tenant: TenantMembership
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={active}
      onClick={onSelect}
      className={cn(
        'flex w-full items-center justify-between gap-3 px-3 py-2 text-left',
        'hover:bg-raised focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-600',
        active && 'bg-accent-subtle',
      )}
    >
      <span className="min-w-0">
        <span className="block truncate text-label text-primary">
          {tenant.name}
        </span>
        <span className="block truncate font-mono text-caption text-secondary">
          {tenant.slug}
        </span>
      </span>
      {roleBadge(tenant.role)}
    </button>
  )
}

function Chevron({ className }: { className?: string }) {
  return (
    <svg
      className={cn('size-4', className)}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M8 10l4 4 4-4" />
    </svg>
  )
}
