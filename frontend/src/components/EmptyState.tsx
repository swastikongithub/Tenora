import type { ReactNode } from 'react'
import { cn } from '../lib/cn'

export interface EmptyStateProps {
  /** Defaults to a neutral placeholder glyph so the panel is never blank. */
  icon?: ReactNode
  headline: string
  description: string
  /** Optional primary action — typically a <Button>. */
  action?: ReactNode
  className?: string
}

export function EmptyState({
  icon,
  headline,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 px-6 py-12 text-center',
        className,
      )}
    >
      {/* The glyph is decorative — text-muted is acceptable here (§C.8 rule). */}
      <div className="text-muted">{icon ?? <DefaultIcon />}</div>
      <h2 className="text-h2 text-primary">{headline}</h2>
      <p className="max-w-sm text-body text-secondary">{description}</p>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}

function DefaultIcon() {
  return (
    <svg
      className="size-8"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      role="presentation"
      aria-hidden="true"
    >
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 4v5" />
    </svg>
  )
}
