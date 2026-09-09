/**
 * The frame every authenticated page renders inside (Tenora redesign).
 *
 * The wide, confident top bar (`TopNavbar`), then page content in a `<main>`
 * that uses the SAME centred outer frame as the navbar's inner container
 * (`mx-auto max-w-[1320px]` + matching gutters). So a page's left content edge
 * lines up with the wordmark, and the page has the same left/right relationship
 * to the viewport as the bar.
 *
 * Redesigned pages (Overview) place their wide editorial content
 * (`max-w-[1080px]`) LEFT-ALIGNED inside this centred frame — the frame is
 * centred, the reading content is not. The not-yet-redesigned pages keep their
 * own `mx-auto max-w-*` wrapper and are visually unchanged (their own centring
 * dominates; every one of them is narrower than this frame's content box).
 */

import { Outlet } from 'react-router-dom'

import { TopNavbar } from './TopNavbar'

export function AppShell() {
  return (
    <div className="min-h-screen bg-base text-primary">
      <TopNavbar />
      <main className="mx-auto w-full max-w-[1320px] px-4 pb-24 pt-8 sm:px-6 lg:px-10">
        <Outlet />
      </main>
    </div>
  )
}
