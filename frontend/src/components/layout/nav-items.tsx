import type { ReactNode } from 'react'

export interface NavItem {
  to: string
  label: string
  icon: ReactNode
}

const iconProps = {
  className: 'size-5 shrink-0',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  'aria-hidden': true,
} as const

export const NAV_ITEMS: NavItem[] = [
  {
    to: '/overview',
    label: 'Overview',
    icon: (
      <svg {...iconProps}>
        <rect x="3" y="3" width="8" height="8" rx="1.5" />
        <rect x="13" y="3" width="8" height="5" rx="1.5" />
        <rect x="13" y="10" width="8" height="11" rx="1.5" />
        <rect x="3" y="13" width="8" height="8" rx="1.5" />
      </svg>
    ),
  },
  {
    to: '/workspace',
    label: 'Workspace',
    icon: (
      <svg {...iconProps}>
        <path d="M3 7l9-4 9 4-9 4-9-4z" />
        <path d="M3 12l9 4 9-4M3 17l9 4 9-4" />
      </svg>
    ),
  },
  {
    to: '/members',
    label: 'Members',
    icon: (
      <svg {...iconProps}>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20a6 6 0 0 1 12 0" />
        <path d="M16 6a3 3 0 0 1 0 6M21 20a6 6 0 0 0-4-5.6" />
      </svg>
    ),
  },
  {
    to: '/subscription',
    label: 'Subscription',
    icon: (
      <svg {...iconProps}>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M3 10h18" />
      </svg>
    ),
  },
]

/**
 * Shown only to platform staff (docs/operator-control-plane-spec.md). Kept
 * out of NAV_ITEMS — that array is unconditional; TopNavbar appends this one
 * entry when `useCurrentUser().isStaff` is true. The nav link is UX only;
 * the real boundary is `IsPlatformStaff` on the backend.
 *
 * `/admin` is the canonical operator surface (docs/operator-control-plane
 * -spec.md §D) — `/platform-admin` is now only a compatibility redirect to
 * it (AppRoutes.tsx), so this link points at the new path directly rather
 * than bouncing through the redirect on every click.
 */
export const PLATFORM_ADMIN_NAV_ITEM: NavItem = {
  to: '/admin',
  label: 'Platform Admin',
  icon: (
    <svg {...iconProps}>
      <path d="M12 3l8 4v5c0 5-3.4 8-8 9-4.6-1-8-4-8-9V7l8-4z" />
    </svg>
  ),
}
