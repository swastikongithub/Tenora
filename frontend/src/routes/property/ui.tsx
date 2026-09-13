/**
 * Small, property-billing-specific presentation pieces built on the shared
 * primitives (Badge, Card, Alert, Button). Kept here rather than in
 * components/ because each encodes a billing concept (a bill status, an aging
 * bucket, a plan quota), not a generic UI element.
 */

import { useId, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { NavLink } from 'react-router-dom'

import { Alert, Badge, Button, Skeleton } from '../../components'
import type { BadgeVariant } from '../../components'
import { errorMessage } from '../../lib/property/errors'
import { cn } from '../../lib/cn'
import { STATUS_LABEL } from '../../lib/property/format'

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
  eyebrow?: string
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="text-caption uppercase tracking-wide text-secondary">{eyebrow}</p>}
        <h1 className="text-display text-primary">{title}</h1>
        {description && <p className="mt-1 max-w-[62ch] text-body text-secondary">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

export function StatTile({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'danger' | 'success' | 'warning'
}) {
  return (
    <div className="rounded-md border border-subtle bg-raised p-4">
      <p className="text-caption text-secondary">{label}</p>
      <p
        className={cn(
          'mt-1 font-mono text-xl tabular-nums text-primary',
          tone === 'danger' && 'text-danger',
          tone === 'success' && 'text-success',
          tone === 'warning' && 'text-warning',
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-caption text-secondary">{hint}</p>}
    </div>
  )
}

export function StatGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
}

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  DRAFT: 'neutral',
  PUBLISHED: 'warning',
  PARTIALLY_PAID: 'accent',
  PAID: 'success',
  CANCELLED: 'neutral',
  OVERDUE: 'danger',
}

/** Multi-signal status: colour AND a text label, plus the overdue duration. */
export function BillStatusBadge({ status, overdueDays }: { status: string; overdueDays?: number }) {
  const label = STATUS_LABEL[status] ?? status
  return (
    <Badge variant={STATUS_VARIANT[status] ?? 'neutral'}>
      {status === 'OVERDUE' && overdueDays ? `${label} · ${overdueDays}d` : label}
    </Badge>
  )
}

/** Plan usage (§43.9): healthy / approaching / reached, stated in words too. */
export function UsageMeter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 100
  const state = used >= limit ? 'reached' : pct >= 80 ? 'approaching' : 'healthy'
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-label text-primary">{label}</span>
        <span className="font-mono text-label tabular-nums text-primary">
          {used} / {limit}
        </span>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-overlay"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={used}
      >
        <div
          className={cn(
            'h-full rounded-full',
            state === 'reached' ? 'bg-danger' : state === 'approaching' ? 'bg-warning' : 'bg-accent-600',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      {state !== 'healthy' && (
        <p className={cn('mt-1 text-caption', state === 'reached' ? 'text-danger' : 'text-warning')}>
          {state === 'reached' ? 'Limit reached — upgrade your plan to add more.' : 'Approaching your plan limit.'}
        </p>
      )}
    </div>
  )
}

export function SubNav({ items, label }: { items: Array<{ to: string; label: string; end?: boolean }>; label: string }) {
  return (
    <nav aria-label={label} className="mb-6 overflow-x-auto border-b border-subtle">
      <ul className="flex gap-5">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'inline-flex h-10 items-center whitespace-nowrap border-b-2 text-label',
                  isActive ? 'border-accent-600 font-medium text-primary' : 'border-transparent text-secondary hover:text-primary',
                )
              }
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

const CONTROL =
  'h-10 rounded-sm border border-strong bg-base px-3 text-body text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600 disabled:opacity-50'

export function Select({
  label,
  helperText,
  error,
  children,
  className,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; helperText?: string; error?: boolean }) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-label text-secondary">
        {label}
      </label>
      <select id={id} className={cn(CONTROL, error && 'border-danger', className)} aria-invalid={error || undefined} {...rest}>
        {children}
      </select>
      {helperText && <p className={cn('text-caption', error ? 'text-danger' : 'text-secondary')}>{helperText}</p>}
    </div>
  )
}

export function TextArea({
  label,
  helperText,
  error,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; helperText?: string; error?: boolean }) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-label text-secondary">
        {label}
      </label>
      <textarea id={id} rows={3} className={cn(CONTROL, 'h-auto py-2', error && 'border-danger')} {...rest} />
      {helperText && <p className={cn('text-caption', error ? 'text-danger' : 'text-secondary')}>{helperText}</p>}
    </div>
  )
}

export function QueryState({
  isLoading,
  error,
  onRetry,
  label,
}: {
  isLoading: boolean
  error: unknown
  onRetry?: () => void
  label: string
}) {
  if (isLoading) return <Skeleton count={3} height={48} label={`Loading ${label}`} />
  if (error)
    return (
      <Alert
        variant="danger"
        action={
          onRetry && (
            <Button size="sm" variant="secondary" onClick={onRetry}>
              Retry
            </Button>
          )
        }
      >
        {errorMessage(error, `Couldn’t load ${label}.`)}
      </Alert>
    )
  return null
}

export function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-medium text-primary">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  )
}
