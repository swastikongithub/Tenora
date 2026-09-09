import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { formatDate, formatMoney, formatRelativeDate } from '../format'

describe('formatMoney', () => {
  it('renders integer cents as a two-decimal currency amount', () => {
    // Not asserting the exact symbol/placement — that is the host locale's
    // business. Asserting the digits is what matters: 2900 cents is 29.00, not
    // 2900 and not 290.
    expect(formatMoney(2900, 'USD')).toContain('29.00')
    expect(formatMoney(9900, 'USD')).toContain('99.00')
  })

  it('keeps cents that are not a round number of units', () => {
    expect(formatMoney(1999, 'USD')).toContain('19.99')
    expect(formatMoney(1, 'USD')).toContain('0.01')
  })

  it('renders a zero price without falling back to an em dash', () => {
    expect(formatMoney(0, 'USD')).toContain('0.00')
  })

  it('never emits a bare hardcoded dollar sign for a non-USD currency', () => {
    // CLAUDE.md forbids a hardcoded `$`. EUR must not render as "$29.00".
    const eur = formatMoney(2900, 'EUR')
    expect(eur).toContain('29.00')
    expect(eur).not.toBe('$29.00')
  })

  it('uses the currency’s real minor-unit exponent, not a hardcoded 100', () => {
    // JPY has zero minor units: 1000 JPY is ¥1,000, not ¥10.00. A blind
    // divide-by-100 would render this as 10.
    const jpy = formatMoney(1000, 'JPY')
    expect(jpy).toContain('1,000')
    expect(jpy).not.toContain('10.00')
  })

  it('falls back to a readable string for an unknown currency code', () => {
    // Intl throws RangeError on a bad code; a billing page should degrade, not
    // blank out.
    expect(formatMoney(2900, 'NOT_A_CURRENCY')).toBe('29.00 NOT_A_CURRENCY')
  })

  it('returns an em dash for a non-finite amount', () => {
    expect(formatMoney(Number.NaN, 'USD')).toBe('—')
  })
})

describe('formatDate', () => {
  it('formats a valid ISO timestamp', () => {
    const out = formatDate('2026-03-14T00:00:00Z')
    expect(out).toMatch(/2026/)
    expect(out).not.toBe('—')
  })

  it('returns an em dash for an unparseable value', () => {
    expect(formatDate('not-a-date')).toBe('—')
  })
})

describe('formatRelativeDate', () => {
  // Pinned "now" so day-diff math can't drift with the real clock.
  const NOW = new Date('2026-03-14T12:00:00')

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reports "today" for the current calendar day', () => {
    expect(formatRelativeDate('2026-03-14T00:00:00')).toBe('today')
  })

  it('reports "tomorrow" and "yesterday" for adjacent days', () => {
    expect(formatRelativeDate('2026-03-15T00:00:00')).toBe('tomorrow')
    expect(formatRelativeDate('2026-03-13T00:00:00')).toBe('yesterday')
  })

  it('reports a day count within the same month', () => {
    expect(formatRelativeDate('2026-03-26T00:00:00')).toBe('in 12 days')
  })

  it('reports a past day count', () => {
    expect(formatRelativeDate('2026-02-18T00:00:00')).toBe('24 days ago')
  })

  it('steps up to months once the gap is large enough', () => {
    expect(formatRelativeDate('2026-05-13T00:00:00')).toBe('in 2 months')
  })

  it('steps up to years for a gap over a year', () => {
    expect(formatRelativeDate('2027-04-10T00:00:00')).toBe('next year')
  })

  it('is not fooled by an evening render into under-reporting "tomorrow"', () => {
    // "now" is pinned to noon above; a render at 11pm the same day must still
    // treat midnight-to-midnight as the day boundary, not raw millisecond math.
    vi.setSystemTime(new Date('2026-03-14T23:00:00'))
    expect(formatRelativeDate('2026-03-15T00:00:00')).toBe('tomorrow')
  })

  it('returns an em dash for an unparseable value', () => {
    expect(formatRelativeDate('not-a-date')).toBe('—')
  })
})
