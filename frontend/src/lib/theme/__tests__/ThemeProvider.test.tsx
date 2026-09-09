import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { ThemeProvider } from '../ThemeProvider'
import { useTheme } from '../theme-context'
import { THEME_STORAGE_KEY } from '../theme-store'

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

function Probe() {
  const { theme, toggleTheme, setTheme } = useTheme()
  return (
    <div>
      <output data-testid="theme">{theme}</output>
      <button onClick={toggleTheme}>toggle</button>
      <button onClick={() => setTheme('light')}>go light</button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeProvider', () => {
  it('exposes the system theme on first render when no choice is stored', () => {
    stubSystem(true)
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    // Correct on the very first render — no loading state, no second-paint swap.
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('respects a data-theme attribute already set by the pre-paint script', () => {
    stubSystem(true) // OS says light...
    document.documentElement.setAttribute('data-theme', 'dark') // ...script said dark
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('toggle updates the attribute, the context value, and persistence', async () => {
    stubSystem(false) // OS: dark
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')

    await userEvent.click(screen.getByText('toggle'))
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')

    await userEvent.click(screen.getByText('toggle'))
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
  })

  it('a component using useTheme without a provider still works off the store', async () => {
    stubSystem(false)
    render(<Probe />)
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')

    await userEvent.click(screen.getByText('go light'))
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
