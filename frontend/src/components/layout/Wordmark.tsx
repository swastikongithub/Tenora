/**
 * The product wordmark — "Tenora" (Tenora redesign).
 *
 * Was a rounded accent-box "B" glyph + "Billing Engine". The rounded glyph box
 * read as "friendly startup", a character design-reference-analysis §5.8
 * explicitly rejects; the redesign uses a flat, exact mark instead: a small
 * SOLID accent square on the baseline, then the name in a tight quiet weight.
 * No container, no rounding.
 *
 * Deliberately not a link: `AuthLayout` renders it plain, `TopNavbar` wraps it
 * in a `<Link to="/overview">`. `labelClassName` lets the navbar hide the text
 * on the narrowest viewports (glyph-only) without touching the auth pages.
 */

import { cn } from '../../lib/cn'

export function Wordmark({
  className,
  labelClassName,
}: {
  className?: string
  labelClassName?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-2.5 text-primary', className)}>
      <span aria-hidden="true" className="size-2 shrink-0 bg-accent-600" />
      <span
        className={cn('text-label font-semibold tracking-tight', labelClassName)}
      >
        Tenora
      </span>
    </span>
  )
}
