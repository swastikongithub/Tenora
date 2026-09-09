import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { AuthArtPanel } from '../AuthArtPanel'

/** Stub `matchMedia` so `useMediaQuery('(prefers-reduced-motion: reduce)')`
 *  returns a known value. Everything else matches (the panel only queries the
 *  one media string). */
function stubReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('reduced-motion') ? reduce : true,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

const originalMatchMedia = window.matchMedia

beforeEach(() => {
  document.documentElement.removeAttribute('data-theme')
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
  document.documentElement.removeAttribute('data-theme')
})

describe('AuthArtPanel', () => {
  it('renders the eyebrow and headline as real, non-decorative page text', () => {
    stubReducedMotion(true)
    const { getByText } = render(
      <AuthArtPanel
        eyebrow="Multi-tenant billing"
        headline="Every charge, every tenant, accounted for."
      />,
    )

    const eyebrow = getByText('Multi-tenant billing')
    const headline = getByText('Every charge, every tenant, accounted for.')

    // A screen reader must reach these — NOT inside the aria-hidden decor.
    expect(eyebrow.closest('[aria-hidden="true"]')).toBeNull()
    expect(headline.closest('[aria-hidden="true"]')).toBeNull()
  })

  it('accepts custom eyebrow / headline copy', () => {
    stubReducedMotion(true)
    const { getByText } = render(
      <AuthArtPanel eyebrow="Custom label" headline="A different headline." />,
    )
    expect(getByText('Custom label')).toBeInTheDocument()
    expect(getByText('A different headline.')).toBeInTheDocument()
  })

  it('keeps the geometric backdrop and the drifting planes inside the aria-hidden layer', () => {
    stubReducedMotion(true)
    const { container } = render(<AuthArtPanel />)

    const decor = container.querySelector('.authart__decor')
    expect(decor).toHaveAttribute('aria-hidden', 'true')

    const svg = container.querySelector('svg')
    expect(svg?.closest('.authart__decor')).toBe(decor)

    for (const cls of [
      '.authart__plane--1',
      '.authart__plane--2',
      '.authart__plane--3',
    ]) {
      const el = container.querySelector(cls)
      expect(el).toBeInTheDocument()
      expect(el?.closest('.authart__decor')).toBe(decor)
    }
  })

  it('has no interactive content — the panel is a visual, not a control', () => {
    stubReducedMotion(true)
    const { container } = render(<AuthArtPanel />)
    expect(
      container.querySelector('.authart a, .authart button, .authart input'),
    ).toBeNull()
  })

  it('draws each angular plane as a gradient-filled polygon', () => {
    stubReducedMotion(true)
    const { container } = render(<AuthArtPanel />)
    const polygons = Array.from(
      container.querySelectorAll('.authart__plane polygon'),
    )
    expect(polygons.length).toBe(3)
    for (const polygon of polygons) {
      expect(polygon.getAttribute('fill')).toMatch(/^url\(#/)
    }
  })

  it('disables plane drift entirely when prefers-reduced-motion is set', () => {
    stubReducedMotion(true)
    const { container } = render(<AuthArtPanel />)
    expect(container.querySelector('.authart')).toHaveAttribute(
      'data-motion',
      'reduced',
    )
    // The planes still render — they just hold still.
    expect(container.querySelectorAll('.authart__plane').length).toBe(3)
  })

  it('drifts the planes when reduced motion is not requested', () => {
    stubReducedMotion(false)
    const { container } = render(<AuthArtPanel />)
    expect(container.querySelector('.authart')).toHaveAttribute(
      'data-motion',
      'full',
    )
  })

  it('renders without error in the light theme', () => {
    stubReducedMotion(true)
    document.documentElement.setAttribute('data-theme', 'light')
    const { getByText } = render(<AuthArtPanel headline="Light headline." />)
    expect(getByText('Light headline.')).toBeInTheDocument()
  })

  it('accepts an extra className without dropping the base class', () => {
    stubReducedMotion(true)
    const { container } = render(<AuthArtPanel className="hidden h-40" />)
    const panel = container.querySelector('.authart')
    expect(panel).toHaveClass('authart', 'hidden', 'h-40')
  })
})
