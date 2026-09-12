/**
 * Builds a `?key=value&...` query string from a params object, dropping any
 * empty/undefined value — the shared helper every /admin list page uses to
 * call its GET endpoint with the current filters/page. Phase 1 is read-only:
 * nothing here builds anything but a GET query string.
 */
export function toSearchParams(
  params: Record<string, string | number | undefined>,
): string {
  const usp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') usp.set(key, String(value))
  }
  const s = usp.toString()
  return s ? `?${s}` : ''
}
