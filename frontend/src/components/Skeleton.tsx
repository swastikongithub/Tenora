import type { CSSProperties } from 'react'
import { cn } from '../lib/cn'

export interface SkeletonProps {
  /** CSS width — number (px) or any length string. Defaults to full width. */
  width?: number | string
  /** CSS height — number (px) or any length string. */
  height?: number | string
  /** Number of stacked blocks (e.g. table rows). */
  count?: number
  radius?: 'sm' | 'md' | 'lg' | 'full'
  className?: string
  /** Accessible label announced while content loads. */
  label?: string
}

const RADIUS: Record<NonNullable<SkeletonProps['radius']>, string> = {
  sm: 'rounded-sm',
  md: 'rounded-md',
  lg: 'rounded-lg',
  full: 'rounded-full',
}

const dim = (v: number | string | undefined): string | undefined =>
  typeof v === 'number' ? `${v}px` : v

export function Skeleton({
  width,
  height = 16,
  count = 1,
  radius = 'md',
  className,
  label = 'Loading',
}: SkeletonProps) {
  const style: CSSProperties = { width: dim(width), height: dim(height) }

  return (
    <div role="status" aria-live="polite" aria-busy="true" className="flex flex-col gap-2">
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          aria-hidden="true"
          style={style}
          className={cn(
            'w-full animate-pulse bg-overlay',
            RADIUS[radius],
            className,
          )}
        />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  )
}
