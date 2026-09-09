/**
 * The avatar account menu in the top navbar (navbar redesign §4.2).
 *
 * Not a plain dropdown: clicking the avatar opens an overlay — a blurred,
 * dimmed scrim behind an anchored panel whose contents fade/slide in.
 *
 *   trigger     circular avatar with the user's initial (same glyph styling the
 *               C2 UserMenu used). aria-haspopup / aria-expanded / aria-controls.
 *   backdrop    fixed, full-viewport, --color-scrim (the C3b token, already
 *               theme-tuned) + backdrop-blur. Click closes.
 *   panel       fixed, anchored under the avatar by the bar's own geometry
 *               (h-16 bar, avatar is the rightmost element), so there is no
 *               getBoundingClientRect math and nothing to recompute on
 *               scroll/resize. role="menu"; renders <UserMenu/> (email + theme
 *               toggle + logout).
 *
 * Backdrop and panel are portaled to <body>: the sticky z-30 header is its own
 * stacking context, so a scrim rendered inside it could not cover the page.
 *
 * Mechanics:
 *   - open/close, Escape (returns focus to the avatar) and outside-press close
 *     come from `useDisclosure`.
 *   - `useFocusTrap` moves focus into the panel, cycles Tab within it, restores
 *     focus to the avatar on close, and locks body scroll while open.
 *   - a tenant switch from any path closes the menu (§8) — no stale state.
 *
 * Motion: Framer Motion (already a dependency from C3b — no new package). A
 * short backdrop fade + panel opacity/scale/slide, then the body fades in just
 * behind it so the contents arrive rather than snap. Fully disabled (not
 * slowed) under prefers-reduced-motion, same rule and same hook as AuthArtPanel
 * (framer's own useReducedMotion caches for the tab lifetime). `data-motion`
 * reflects the path taken.
 */

import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'

import { cn } from '../../lib/cn'
import { useTenant } from '../../lib/tenant'
import { useCurrentUser } from './use-current-user'
import { useDisclosure } from './use-disclosure'
import { useFocusTrap } from './use-focus-trap'
import { useMediaQuery } from '../use-media-query'
import { UserMenu } from './UserMenu'

export function AccountMenu() {
  const disclosure = useDisclosure()
  const { open, close, setOpen, toggle, triggerRef, panelRef } = disclosure
  const { email } = useCurrentUser()
  const { currentTenant } = useTenant()
  const reduce = useMediaQuery('(prefers-reduced-motion: reduce)')

  const initial = email ? (email[0]?.toUpperCase() ?? '@') : '@'

  useFocusTrap(open, panelRef)

  // §8: switching tenant (from a keyboard shortcut or any other path) closes the
  // menu instead of leaving it open over a changed context. Only a genuine
  // switch — one defined tenant to a different defined tenant — counts; the
  // initial null -> first-tenant resolution must not slam a just-opened menu.
  const currentTenantId = currentTenant?.id
  const prevTenantId = useRef(currentTenantId)
  useEffect(() => {
    if (
      prevTenantId.current !== undefined &&
      currentTenantId !== undefined &&
      prevTenantId.current !== currentTenantId
    ) {
      setOpen(false)
    }
    prevTenantId.current = currentTenantId
  }, [currentTenantId, setOpen])

  const overlay = (
    <AnimatePresence>
      {open && (
        <div key="account-menu">
          <motion.div
            className="fixed inset-0 z-40 bg-[var(--color-scrim)] backdrop-blur-sm"
            data-testid="account-menu-backdrop"
            onClick={close}
            initial={reduce ? undefined : { opacity: 0 }}
            animate={reduce ? undefined : { opacity: 1 }}
            exit={reduce ? undefined : { opacity: 0 }}
            transition={{ duration: 0.16 }}
          />
          <motion.div
            ref={panelRef}
            id="account-menu-panel"
            role="menu"
            aria-label="Account"
            data-motion={reduce ? 'reduced' : 'full'}
            className="fixed right-4 top-[4.5rem] z-50 w-[280px] rounded-lg border border-strong bg-overlay p-4 shadow-overlay outline-none md:right-6"
            initial={reduce ? undefined : { opacity: 0, y: -8, scale: 0.98 }}
            animate={reduce ? undefined : { opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? undefined : { opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
          >
            <motion.div
              initial={reduce ? undefined : { opacity: 0, y: 6 }}
              animate={reduce ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.18, delay: 0.06, ease: 'easeOut' }}
            >
              <UserMenu />
            </motion.div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="account-menu-panel"
        aria-label="Account menu"
        onClick={toggle}
        className={cn(
          'grid size-8 place-items-center rounded-full border border-subtle bg-transparent text-caption font-medium text-secondary',
          'transition-colors hover:border-strong hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
        )}
      >
        <span aria-hidden="true">{initial}</span>
      </button>

      {createPortal(overlay, document.body)}
    </div>
  )
}
