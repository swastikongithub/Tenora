/**
 * Light/dark toggle, shown in the account menu (Stage C3b §4.1 — the original
 * admin-dashboard reference had a dark-mode toggle in the user area).
 *
 * Accessibility (§7): a real <button>, keyboard-reachable, with the shared
 * focus-visible ring every control in this app uses. It's a toggle button —
 * `aria-pressed` reports whether dark mode is on, and the label is fixed
 * ("Dark mode") so the pressed state, not a changing name, carries the meaning.
 * The icon is decorative (`aria-hidden`).
 */

import { cn } from '../../lib/cn'
import { useTheme } from '../../lib/theme'

const iconProps = {
  className: 'size-4 shrink-0',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  'aria-hidden': true,
} as const

function SunIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg {...iconProps}>
      <path d="M20 14.5A8 8 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z" />
    </svg>
  )
}

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-pressed={isDark}
      className={cn(
        'flex items-center gap-2 rounded-md border border-subtle px-3 py-2',
        'text-label text-secondary transition-colors',
        'hover:bg-overlay hover:text-primary',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
      )}
    >
      {isDark ? <MoonIcon /> : <SunIcon />}
      <span>Dark mode</span>
    </button>
  )
}
