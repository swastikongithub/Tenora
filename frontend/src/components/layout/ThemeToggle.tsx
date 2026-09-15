/**
 * The account menu's theme toggle — the shared Eclipse ThemeToggle
 * (components/ThemeToggle.tsx) in its labelled row form. Kept at this path so
 * the account menu and its tests import it exactly as before; there is no
 * second implementation.
 */

import { ThemeToggle as SharedThemeToggle } from '../ThemeToggle'

export function ThemeToggle() {
  return <SharedThemeToggle label />
}
