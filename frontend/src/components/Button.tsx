import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '../lib/cn'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Loading: the spinner replaces the label and the button keeps its width. */
  loading?: boolean
  children: ReactNode
}

const VARIANT: Record<ButtonVariant, string> = {
  // The accent glow (§C.1a) composes with — does not replace — the shared
  // focus-visible outline ring below: the glow's `0 0 0 1px accent-600` hugs
  // the border edge, the 2px-offset outline sits just outside it, and the
  // 24px blur reads as a soft purple halo behind both.
  // `text-[var(--color-on-accent)]`, not `text-primary`: the label sits on the
  // accent-600 fill, and `text-primary` flips to near-black in light mode (3.5:1
  // on the purple — a fail). `--color-on-accent` is near-white in both themes
  // (dark value #F4F4F6 = the old `text-primary`, so dark rendering is
  // unchanged). Same explicit-var pattern the danger variant already uses.
  primary:
    'bg-accent-600 text-[var(--color-on-accent)] hover:bg-accent-500 focus-visible:shadow-accent-glow',
  secondary:
    'bg-overlay text-primary border border-strong hover:bg-subtle',
  // §C.1a fix: a visible border by default (was borderless and unreadable
  // against bg-base) plus the bg-overlay hover already present. The
  // focus-visible ring is inherited from the shared class list below, same as
  // every other variant — it was never missing here, only visually unframed.
  ghost:
    'border border-subtle bg-transparent text-secondary hover:bg-overlay hover:text-primary',
  // Dark text on the danger fill — the base surface colour. Written as an
  // explicit var() rather than `text-base` (which resolves to this same colour
  // here) so it does not read like a font-size utility.
  danger: 'bg-danger text-[var(--color-base)] hover:bg-danger/90',
}

const SIZE: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-label',
  md: 'h-10 px-4 text-body',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  type = 'button',
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'relative inline-flex select-none items-center justify-center gap-2',
        'rounded-md font-medium transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
        'disabled:pointer-events-none disabled:opacity-50',
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...rest}
    >
      {/* Label stays mounted while loading (visibility:hidden) so the button's
          width never changes between resting and loading states. */}
      <span
        className={cn(
          'inline-flex items-center gap-2',
          loading && 'invisible',
        )}
        aria-hidden={loading || undefined}
      >
        {children}
      </span>

      {loading && (
        <span className="absolute inset-0 flex items-center justify-center">
          <Spinner />
          <span className="sr-only">Loading</span>
        </span>
      )}
    </button>
  )
}

function Spinner() {
  return (
    <svg
      className="size-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      role="presentation"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  )
}
