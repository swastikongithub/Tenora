import type { ReactNode } from 'react'
import { cn } from '../lib/cn'

/**
 * §C.1 "Alert" — full-width bar, radius md, left icon, colored left border,
 * text-primary body. This primitive was on the C1-deferred list (Select /
 * Alert / Nav); Stage C2 needs it for the login error region and the
 * blocking tenant-switcher error, so it is built here following the same
 * token-driven pattern as the C1 eight. Reported as a scope addition.
 *
 * `assertive` (default for `danger`) sets `role="alert"` so screen readers
 * announce it immediately — used for form submission errors (§C.8).
 */

export type AlertVariant = 'info' | 'success' | 'warning' | 'danger'

export interface AlertProps {
  variant?: AlertVariant
  /** Optional bold lead-in above the body. */
  title?: string
  children: ReactNode
  /** Right-aligned slot for a single action, e.g. a Retry button. */
  action?: ReactNode
  /**
   * Announce immediately via `role="alert"`. Defaults to `true` for `danger`,
   * `false` otherwise. Set explicitly for a warning that must interrupt.
   */
  assertive?: boolean
  className?: string
}

const VARIANT: Record<
  AlertVariant,
  { bar: string; text: string; icon: ReactNode }
> = {
  info: {
    bar: 'border-l-accent-600 bg-accent-subtle',
    text: 'text-accent-500',
    icon: <GlyphInfo />,
  },
  success: {
    bar: 'border-l-success bg-success/12',
    text: 'text-success',
    icon: <GlyphCheck />,
  },
  warning: {
    bar: 'border-l-warning bg-warning/12',
    text: 'text-warning',
    icon: <GlyphWarning />,
  },
  danger: {
    bar: 'border-l-danger bg-danger/12',
    text: 'text-danger',
    icon: <GlyphWarning />,
  },
}

export function Alert({
  variant = 'info',
  title,
  children,
  action,
  assertive,
  className,
}: AlertProps) {
  const styles = VARIANT[variant]
  const isAssertive = assertive ?? variant === 'danger'

  return (
    <div
      role={isAssertive ? 'alert' : 'status'}
      className={cn(
        'flex items-start gap-3 rounded-md border border-subtle border-l-4 p-4',
        styles.bar,
        className,
      )}
    >
      <span className={cn('mt-0.5 shrink-0', styles.text)} aria-hidden="true">
        {styles.icon}
      </span>
      <div className="flex-1 text-body text-primary">
        {title && <p className="font-medium">{title}</p>}
        <div className={title ? 'mt-0.5 text-secondary' : undefined}>
          {children}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

function GlyphInfo() {
  return (
    <svg
      className="size-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </svg>
  )
}

function GlyphCheck() {
  return (
    <svg
      className="size-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12l3 3 5-6" />
    </svg>
  )
}

function GlyphWarning() {
  return (
    <svg
      className="size-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M12 3l9 16H3z" />
      <path d="M12 10v4M12 17h.01" />
    </svg>
  )
}
