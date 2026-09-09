import type { ReactNode } from 'react'
import { cn } from '../lib/cn'

export type BadgeVariant =
  | 'success'
  | 'warning'
  | 'danger'
  | 'neutral'
  | 'accent'

export interface BadgeProps {
  variant?: BadgeVariant
  /** Required. A Badge without a text label is a defect (§C.8). */
  children: ReactNode
  className?: string
}

const VARIANT: Record<BadgeVariant, string> = {
  success: 'bg-success/12 text-success',
  warning: 'bg-warning/12 text-warning',
  danger: 'bg-danger/12 text-danger',
  neutral: 'bg-neutral/12 text-neutral',
  // accent-subtle is exactly rgba(124,92,255,0.12) — the §C.1 12%-alpha value.
  accent: 'bg-accent-subtle text-accent-500',
}

export function Badge({
  variant = 'neutral',
  children,
  className,
}: BadgeProps) {
  if (
    children == null ||
    children === false ||
    (typeof children === 'string' && children.trim() === '')
  ) {
    throw new Error(
      'Badge requires a visible text label — status must never be conveyed by ' +
        'color alone (§C.8).',
    )
  }

  return (
    <span
      className={cn(
        'inline-flex h-[22px] items-center rounded-sm px-2 text-caption font-medium',
        VARIANT[variant],
        className,
      )}
    >
      {children}
    </span>
  )
}
