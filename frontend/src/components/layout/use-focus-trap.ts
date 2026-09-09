/**
 * Focus-trap mechanics for the navbar's anchored menus — the account-menu
 * overlay and the tenant switcher (navbar redesign §4.2 / §7).
 *
 * This is the same behaviour `components/Modal.tsx` implements inline
 * (Modal.tsx:45-96): on activate, remember what was focused and move focus into
 * the container; while active, cycle Tab within the container; on deactivate,
 * restore focus. Body-scroll lock is opt-in (`lockScroll`) — the right call for
 * the account overlay, which pairs with a full-screen scrim, but heavier than
 * warranted for a plain dropdown, so the switcher opts out.
 *
 * It is duplicated rather than shared with Modal because `Modal` is a shipped,
 * tested primitive and this stage has no business refactoring it — §4.2
 * explicitly prefers a small purpose-built copy over bending Modal to fit an
 * anchored, non-dialog overlay. Escape-to-close is NOT here: `useDisclosure`
 * already owns it for both menus.
 */

import { useEffect } from 'react'
import type { RefObject } from 'react'

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])'

function getFocusable(node: HTMLElement | null): HTMLElement[] {
  if (!node) return []
  return Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE))
}

export function useFocusTrap<T extends HTMLElement>(
  active: boolean,
  containerRef: RefObject<T | null>,
  { lockScroll = true }: { lockScroll?: boolean } = {},
) {
  // Focus in on activate, restore (+ unlock) on deactivate. Depends on `active`
  // only, so the previously-focused element is captured exactly once per open.
  useEffect(() => {
    if (!active) return

    const previouslyFocused = document.activeElement as HTMLElement | null
    const focusables = getFocusable(containerRef.current)
    ;(focusables[0] ?? containerRef.current)?.focus()

    const prevOverflow = document.body.style.overflow
    if (lockScroll) document.body.style.overflow = 'hidden'

    return () => {
      if (lockScroll) document.body.style.overflow = prevOverflow
      previouslyFocused?.focus?.()
    }
  }, [active, containerRef, lockScroll])

  // Tab cycle within the container.
  useEffect(() => {
    if (!active) return

    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab') return

      const items = getFocusable(containerRef.current)
      if (items.length === 0) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const activeEl = document.activeElement

      if (!containerRef.current?.contains(activeEl)) {
        e.preventDefault()
        first.focus()
      } else if (e.shiftKey && activeEl === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && activeEl === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [active, containerRef])
}
