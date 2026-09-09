import type { MouseEvent, ReactNode } from 'react'
import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../lib/cn'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  /** form → max-width 480; detail → max-width 640 (§C.1). */
  size?: 'form' | 'detail'
  /**
   * When true, a backdrop click will NOT close the modal (§C.8 — backdrop
   * click closes only if there is no unsaved input). Escape and the close
   * button still work.
   */
  hasUnsavedChanges?: boolean
  children: ReactNode
  footer?: ReactNode
}

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])'

function getFocusable(node: HTMLElement | null): HTMLElement[] {
  if (!node) return []
  return Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE))
}

export function Modal({
  open,
  onClose,
  title,
  size = 'form',
  hasUnsavedChanges = false,
  children,
  footer,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  // Focus management: capture the trigger when the modal opens, move focus in,
  // and return focus to the trigger when it closes. Depends on `open` only so
  // the trigger is captured exactly once per open.
  useEffect(() => {
    if (!open) return

    const trigger = document.activeElement as HTMLElement | null
    const focusables = getFocusable(dialogRef.current)
    ;(focusables[0] ?? dialogRef.current)?.focus()

    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = prevOverflow
      trigger?.focus?.()
    }
  }, [open])

  // Escape to close + Tab focus trap.
  useEffect(() => {
    if (!open) return

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      const items = getFocusable(dialogRef.current)
      if (items.length === 0) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement

      if (!dialogRef.current?.contains(active)) {
        e.preventDefault()
        first.focus()
      } else if (e.shiftKey && active === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [open, onClose])

  if (!open) return null

  const onBackdropClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return
    if (hasUnsavedChanges) return
    onClose()
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-scrim)] p-4 max-md:p-0"
      onClick={onBackdropClick}
      data-testid="modal-backdrop"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          'flex w-full flex-col rounded-lg bg-overlay shadow-overlay outline-none',
          size === 'detail' ? 'max-w-[640px]' : 'max-w-[480px]',
          // Full-screen sheet below 768px (§C.7).
          'max-md:h-full max-md:max-w-full max-md:rounded-none',
        )}
      >
        <div className="flex items-center justify-between gap-4 border-b border-subtle p-6">
          <h2 id={titleId} className="text-h2 text-primary">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-secondary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
          >
            <svg
              className="size-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="overflow-y-auto p-6 text-body text-secondary">
          {children}
        </div>

        {footer && (
          <div className="flex justify-end gap-2 border-t border-subtle p-6">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
