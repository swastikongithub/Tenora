/**
 * `/` — the public Tenora marketing page (docs/TENORA_LANDING_PAGE_PLAN.md,
 * approved proposal A–L). Loaded lazily from AppRoutes, so none of GSAP, Lenis
 * or the landing sections ship with the authenticated app, and the app's pages
 * don't ship with the landing page.
 *
 * Section order and narrative purpose: proposal §D. Motion: useLandingMotion
 * (proposal §E). Every section is complete without JavaScript animation.
 */

import { useRef } from 'react'

import './landing.css'
import { LandingNav } from './LandingNav'
import { useLandingMotion } from './motion/useLandingMotion'
import { AgingReporting, BillingEngine, PaymentsReceipts } from './sections/Billing'
import { FinalCta, LandingFooter, Pricing, Trust, TwoSides } from './sections/Closing'
import { Hero } from './sections/Hero'
import { Portfolio, Problem, WorkflowRail } from './sections/Story'

export function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null)
  useLandingMotion(rootRef)

  return (
    <div ref={rootRef} className="min-h-screen bg-base text-primary">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-accent-600 focus:px-4 focus:py-2 focus:text-label focus:text-[var(--color-on-accent)]"
      >
        Skip to content
      </a>
      <LandingNav />
      <main id="main" tabIndex={-1} className="outline-none">
        <Hero />
        <Problem />
        <WorkflowRail />
        <Portfolio />
        <BillingEngine />
        <PaymentsReceipts />
        <AgingReporting />
        <TwoSides />
        <Trust />
        <Pricing />
        <FinalCta />
      </main>
      <LandingFooter />
    </div>
  )
}

export default LandingPage
