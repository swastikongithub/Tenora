/**
 * Landing navigation: wordmark, in-page anchors, Sign in / Get started.
 * A visitor with a live session sees "Open workspace" instead (decision H-D2).
 * The auth check never blocks rendering: while the silent refresh is still
 * resolving, the signed-out CTAs show.
 *
 * Mobile: a sheet with a focus trap and Escape-to-close (the navbar's own
 * useDisclosure + useFocusTrap), closing on any link choice.
 */

import hamburger from '@iconify-icons/solar/hamburger-menu-linear'
import closeIcon from '@iconify-icons/solar/close-circle-linear'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ThemeToggle } from '../components/ThemeToggle'
import { useDisclosure } from '../components/layout/use-disclosure'
import { useFocusTrap } from '../components/layout/use-focus-trap'
import { Wordmark } from '../components/layout/Wordmark'
import { useAuth } from '../lib/auth'
import { cn } from '../lib/cn'
import { CtaLink, Frame, LandingIcon } from './ui'

const ANCHORS = [
  { href: '#workflow', label: 'Workflow' },
  { href: '#billing', label: 'Billing' },
  { href: '#residents', label: 'Residents' },
  { href: '#pricing', label: 'Pricing' },
]

export function LandingNav() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  const [scrolled, setScrolled] = useState(false)
  const menu = useDisclosure()
  useFocusTrap(menu.open, menu.panelRef)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      data-hero-nav
      className={cn(
        'sticky top-0 z-40 border-b bg-base/90 backdrop-blur-sm transition-colors',
        scrolled ? 'border-subtle' : 'border-transparent',
      )}
    >
      <Frame className="flex h-16 items-center gap-6">
        <Link
          to="/"
          aria-label="Tenora home"
          className="rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent-600"
        >
          <Wordmark />
        </Link>

        <nav aria-label="Primary" className="hidden flex-1 justify-center md:flex">
          <ul className="flex items-center gap-7">
            {ANCHORS.map((a) => (
              <li key={a.href}>
                <a
                  href={a.href}
                  className="rounded-sm text-label text-secondary transition-colors hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent-600"
                >
                  {a.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto hidden items-center gap-3 md:flex">
          <ThemeToggle />
          {signedIn ? (
            <CtaLink to="/workspace">Open workspace</CtaLink>
          ) : (
            <>
              <CtaLink to="/login" variant="ghost">
                Sign in
              </CtaLink>
              <CtaLink to="/register">Get started</CtaLink>
            </>
          )}
        </div>

        <button
          ref={menu.triggerRef}
          type="button"
          onClick={menu.toggle}
          aria-expanded={menu.open}
          aria-controls="landing-menu"
          className="ml-auto inline-flex size-11 items-center justify-center rounded-md border border-subtle text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-600 md:hidden"
        >
          <LandingIcon icon={menu.open ? closeIcon : hamburger} />
          <span className="sr-only">{menu.open ? 'Close menu' : 'Open menu'}</span>
        </button>
      </Frame>

      {menu.open && (
        <div
          ref={menu.panelRef}
          id="landing-menu"
          role="dialog"
          aria-modal="true"
          aria-label="Menu"
          className="landing-fade border-t border-subtle bg-base md:hidden"
        >
          <Frame className="flex flex-col gap-1 py-4">
            <nav aria-label="Sections">
              <ul className="flex flex-col">
                {ANCHORS.map((a) => (
                  <li key={a.href}>
                    <a
                      href={a.href}
                      onClick={menu.close}
                      className="flex h-12 items-center rounded-md px-2 text-body text-primary focus-visible:outline-2 focus-visible:outline-accent-600"
                    >
                      {a.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="mt-3 grid grid-cols-1 gap-3 border-t border-subtle pt-4">
              <ThemeToggle label className="h-12" />
              {signedIn ? (
                <CtaLink to="/workspace" size="lg">
                  Open workspace
                </CtaLink>
              ) : (
                <>
                  <CtaLink to="/register" size="lg">
                    Get started
                  </CtaLink>
                  <CtaLink to="/login" variant="secondary" size="lg">
                    Sign in
                  </CtaLink>
                </>
              )}
            </div>
          </Frame>
        </div>
      )}
    </header>
  )
}
