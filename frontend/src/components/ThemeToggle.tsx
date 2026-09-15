/**
 * The one theme toggle: the Eclipse control from @theme-toggles/react, driven
 * by Tenora's existing theme store (lib/theme). There is no local state here —
 * `theme` and `toggleTheme` come from `useTheme()`, which reads and writes the
 * same `<html data-theme>` attribute and `billing.theme` storage key the
 * pre-paint script in index.html uses. Every placement (account menu, landing
 * nav, auth pages) renders this component, so they can never disagree.
 *
 * Accessibility: Eclipse renders a real <button>. It keeps the contract the
 * previous toggle established — accessible name "Dark mode", `aria-pressed`
 * reporting whether dark mode is on — so the pressed state, not a changing
 * label, carries the meaning. Eclipse's transitions only exist under
 * `prefers-reduced-motion: no-preference`; with reduced motion the icon swaps
 * state instantly and switching still works.
 *
 * `label` renders a visible "Dark mode" caption beside the icon (the account
 * menu row and the mobile landing menu). The caption is a <label> for the
 * button, so the whole row is clickable without nesting interactive elements.
 */

import { Eclipse } from '@theme-toggles/react'
import '@theme-toggles/react/styles/eclipse.css'
import { useId } from 'react'

import { cn } from '../lib/cn'
import { useTheme } from '../lib/theme'

/** Transition length for the eclipse morph (the package default is 500ms). */
const DURATION_MS = 400

const FOCUS_RING = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600'

export function ThemeToggle({ label = false, className }: { label?: boolean; className?: string }) {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'
  const id = useId()

  const button = (
    <Eclipse
      id={id}
      toggled={isDark}
      onClick={toggleTheme}
      duration={DURATION_MS}
      aria-label="Dark mode"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-md text-secondary transition-colors hover:text-primary',
        label ? 'text-[1rem]' : cn('size-9 border border-subtle text-[1.125rem] hover:bg-overlay', FOCUS_RING, className),
        label && 'focus-visible:outline-none',
      )}
    />
  )

  if (!label) return button

  return (
    <label
      htmlFor={id}
      className={cn(
        'flex cursor-pointer items-center gap-2 rounded-md border border-subtle px-3 py-2',
        'text-label text-secondary transition-colors hover:bg-overlay hover:text-primary',
        'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent-600',
        className,
      )}
    >
      {button}
      <span aria-hidden="true">Dark mode</span>
    </label>
  )
}
