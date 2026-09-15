/**
 * Public landing page (docs/TENORA_LANDING_PAGE_PLAN.md, proposal §K).
 *
 * Routing safety, honest content, accessibility, reduced-motion behaviour and
 * animation cleanup. jsdom has no layout, so these assert structure and
 * lifecycle; visual choreography is checked in the browser pass.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { AuthProvider } from '../../lib/auth'
import { createQueryClient } from '../../lib/query-client'
import { server } from '../../test/msw/server'
import { authHandlers, TENANT_A, tenantsMeHandler } from '../../test/fixtures'
import { AppRoutes } from '../../routes/AppRoutes'
import { LandingPage } from '../LandingPage'
import { lenisRef, railTravelDistance } from '../motion/useLandingMotion'
import {
  CLOSING_READING,
  ELECTRICITY_CENTS,
  OPENING_READING,
  PLAN_LIMITS,
  RATE_PER_UNIT_CENTS,
  SAMPLE_TOTAL_CENTS,
  UNITS,
} from '../sample-data'

const originalMatchMedia = window.matchMedia

function mockMatchMedia(matches: (query: string) => boolean) {
  window.matchMedia = ((query: string) => ({
    matches: matches(query),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
}

function renderRoutes(path: string, { signedIn = false } = {}) {
  if (signedIn) {
    sessionStorage.setItem('billing.refresh_token', 'valid-refresh')
    localStorage.setItem('billing.last_tenant_id', TENANT_A.id)
  }
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function renderLanding() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter>
          <LandingPage />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  server.use(...authHandlers(), tenantsMeHandler([TENANT_A]))
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
})

describe('routing', () => {
  it('serves the landing page at / to a signed-out visitor, without redirecting', async () => {
    renderRoutes('/')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Property management, without the paperwork.' }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Get started' })[0]).toHaveAttribute('href', '/register')
    expect(screen.getAllByRole('link', { name: 'Sign in' })[0]).toHaveAttribute('href', '/login')
  })

  it('still gates the app and the operator console', async () => {
    for (const path of ['/overview', '/workspace', '/admin', '/billing/bills']) {
      const view = renderRoutes(path)
      expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
      view.unmount()
    }
  })

  it('offers a signed-in visitor their workspace', async () => {
    renderRoutes('/', { signedIn: true })
    const nav = await screen.findByRole('banner')
    expect(await within(nav).findByRole('link', { name: 'Open workspace' })).toHaveAttribute('href', '/workspace')
  })

  it('links the auth pages back to the landing page', async () => {
    renderRoutes('/login')
    await screen.findByRole('heading', { name: 'Sign in' })
    expect(screen.getByRole('link', { name: 'Tenora home' })).toHaveAttribute('href', '/')
  })
})

describe('content', () => {
  it('shows the plan headline, CTAs, every section and the implemented plan limits', async () => {
    renderLanding()
    for (const name of [
      'The month closes in five different places.',
      'One chain of records, from workspace to receipt.',
      'Every amount on a bill explains itself.',
      'Record the payment. The receipt writes itself.',
      'Two sides of every bill.',
      'Plans sized to your portfolio.',
      'Close the month in one workspace.',
    ]) {
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument()
    }
    for (const plan of PLAN_LIMITS) {
      expect(
        screen.getByText(`Up to ${plan.workspaces} workspaces and up to ${plan.members} active members or residents in each.`),
      ).toBeInTheDocument()
    }
  })

  it('makes no unsupported claims', () => {
    const { container } = renderLanding()
    const text = container.textContent ?? ''
    for (const banned of [
      /testimonial/i,
      /trusted by/i,
      /customers?\b/i,
      /certified|certification/i,
      /\bSOC ?2\b|\bISO ?27001\b|\bPCI\b|\bGDPR\b/,
      /award/i,
      /partner/i,
      /pay online|online payment|pay your bill online|cashfree/i,
      /₹\s*\d[\d,]*\s*\/\s*(month|mo)\b.*plan/i,
      /lorem ipsum|placeholder|TODO/i,
      /weevolve/i,
    ]) {
      expect(text).not.toMatch(banned)
    }
  })

  it('keeps the sample bill arithmetic honest', () => {
    expect(UNITS).toBe(CLOSING_READING - OPENING_READING)
    expect(ELECTRICITY_CENTS).toBe(160 * RATE_PER_UNIT_CENTS)
    expect(SAMPLE_TOTAL_CENTS).toBe(1_200_000 + 128_000 + 50_000)
    renderLanding()
    const bill = screen.getByRole('figure', { name: /Sample Tenora bill/ })
    expect(within(bill).getByText('₹13,780.00')).toBeInTheDocument()
    expect(within(bill).getByText('Sample data')).toBeInTheDocument()
  })
})

describe('accessibility', () => {
  it('has one h1, landmarks and a working skip link', () => {
    renderLanding()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main')
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main')
  })

  it('explains a bill line on keyboard focus, not only on hover', async () => {
    renderLanding()
    const rent = screen.getByRole('button', { name: /^Rent/ })
    act(() => rent.focus())
    expect(rent).toHaveAttribute('aria-pressed', 'true')
    expect(rent).toHaveAccessibleDescription(/Lease for Unit 203/)
    expect(screen.getByText('₹12,000 a month since 1 Jan 2026')).toBeInTheDocument()
  })

  it('switches owner and resident views with the arrow keys', async () => {
    renderLanding()
    const owner = screen.getByRole('tab', { name: 'Owner' })
    act(() => owner.focus())
    await userEvent.keyboard('{ArrowRight}')
    const resident = screen.getByRole('tab', { name: 'Resident' })
    expect(resident).toHaveAttribute('aria-selected', 'true')
    expect(resident).toHaveFocus()
    expect(screen.getByRole('tabpanel', { name: 'Resident' })).toHaveTextContent(
      'Residents see their own bills — and nothing else.',
    )
  })

  it('opens the mobile menu as a dialog and closes it with Escape', async () => {
    renderLanding()
    const trigger = screen.getByRole('button', { name: 'Open menu' })
    await userEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Menu' })
    expect(within(dialog).getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '/register')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Menu' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open menu' })).toHaveFocus()
  })
})

describe('motion', () => {
  it('under reduced motion creates no smooth scroll, pins, splits or hidden states', () => {
    mockMatchMedia((q) => q.includes('prefers-reduced-motion: reduce') || !q.includes('prefers-reduced-motion'))
    const { container } = renderLanding()
    expect(ScrollTrigger.getAll()).toHaveLength(0)
    expect(lenisRef.current).toBeNull()
    for (const el of Array.from(container.querySelectorAll<HTMLElement>('[data-reveal], [data-bill-line], [data-hero-heading]'))) {
      expect(el.getAttribute('style') ?? '').not.toMatch(/opacity|transform|clip-path/)
    }
    expect(screen.getByRole('heading', { level: 1 }).querySelector('div, span')).toBeNull()
  })

  it('with motion allowed, builds the choreography and removes all of it on unmount', () => {
    mockMatchMedia((q) => !q.includes('prefers-reduced-motion: reduce'))
    // jsdom lacks ResizeObserver, which Lenis needs; browsers have it.
    const original = window.ResizeObserver
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
    const view = renderLanding()
    expect(ScrollTrigger.getAll().length).toBeGreaterThan(0)
    expect(lenisRef.current).not.toBeNull()
    // Split words stay hidden from assistive tech; the heading's name is whole.
    expect(
      screen.getByRole('heading', { level: 1, name: 'Property management, without the paperwork.' }),
    ).toBeInTheDocument()

    view.unmount()
    expect(ScrollTrigger.getAll()).toHaveLength(0)
    expect(lenisRef.current).toBeNull()
    expect(document.documentElement.classList.contains('lenis')).toBe(false)
    window.ResizeObserver = original
  })
})

describe('workflow rail geometry', () => {
  // Rendered values measured in Chromium at each pinned breakpoint: the Frame is
  // max-w 1320px centred with 40px padding, the track 2616px wide.
  const at = (vw: number) => {
    const frameWidth = Math.min(vw, 1320)
    const left = (vw - frameWidth) / 2
    return {
      rail: { left: 0, right: vw },
      frame: { left, right: left + frameWidth },
      framePaddingLeft: 40,
      framePaddingRight: 40,
      trackWidth: 2616,
      railWidth: vw,
    }
  }

  it.each([
    [1440, 1376],
    [1280, 1416],
    [1024, 1672],
    [1920, 1376],
  ])('at %ipx the last stop ends on the Frame content edge (travel %ipx)', (vw, expected) => {
    const g = at(vw)
    const travel = railTravelDistance(g)
    expect(travel).toBe(expected)
    const startInset = g.frame.left + g.framePaddingLeft
    const lastStopRight = startInset + g.trackWidth - travel
    expect(lastStopRight).toBe(g.frame.right - g.framePaddingRight)
    expect(lastStopRight).toBeLessThanOrEqual(vw)
  })

  it('never travels backwards when the track already fits', () => {
    expect(railTravelDistance({ ...at(1440), trackWidth: 400 })).toBe(0)
  })
})
