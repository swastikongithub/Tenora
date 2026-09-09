/**
 * The horizontal top navbar (Tenora redesign).
 *
 *   left           the Tenora wordmark, linking to /overview
 *   following it   primary nav links (Overview / Workspace / Members /
 *                  Subscription, plus Platform Admin for platform staff only).
 *                  Text-only here — the vertical mobile panel keeps the icons.
 *                  The active route is marked MULTI-SIGNAL (§7 / §C.8): weight +
 *                  colour + an accent underline anchored to the bar's bottom
 *                  hairline — a tab, never colour alone. `NavLink` supplies
 *                  `aria-current="page"`.
 *   right (ml-auto) the tenant switcher (kept visible and separate from the
 *                  account menu at every breakpoint), then the avatar account
 *                  menu.
 *
 * The bar itself is WIDE and confident: full viewport width, a single thin
 * hairline underneath, sitting on the page ground (`bg-base` — "an edge, not a
 * container", design-reference-analysis §8.9). Its inner row is a generous
 * ~1320px container — deliberately WIDER than the narrow left-aligned editorial
 * content column below it; the two need not share a width.
 *
 * Responsive: the links collapse behind a hamburger below 1024px — wider than a
 * literal tablet breakpoint, so the switcher keeps a readable width in the
 * 768–1023 band. The switcher and avatar never move into the hamburger panel.
 * The desktop nav and the mobile panel are conditionally rendered (not
 * CSS-hidden) so "the primary nav is behind the hamburger" is literally true in
 * the DOM.
 */

import { useEffect } from 'react'
import { Link, NavLink } from 'react-router-dom'

import { cn } from '../../lib/cn'
import { AccountMenu } from './AccountMenu'
import { NAV_ITEMS, PLATFORM_ADMIN_NAV_ITEM } from './nav-items'
import { TenantSwitcher } from './TenantSwitcher'
import { useCurrentUser } from './use-current-user'
import { useDisclosure } from './use-disclosure'
import { useMediaQuery } from '../use-media-query'
import { Wordmark } from './Wordmark'

/** Wide inner container — deliberately not the content column's width. */
const CONTAINER = 'mx-auto w-full max-w-[1320px] px-4 sm:px-6 lg:px-10'
const BAR = cn('flex h-16 items-center gap-3 sm:gap-6 lg:gap-8', CONTAINER)

/** Desktop nav item: a full-height tab whose active state carries an accent
 *  underline on the bar's bottom hairline — plus weight + colour (multi-signal). */
const desktopLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex h-16 items-center border-b-2 text-label transition-colors',
    'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-600',
    isActive
      ? 'border-accent-600 font-medium text-primary'
      : 'border-transparent text-secondary hover:text-primary',
  )

/** Mobile panel nav item: a left accent-border marker instead of the underline. */
const panelLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex items-center gap-3 border-l-2 py-2.5 pl-3 text-label transition-colors',
    'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-600',
    isActive
      ? 'border-accent-600 font-medium text-primary'
      : 'border-transparent text-secondary hover:text-primary',
  )

export function TopNavbar() {
  const isDesktop = useMediaQuery('(min-width: 1024px)')
  const menu = useDisclosure()
  const { isStaff } = useCurrentUser()

  // Platform staff get one extra nav entry. Appended, not built into
  // NAV_ITEMS — see nav-items.tsx. The link is UX only; IsPlatformStaff on
  // the backend is the real boundary.
  const navItems = isStaff
    ? [...NAV_ITEMS, PLATFORM_ADMIN_NAV_ITEM]
    : NAV_ITEMS

  // Fold the mobile panel away when the viewport grows to desktop.
  useEffect(() => {
    if (isDesktop) menu.close()
  }, [isDesktop, menu])

  return (
    <header className="sticky top-0 z-30 border-b border-subtle bg-base">
      <div className={BAR}>
        <Link
          to="/overview"
          aria-label="Tenora — go to overview"
          className="shrink-0 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
        >
          <Wordmark />
        </Link>

        {isDesktop ? (
          <nav aria-label="Primary" className="min-w-0">
            <ul className="flex items-center gap-6">
              {navItems.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} className={desktopLinkClass}>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        ) : (
          <button
            type="button"
            aria-label="Open navigation"
            aria-controls="mobile-nav-panel"
            aria-expanded={menu.open}
            onClick={menu.toggle}
            ref={menu.triggerRef}
            className="grid size-9 shrink-0 place-items-center rounded-md border border-subtle text-secondary hover:bg-overlay hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600"
          >
            <svg
              className="size-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        )}

        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
          <div className="w-[132px] sm:w-[190px] lg:w-[220px]">
            <TenantSwitcher />
          </div>
          <AccountMenu />
        </div>
      </div>

      {!isDesktop && menu.open && (
        <div
          ref={menu.panelRef}
          id="mobile-nav-panel"
          className="border-t border-subtle bg-base"
        >
          <nav aria-label="Primary" className={cn('py-2', CONTAINER)}>
            <ul className="flex flex-col">
              {navItems.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    onClick={menu.close}
                    className={panelLinkClass}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      )}
    </header>
  )
}
