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
 * Property billing (docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md §20, §43.11) —
 * navigation follows the viewer's role in the ACTIVE workspace.
 *
 *   OWNER    the four items above, plus the property-management surfaces:
 *            Properties, Residents, Billing (property billing — resident ->
 *            owner) and Payments, with Settings. Subscription (owner -> Tenora)
 *            stays: an owner has both relationships.
 *   MEMBER   (a resident) a deliberately narrow portal. No Subscription and no
 *            workspace administration; Billing replaces them.
 *
 * Hiding a link is UX only — every one of these surfaces is enforced server-side.
 */
const icon = (d: string) => (
  <svg {...iconProps}>
    <path d={d} />
  </svg>
)

export const OWNER_NAV_ITEMS: NavItem[] = [
  NAV_ITEMS[0],
  { to: '/properties', label: 'Properties', icon: icon('M4 21V8l8-5 8 5v13M9 21v-6h6v6') },
  { to: '/residents', label: 'Residents', icon: icon('M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0') },
  { to: '/billing', label: 'Billing', icon: icon('M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6') },
  { to: '/payments', label: 'Payments', icon: icon('M3 7h18v10H3zM3 11h18') },
  NAV_ITEMS[2],
  NAV_ITEMS[3],
  NAV_ITEMS[1],
  { to: '/settings', label: 'Settings', icon: icon('M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l2-1-2-4-2 1-2-2V4h-4v2L9 7 7 6 5 10l2 1v2l-2 1 2 4 2-1 2 2v2h4v-2l2-2 2 1 2-4-2-1z') },
]

export const RESIDENT_NAV_ITEMS: NavItem[] = [
  { to: '/home', label: 'Dashboard', icon: NAV_ITEMS[0].icon },
  { to: '/my-bills', label: 'My Bills', icon: icon('M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6') },
  { to: '/billing-history', label: 'Billing History', icon: icon('M12 8v4l3 2M21 12a9 9 0 1 1-9-9') },
  { to: '/receipts', label: 'Receipts', icon: icon('M5 3h14v18H5zM9 8h6M9 12h6M9 16h3') },
  { to: '/notifications', label: 'Notifications', icon: icon('M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0') },
  { to: '/settings', label: 'Settings', icon: icon('M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z') },
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
