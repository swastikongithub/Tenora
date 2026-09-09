import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getStoredTheme,
  getSystemTheme,
  getTheme,
  setTheme,
  startThemeSync,
  subscribe,
  toggleTheme,
  THEME_STORAGE_KEY,
} from '../theme-store'

/**
 * Point `prefers-color-scheme` at a fixed answer and capture the `change`
 * listener so a test can simulate the OS theme flipping. jsdom has no real
 * matchMedia; test/setup.ts installs a permissive stub, which this overrides.
 */
function stubSystem(prefersLight: boolean) {
  const listeners = new Set<() => void>()
  let light = prefersLight
  window.matchMedia = ((query: string) => ({
    matches: query.includes('light') ? light : !light,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: (_: string, cb: () => void) => {
      listeners.add(cb)
    },
    removeEventListener: (_: string, cb: () => void) => {
      listeners.delete(cb)
    },
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
  return {
    flip(nowPrefersLight: boolean) {
      light = nowPrefersLight
      for (const cb of listeners) cb()
    },
  }
}

const originalMatchMedia = window.matchMedia

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
  document.documentElement.removeAttribute('data-theme')
})

describe('theme-store — resolution', () => {
  it('follows the OS setting when the user has made no choice', () => {
    stubSystem(true)
    expect(getStoredTheme()).toBeNull()
    expect(getSystemTheme()).toBe('light')
    expect(getTheme()).toBe('light')

    stubSystem(false)
    expect(getTheme()).toBe('dark')
  })

  it('defaults to dark when the OS preference cannot be read', () => {
    // Simulate an environment without matchMedia.
    ;(window as { matchMedia?: unknown }).matchMedia = undefined
    expect(getSystemTheme()).toBe('dark')
    expect(getTheme()).toBe('dark')
  })

  it('the <html data-theme> attribute wins once present', () => {
    stubSystem(true) // OS says light
    document.documentElement.setAttribute('data-theme', 'dark')
    expect(getTheme()).toBe('dark')
  })
})

describe('theme-store — explicit choice', () => {
  it('setTheme persists the choice and applies the attribute', () => {
    setTheme('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(getTheme()).toBe('light')
  })

  it('a stored choice overrides the OS preference on the next load', () => {
    stubSystem(false) // OS: dark
    setTheme('light')
    document.documentElement.removeAttribute('data-theme') // simulate reload, pre-script
    expect(getTheme()).toBe('light')
  })

  it('toggleTheme flips and persists', () => {
    setTheme('dark')
    toggleTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    toggleTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('notifies subscribers on change', () => {
    const seen = vi.fn()
    const unsubscribe = subscribe(seen)
    setTheme('light')
    setTheme('dark')
    expect(seen).toHaveBeenCalledTimes(2)
    unsubscribe()
    setTheme('light')
    expect(seen).toHaveBeenCalledTimes(2)
  })
})

describe('theme-store — startThemeSync', () => {
  it('applies the resolved theme and follows later OS changes until a choice is made', () => {
    const sys = stubSystem(false) // OS: dark
    const stop = startThemeSync()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    sys.flip(true) // user switches OS to light
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    stop()
  })

  it('stops following the OS once the user has chosen explicitly', () => {
    const sys = stubSystem(false)
    const stop = startThemeSync()

    setTheme('dark') // explicit choice (same value, but now "chosen")
    sys.flip(true) // OS goes light — must be ignored now
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    stop()
  })

  it('picks up an explicit choice made in another tab (storage event)', () => {
    stubSystem(false) // OS: dark
    const stop = startThemeSync()
    const seen = vi.fn()
    const unsub = subscribe(seen)

    // Another tab wrote the key; jsdom does not fire `storage` for same-window
    // localStorage writes, so simulate the event the browser would deliver.
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    window.dispatchEvent(
      new StorageEvent('storage', { key: THEME_STORAGE_KEY, newValue: 'light' }),
    )

    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(seen).toHaveBeenCalled()

    unsub()
    stop()
  })
})
