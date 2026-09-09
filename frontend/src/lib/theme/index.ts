// Public surface of the theme layer. Import from '../theme', not individual files.

export { ThemeProvider } from './ThemeProvider'
export { useTheme } from './theme-context'
export type { ThemeContextValue } from './theme-context'
export {
  getTheme,
  getSystemTheme,
  getStoredTheme,
  setTheme,
  toggleTheme,
  THEME_STORAGE_KEY,
  type Theme,
} from './theme-store'
