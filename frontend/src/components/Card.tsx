import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../lib/cn'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Optional header row: h2 title on the left. */
  title?: string
  /** Optional header row: actions on the right (buttons, links). */
  actions?: ReactNode
  /**
   * Opt-in emphasis treatment (§C.1a): accent-tinted gradient background +
   * accent glow, in place of the plain `bg-raised` + `shadow-card`. Radius,
   * padding and header behaviour are unchanged.
   *
   * Reserve for the single most important card on a page — if more than one
   * card is `featured`, none of them read as featured.
   */
  featured?: boolean
  children: ReactNode
}

export function Card({
  title,
  actions,
  featured = false,
  className,
  children,
  ...rest
}: CardProps) {
  const hasHeader = Boolean(title || actions)

  return (
    <div
      className={cn(
        'rounded-lg border border-subtle bg-raised p-6',
        featured ? 'bg-featured shadow-accent-glow' : 'shadow-card',
        className,
      )}
      {...rest}
    >
      {hasHeader && (
        <div className="mb-4 flex items-center justify-between gap-4">
          {title ? (
            <h2 className="text-h2 text-primary">{title}</h2>
          ) : (
            <span />
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  )
}
