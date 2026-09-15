/**
 * Small landing-only building blocks. Visual tokens come from theme.css; CTA
 * links reuse the exact class vocabulary of the shared `Button` so a link and a
 * button look identical, without making `Button` polymorphic.
 *
 * Icons: Solar by 480 Design (CC BY 4.0), bundled offline via
 * @iconify-icons/solar — no runtime request to the Iconify API. Credited in the
 * landing footer.
 */

import { Icon, type IconifyIcon } from '@iconify/react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { cn } from '../lib/cn'

export function LandingIcon({ icon, className }: { icon: IconifyIcon; className?: string }) {
  return <Icon icon={icon} aria-hidden="true" className={cn('size-5 shrink-0', className)} />
}

const CTA_BASE =
  'inline-flex select-none items-center justify-center gap-2 rounded-md font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600'

const CTA_VARIANT = {
  primary: 'bg-accent-600 text-[var(--color-on-accent)] hover:bg-accent-500 focus-visible:shadow-accent-glow',
  secondary: 'bg-overlay text-primary border border-strong hover:bg-subtle',
  ghost: 'border border-subtle bg-transparent text-secondary hover:bg-overlay hover:text-primary',
}

const CTA_SIZE = {
  md: 'h-10 px-4 text-body',
  lg: 'h-12 px-6 text-body',
}

export function CtaLink({
  to,
  variant = 'primary',
  size = 'md',
  className,
  children,
}: {
  to: string
  variant?: keyof typeof CTA_VARIANT
  size?: keyof typeof CTA_SIZE
  className?: string
  children: ReactNode
}) {
  return (
    <Link to={to} className={cn(CTA_BASE, CTA_VARIANT[variant], CTA_SIZE[size], className)}>
      {children}
    </Link>
  )
}

/** Section frame: the same centred container as the app shell. */
export function Frame({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mx-auto w-full max-w-[1320px] px-4 sm:px-6 lg:px-10', className)}>{children}</div>
}

/** Numbered section opener: overline + large heading + optional lede. */
export function SectionHeading({
  id,
  index,
  overline,
  title,
  lede,
  className,
}: {
  id: string
  index: string
  overline: string
  title: string
  lede?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('max-w-[46rem]', className)}>
      <p className="flex items-center gap-3 font-mono text-caption uppercase tracking-[0.14em] text-secondary">
        <span className="text-accent-500">{index}</span>
        <span aria-hidden="true" className="ledger-line h-px w-8" />
        <span>{overline}</span>
      </p>
      <h2 id={id} data-split-heading className="mt-5 text-section tracking-[var(--tracking-hero)] text-primary text-balance">
        {title}
      </h2>
      {lede && <p className="mt-5 max-w-[40rem] text-lg leading-8 text-secondary">{lede}</p>}
    </div>
  )
}

/** A figure caption that keeps sample data honest. */
export function SampleTag({ className }: { className?: string }) {
  return (
    <span className={cn('font-mono text-caption uppercase tracking-[0.14em] text-secondary', className)}>
      Sample data
    </span>
  )
}
