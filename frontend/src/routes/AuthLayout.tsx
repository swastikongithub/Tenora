/**
 * Shared split-panel shell for the auth pages (Login / Register / Verify),
 * redesigned for the Tenora system. Reused by every auth flow so they speak one
 * visual language.
 *
 * Responsive:
 *   - desktop (≥1280, `xl`): a 50/50 split — the `AuthArtPanel` (brand +
 *     editorial statement + quiet geometry) on the left, a hairline, then the
 *     focused sign-in column on the right, vertically centred.
 *   - tablet (768–1279, `md`): the panel collapses to a short top banner
 *     (`h-[36vh]`) — wordmark + eyebrow + a stepped-down headline over a
 *     cropped slice of the geometry.
 *   - mobile (<768): the panel is removed; the form column is full-width with
 *     its own wordmark on top (exactly one wordmark shows per breakpoint).
 *
 * `<main>` is `flex-1` so it always fills the viewport and vertically centres
 * its content whether or not the banner renders above it.
 *
 * The form column stays `max-w-[400px]` — Google Identity Services renders its
 * button at a fixed 400px width (see GoogleSignInButton), so the column must
 * match. The `<h1>` heading (Sign in / Create account / Verify your email) is
 * the page's one heading; the panel's headline is a `<p>`.
 */

import type { ReactNode } from 'react'

import { Wordmark } from '../components/layout/Wordmark'
import { AuthArtPanel } from './AuthArtPanel'

export interface AuthLayoutProps {
  heading: string
  subheading: string
  /** Art-panel eyebrow label — defaults to the Login copy. */
  panelEyebrow?: string
  /** Art-panel headline — defaults to the Login copy. */
  panelHeadline?: string
  children: ReactNode
}

export function AuthLayout({
  heading,
  subheading,
  panelEyebrow,
  panelHeadline,
  children,
}: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-base xl:grid xl:grid-cols-2">
      <AuthArtPanel
        className="hidden h-[36vh] shrink-0 border-b border-subtle md:block xl:h-full xl:border-b-0"
        eyebrow={panelEyebrow}
        headline={panelHeadline}
      />

      <main className="flex flex-1 items-center justify-center px-5 py-12 sm:px-8 xl:border-l xl:border-subtle">
        <div className="w-full max-w-[400px]">
          <Wordmark className="md:hidden" />
          <h1 className="mt-8 text-display text-primary md:mt-0">{heading}</h1>
          <p className="mt-2 text-body text-secondary">{subheading}</p>
          {children}
        </div>
      </main>
    </div>
  )
}
