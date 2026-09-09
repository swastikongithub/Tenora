/**
 * The React seam for theming (Stage C3b §4.1). Thin by design: the actual state
 * lives in theme-store.ts and on the <html data-theme> attribute. This provider
 * (1) starts the store's lifecycle — apply the resolved theme, follow the OS
 * setting until the user chooses — and (2) hands the current value + setters to
 * the tree via context.
 *
 * First paint is already handled by the inline script in index.html, so mounting
 * this provider never causes a flash.
 */

import { useSyncExternalStore, useEffect, type ReactNode } from 'react'

import { ThemeContext, type ThemeContextValue } from './theme-context'
import {
  getTheme,
  setTheme,
  startThemeSync,
  subscribe,
  toggleTheme,
} from './theme-store'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribe, getTheme, getTheme)

  useEffect(() => startThemeSync(), [])

  const value: ThemeContextValue = { theme, setTheme, toggleTheme }

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
