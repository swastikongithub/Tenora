import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { ThemeProvider } from '../../../lib/theme'
import { ThemeToggle } from '../ThemeToggle'

function stubSystem(prefersLight: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('light') ? prefersLight : !prefersLight,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
}

const originalMatchMedia = window.matchMedia

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  stubSystem(false) // start in dark
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
  document.documentElement.removeAttribute('data-theme')
})

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  )
}

describe('ThemeToggle', () => {
  it('is a toggle button reporting whether dark mode is on', () => {
    renderToggle()
    const btn = screen.getByRole('button', { name: /dark mode/i })
    expect(btn).toHaveAttribute('aria-pressed', 'true')
  })

  it('is keyboard reachable and operable', async () => {
    const user = userEvent.setup()
    renderToggle()
    const btn = screen.getByRole('button', { name: /dark mode/i })

    await user.tab()
    expect(btn).toHaveFocus()

    await user.keyboard('{Enter}')
    expect(btn).toHaveAttribute('aria-pressed', 'false')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    await user.keyboard(' ')
    expect(btn).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('toggles the theme on click', async () => {
    const user = userEvent.setup()
    renderToggle()
    const btn = screen.getByRole('button', { name: /dark mode/i })

    await user.click(btn)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(btn).toHaveAttribute('aria-pressed', 'false')
  })
})
