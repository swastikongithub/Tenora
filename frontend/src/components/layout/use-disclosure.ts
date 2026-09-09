import { useEffect, useRef, useState } from 'react'

/**
 * Shared open/close plumbing for the navbar's toggled surfaces (tenant switcher
 * dropdown, account menu, mobile nav panel): Escape closes and returns focus to
 * the trigger, a pointer press outside both the trigger and the panel closes it.
 */
export function useDisclosure() {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }

    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node | null
      if (!target) return
      if (triggerRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setOpen(false)
    }

    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  return {
    open,
    setOpen,
    toggle: () => setOpen((value) => !value),
    close: () => setOpen(false),
    triggerRef,
    panelRef,
  }
}
