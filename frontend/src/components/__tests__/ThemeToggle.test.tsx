/**
 * The shared Eclipse ThemeToggle: one control, driven by the existing theme
 * store (no local state, no second storage key), used by the account menu,
 * the landing nav and the auth pages.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { LandingNav } from '../../landing/LandingNav'
import { AuthProvider } from '../../lib/auth'
import { createQueryClient } from '../../lib/query-client'
import { THEME_STORAGE_KEY, ThemeProvider } from '../../lib/theme'
import { RegisterPage } from '../../routes/RegisterPage'
import { ThemeToggle as AccountMenuThemeToggle } from '../layout/ThemeToggle'
import { ThemeToggle } from '../ThemeToggle'

function stubSystem(prefersLight: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('prefers-color-scheme: light') ? prefersLight : query.includes('prefers-color-scheme: dark') ? !prefersLight : true,
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
  stubSystem(true) // a light-OS visitor with no stored choice
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
  document.documentElement.removeAttribute('data-theme')
})

const theme = () => document.documentElement.getAttribute('data-theme')

function withProviders(ui: React.ReactNode) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={createQueryClient()}>
        <AuthProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

describe('shared ThemeToggle', () => {
  it('renders the Eclipse control as a labelled toggle button in the resolved theme', () => {
    render(withProviders(<ThemeToggle />))
    const button = screen.getByRole('button', { name: 'Dark mode' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(button.querySelector('svg[aria-hidden="true"] circle')).not.toBeNull()
    expect(theme()).toBe('light')
  })

  it('switches light → dark → light through the existing store and its storage key', async () => {
    const user = userEvent.setup()
    render(withProviders(<ThemeToggle />))
    const button = screen.getByRole('button', { name: 'Dark mode' })

    await user.click(button)
    expect(theme()).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(button).toHaveClass('dark')

    await user.click(button)
    expect(theme()).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(button).toHaveClass('light')
    // No second key was invented.
    expect(Object.keys(localStorage).filter((k) => /theme/i.test(k))).toEqual([THEME_STORAGE_KEY])
  })

  it('keeps every placement in sync — one source of truth', async () => {
    const user = userEvent.setup()
    render(
      withProviders(
        <>
          <ThemeToggle />
          <AccountMenuThemeToggle />
        </>,
      ),
    )
    const [first, second] = screen.getAllByRole('button', { name: 'Dark mode' })
    await user.click(first)
    expect(second).toHaveAttribute('aria-pressed', 'true')
    await user.click(second)
    expect(first).toHaveAttribute('aria-pressed', 'false')
  })

  it('starts from a stored choice (persistence across reloads)', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    render(withProviders(<ThemeToggle />))
    expect(screen.getByRole('button', { name: 'Dark mode' })).toHaveAttribute('aria-pressed', 'true')
    expect(theme()).toBe('dark')
  })

  it('the account-menu row is the same control with a visible, clickable caption', async () => {
    const user = userEvent.setup()
    render(withProviders(<AccountMenuThemeToggle />))
    await user.click(screen.getByText('Dark mode'))
    expect(theme()).toBe('dark')
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })
})

describe('placements', () => {
  it('landing navigation: beside the auth CTAs and inside the mobile menu', async () => {
    const user = userEvent.setup()
    render(withProviders(<LandingNav />))
    const banner = screen.getByRole('banner')
    expect(within(banner).getByRole('button', { name: 'Dark mode' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    const menu = screen.getByRole('dialog', { name: 'Menu' })
    const menuToggle = within(menu).getByRole('button', { name: 'Dark mode' })
    await user.click(menuToggle)
    expect(theme()).toBe('dark')
    expect(screen.getByRole('dialog', { name: 'Menu' })).toBeInTheDocument()
  })

  it('sign-up page: rendered by the shared auth layout', async () => {
    render(withProviders(<RegisterPage />))
    const toggle = await screen.findByRole('button', { name: 'Dark mode' })
    act(() => toggle.click())
    expect(theme()).toBe('dark')
  })
})
