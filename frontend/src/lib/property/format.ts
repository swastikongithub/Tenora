/**
 * Property-billing display helpers. Decimal values stay strings: trimming
 * trailing zeros is presentation, not arithmetic.
 */

import { formatMoney } from '../format'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

/** '2026-03-01' -> 'March 2026' (no Date parsing, so no timezone drift). */
export function formatPeriod(isoDate: string | null | undefined): string {
  if (!isoDate) return '—'
  const [year, month] = isoDate.split('-')
  const name = MONTHS[Number(month) - 1]
  return name && year ? `${name} ${year}` : '—'
}

/** '2026-04-10' -> '10 Apr 2026' without timezone conversion. */
export function formatDay(isoDate: string | null | undefined): string {
  if (!isoDate) return '—'
  const [year, month, day] = isoDate.slice(0, 10).split('-')
  const name = MONTHS[Number(month) - 1]
  return name && year && day ? `${Number(day)} ${name.slice(0, 3)} ${year}` : '—'
}

/** '12450.000' -> '12,450'; '150.500' -> '150.5'. Display only. */
export function formatDecimal(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const negative = value.startsWith('-')
  const [whole, fraction = ''] = value.replace('-', '').split('.')
  const trimmed = fraction.replace(/0+$/, '')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}${trimmed ? `.${trimmed}` : ''}`
}

/** A rate stored in minor units per unit ('825.0000') shown as currency per unit. */
export function formatRate(rateMinor: string | null | undefined, currency: string, unit = 'unit'): string {
  if (!rateMinor) return '—'
  const [whole, fraction = ''] = rateMinor.split('.')
  const padded = whole.padStart(3, '0')
  const majorDigits = `${padded.slice(0, -2)}.${padded.slice(-2)}${fraction}`.replace(/0+$/, '')
  const decimals = Math.max(2, (majorDigits.split('.')[1] ?? '').length)
  try {
    const text = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(Number(majorDigits))
    return `${text}/${unit}`
  } catch {
    return `${majorDigits} ${currency}/${unit}`
  }
}

export function money(cents: number | null | undefined, currency = 'INR'): string {
  return formatMoney(cents ?? 0, currency)
}

/** Current month as 'YYYY-MM' from the browser — a DEFAULT for a filter only,
 *  never an authoritative date (overdue days always come from the server). */
export function currentPeriodParam(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

/** Convert a major-unit string the user typed ('12000.50') to integer minor units. */
export function toMinorUnits(input: string): number | null {
  const text = input.trim().replace(/,/g, '')
  if (!/^-?\d+(\.\d{0,2})?$/.test(text)) return null
  const negative = text.startsWith('-')
  const [whole, fraction = ''] = text.replace('-', '').split('.')
  const value = Number(whole) * 100 + Number((fraction + '00').slice(0, 2))
  return negative ? -value : value
}

/** Convert a major-unit rate ('8.25') to a minor-unit decimal string ('825.0000'). */
export function toMinorRate(input: string): string | null {
  const text = input.trim()
  if (!/^\d+(\.\d{0,6})?$/.test(text)) return null
  const [whole, fraction = ''] = text.split('.')
  const padded = (fraction + '000000').slice(0, 6)
  const minorWhole = Number(whole) * 100 + Number(padded.slice(0, 2))
  return `${minorWhole}.${padded.slice(2, 6)}`
}

export const STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Draft',
  PUBLISHED: 'Unpaid',
  PARTIALLY_PAID: 'Partially paid',
  PAID: 'Paid',
  CANCELLED: 'Cancelled',
  OVERDUE: 'Overdue',
}

export const METHOD_LABEL: Record<string, string> = {
  CASH: 'Cash',
  BANK_TRANSFER: 'Bank transfer',
  UPI: 'UPI',
  CARD: 'Card',
  ONLINE: 'Online',
  OTHER: 'Other',
}
