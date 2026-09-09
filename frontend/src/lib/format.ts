/**
 * Display formatters for money and dates.
 *
 * Money is the reason this module exists. CLAUDE.md: "Money is `price_cents`
 * (integer) + `currency`. Never floats. Never a hardcoded `$`." The integer
 * cents stay integer everywhere except the single division that hands a value
 * to `Intl.NumberFormat`, and the currency symbol/placement comes from the
 * formatter, never from a literal in a template string.
 *
 * `formatDate` is lifted from the local helper `MembersPage` has had since C4 —
 * same behaviour, including the em-dash fallback. It lives here rather than
 * page-local because C5 and C6 both render dates and prices.
 *
 * `formatRelativeDate` was added in C6 (a scoped exception to that stage's
 * spec, which had said no change to this file — see stage-c6-spec.md §4.1a):
 * the Overview dashboard renders a renewal date as both an absolute date and a
 * relative phrase ("in 12 days"), and a second hand-rolled day-math helper
 * next to `formatDate` would be the kind of duplication CLAUDE.md's "three
 * similar lines is better than a premature abstraction" doesn't apply to —
 * this is the same concept, not a coincidentally similar one.
 */

/**
 * Format integer minor units (cents) as a currency string.
 *
 * The minor-unit exponent comes from the resolved format, not a hardcoded 100:
 * JPY has zero minor units, so `1000` JPY is ¥1,000 while `1000` USD is $10.00.
 * Dividing blindly by 100 would be wrong for every zero- or three-decimal
 * currency. Every seeded plan is USD today, but the `Plan.currency` column is
 * free-form, so the correct arithmetic costs nothing to do now.
 *
 * An unknown/malformed currency code makes `Intl.NumberFormat` throw a
 * RangeError; rather than blanking a billing page over bad reference data, fall
 * back to a plain "<amount> <CODE>" rendering.
 */
export function formatMoney(cents: number, currency: string): string {
  if (!Number.isFinite(cents)) return '—'

  try {
    const formatter = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
    })
    const exponent = formatter.resolvedOptions().maximumFractionDigits ?? 2
    return formatter.format(cents / 10 ** exponent)
  } catch {
    return `${(cents / 100).toFixed(2)} ${currency}`
  }
}

/** Format an ISO timestamp as a short human date, or an em dash if unparseable. */
export function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
}

const DAY_MS = 24 * 60 * 60 * 1000
const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 365],
  ['month', 30],
  ['day', 1],
]

/**
 * Format an ISO timestamp as a relative phrase — "in 12 days", "today",
 * "24 days ago" — or an em dash if unparseable, matching `formatDate`.
 *
 * The day difference is computed from local calendar midnights, not raw
 * millisecond subtraction, so a render at 11pm doesn't report "in 0 days" for
 * a target that is really tomorrow. `Intl.RelativeTimeFormat` with
 * `numeric: 'auto'` supplies "today"/"tomorrow"/"yesterday" for free once the
 * unit is "day" and the count is -1, 0, or 1.
 */
export function formatRelativeDate(iso: string): string {
  const target = new Date(iso)
  if (Number.isNaN(target.getTime())) return '—'

  const now = new Date()
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const dayDiff = Math.round(
    (startOf(target).getTime() - startOf(now).getTime()) / DAY_MS,
  )

  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(dayDiff) >= size || unit === 'day') {
      const value = unit === 'day' ? dayDiff : Math.round(dayDiff / size)
      return formatter.format(value, unit)
    }
  }
  return formatter.format(dayDiff, 'day')
}
