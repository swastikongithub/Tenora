/**
 * The theme engine — framework-free, one module-level source of truth.
 *
 * Why a store and not just context: the `data-theme` attribute on <html> is
 * already authoritative from the first paint (index.html's inline script sets
 * it). This module keeps React in sync with that attribute and owns the two
 * writes that can change it — an explicit user choice (persisted) and the OS
 * `prefers-color-scheme` following that applies only until a choice is made.
 *
 * `ThemeProvider` is the spec-required React seam (§4.1) but it is thin: it just
 * drives this store's lifecycle. `useTheme` reads the store, so a component that
 * renders without a provider (some unit tests) still gets a real, reactive value
 * instead of a crash — theme is display chrome, not an authorization concern.
 */

export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'billing.theme'

const listeners = new Set<() => void>()

function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark'
}

/** The OS preference, or `'dark'` when it can't be read (dark is the default). */
export function getSystemTheme(): Theme {
  try {
    return window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark'
  } catch {
    return 'dark'
  }
}

/** The user's explicitly-chosen theme, or `null` if they've never chosen. */
export function getStoredTheme(): Theme | null {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    return isTheme(raw) ? raw : null
  } catch {
    return null
  }
}

/**
 * The theme the app should currently show. The <html> attribute wins once set
 * (it's what the user is actually looking at); otherwise fall back the same way
 * the inline script does — stored choice, then OS, then dark.
 */
export function getTheme(): Theme {
  try {
    const attr = document.documentElement.getAttribute('data-theme')
    if (isTheme(attr)) return attr
  } catch {
    /* no DOM — fall through */
  }
  return getStoredTheme() ?? getSystemTheme()
}

function emit(): void {
  for (const listener of listeners) listener()
}

/** Subscribe to theme changes. Returns an unsubscribe function. */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function applyAttribute(theme: Theme): void {
  try {
    document.documentElement.setAttribute('data-theme', theme)
  } catch {
    /* no DOM */
  }
}

/**
 * Set an explicit theme: persist it (so it survives reload and outlasts an OS
 * theme change) and apply it. This is the only path that writes localStorage.
 */
export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    /* storage unavailable — still apply, just don't persist */
  }
  applyAttribute(theme)
  emit()
}

/** Flip between light and dark, persisting the result. */
export function toggleTheme(): void {
  setTheme(getTheme() === 'dark' ? 'light' : 'dark')
}

/**
 * Apply the resolved theme to <html> without persisting, and keep it in sync
 * with two external sources: the OS preference (followed only while no explicit
 * choice is stored) and another tab of the same app changing the choice (a
 * `storage` event). Call once (ThemeProvider does, on mount). Returns cleanup.
 */
export function startThemeSync(): () => void {
  applyAttribute(getTheme())
  emit()

  // Another tab wrote billing.theme (or cleared it). Re-resolve from storage →
  // OS (not from `getTheme()`, which trusts the now-stale <html> attribute).
  const onStorage = (e: StorageEvent) => {
    if (e.key !== null && e.key !== THEME_STORAGE_KEY) return
    applyAttribute(getStoredTheme() ?? getSystemTheme())
    emit()
  }
  window.addEventListener('storage', onStorage)

  let mq: MediaQueryList
  try {
    mq = window.matchMedia('(prefers-color-scheme: light)')
  } catch {
    return () => window.removeEventListener('storage', onStorage)
  }

  const onSystemChange = () => {
    // An explicit choice always wins — once the user has picked, stop following.
    if (getStoredTheme() !== null) return
    applyAttribute(getSystemTheme())
    emit()
  }
  mq.addEventListener('change', onSystemChange)

  return () => {
    window.removeEventListener('storage', onStorage)
    mq.removeEventListener('change', onSystemChange)
  }
}
