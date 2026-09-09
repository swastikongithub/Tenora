/**
 * The theme context and its hook — kept separate from ThemeProvider.tsx so each
 * file exports one kind of thing (the `react-refresh/only-export-components`
 * rule), matching the auth-context.ts / AuthProvider.tsx split.
 */

import { createContext, useContext, useSyncExternalStore } from 'react'

import {
  getTheme,
  setTheme,
  subscribe,
  toggleTheme,
  type Theme,
} from './theme-store'

export interface ThemeContextValue {
  theme: Theme
  /** Set an explicit theme. Persists the choice and overrides the OS setting. */
  setTheme: (theme: Theme) => void
  /** Flip between light and dark, persisting the result. */
  toggleTheme: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

/**
 * Current theme + setters. Works with or without a `<ThemeProvider>` above it:
 * with one, reads the context; without one, subscribes to the module store
 * directly (still reactive, still correct) so a provider-less unit test render
 * doesn't crash. Both paths observe the same store.
 */
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  const storeTheme = useSyncExternalStore(subscribe, getTheme, getTheme)
  return ctx ?? { theme: storeTheme, setTheme, toggleTheme }
}
