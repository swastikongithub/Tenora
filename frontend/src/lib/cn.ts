/**
 * Minimal className joiner — no dependency. Falsy entries are dropped so callers
 * can write `cn('base', condition && 'variant', props.className)`.
 *
 * This is a plain concatenator, not a Tailwind-aware merge: if two conflicting
 * utilities are passed, the later one wins only by CSS source order. Components
 * here are structured so that does not happen (variants are mutually exclusive).
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
