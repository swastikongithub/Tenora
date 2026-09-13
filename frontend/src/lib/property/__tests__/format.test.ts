import { describe, expect, it } from 'vitest'

import { formatDay, formatDecimal, formatPeriod, toMinorRate, toMinorUnits } from '../format'

describe('property format helpers', () => {
  it('converts typed major units to integer minor units without floats', () => {
    expect(toMinorUnits('12000')).toBe(1200000)
    expect(toMinorUnits('12,000.5')).toBe(1200050)
    expect(toMinorUnits('0.07')).toBe(7)
    expect(toMinorUnits('-80')).toBe(-8000)
    expect(toMinorUnits('1.234')).toBeNull()
    expect(toMinorUnits('abc')).toBeNull()
  })

  it('converts a major-unit rate to a minor-unit decimal string', () => {
    expect(toMinorRate('8')).toBe('800.0000')
    expect(toMinorRate('8.25')).toBe('825.0000')
    expect(toMinorRate('0.123456')).toBe('12.3456')
    expect(toMinorRate('-1')).toBeNull()
  })

  it('formats decimal strings for display only', () => {
    expect(formatDecimal('12450.000')).toBe('12,450')
    expect(formatDecimal('150.500')).toBe('150.5')
    expect(formatDecimal(null)).toBe('—')
  })

  it('formats periods and days without timezone drift', () => {
    expect(formatPeriod('2026-03-01')).toBe('March 2026')
    expect(formatDay('2026-04-10')).toBe('10 Apr 2026')
    expect(formatDay('2026-04-01T23:30:00Z')).toBe('1 Apr 2026')
  })
})
