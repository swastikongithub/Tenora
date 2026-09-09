import type { InputHTMLAttributes } from 'react'
import { useId } from 'react'
import { cn } from '../lib/cn'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  /** Caption-style text below the field. Turns danger-colored when `error`. */
  helperText?: string
  error?: boolean
}

export function Input({
  label,
  helperText,
  error = false,
  id,
  className,
  ...rest
}: InputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const helperId = `${inputId}-helper`

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-label text-secondary">
        {label}
      </label>

      <input
        id={inputId}
        aria-invalid={error || undefined}
        aria-describedby={helperText ? helperId : undefined}
        className={cn(
          'h-10 rounded-sm bg-base px-3 text-body text-primary',
          'border placeholder:text-muted',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600',
          'disabled:cursor-not-allowed disabled:opacity-50',
          error ? 'border-danger' : 'border-strong',
          className,
        )}
        {...rest}
      />

      {helperText && (
        <p
          id={helperId}
          className={cn(
            'text-caption',
            // Meaningful helper text uses text-secondary (readable); the muted
            // token is not used for content a user must read (§C.8 usage rule).
            error ? 'text-danger' : 'text-secondary',
          )}
        >
          {helperText}
        </p>
      )}
    </div>
  )
}
