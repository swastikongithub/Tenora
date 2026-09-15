/**
 * Sample records shown on the public landing page.
 *
 * Provenance: fictional data from the property billing plan's worked example
 * (docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md §39 — Sunrise Apartments, unit
 * 203, a ₹12,000 rent, meter 12,450 → 12,610, ₹8/unit, ₹500 maintenance). Every
 * figure is typed against the real product types in lib/property/types, so if
 * the product's shapes change, this file stops compiling instead of drifting.
 * The page labels it "Sample data"; none of it describes a real customer.
 *
 * The arithmetic is derived here (units × rate, line sums) rather than typed in
 * twice, and the landing tests assert it.
 */

import type { AgingBucket, BillStatus, LineItem, Receipt } from '../lib/property/types'

export const SAMPLE_CURRENCY = 'INR'

export const OPENING_READING = 12450
export const CLOSING_READING = 12610
export const MULTIPLIER = 1
export const RATE_PER_UNIT_CENTS = 800
export const UNITS = (CLOSING_READING - OPENING_READING) * MULTIPLIER // 160
export const ELECTRICITY_CENTS = UNITS * RATE_PER_UNIT_CENTS // ₹1,280
export const RENT_CENTS = 1_200_000
export const MAINTENANCE_CENTS = 50_000

type SampleLine = Pick<LineItem, 'id' | 'type' | 'description' | 'amount_cents'> & {
  /** What the line is traced back to — shown when the line is focused. */
  source: string[]
}

export const SAMPLE_LINES: SampleLine[] = [
  {
    id: 'rent',
    type: 'RENT',
    description: 'Rent',
    amount_cents: RENT_CENTS,
    source: ['Lease for Unit 203', '₹12,000 a month since 1 Jan 2026'],
  },
  {
    id: 'electricity',
    type: 'ELECTRICITY',
    description: 'Electricity',
    amount_cents: ELECTRICITY_CENTS,
    source: [
      'Opening 12,450 · 28 Feb · photo proof attached',
      'Closing 12,610 · 31 Mar · photo proof attached',
      '160 units × ₹8.00 — tariff effective 1 Jan',
    ],
  },
  {
    id: 'maintenance',
    type: 'MAINTENANCE',
    description: 'Maintenance',
    amount_cents: MAINTENANCE_CENTS,
    source: ['Workspace default charge', 'Applied to every bill this cycle'],
  },
]

export const SAMPLE_TOTAL_CENTS = SAMPLE_LINES.reduce((sum, line) => sum + line.amount_cents, 0) // ₹13,780

export const SAMPLE_BILL = {
  bill_number: 'BILL-2026-000001',
  status: 'PUBLISHED' as BillStatus,
  property_name: 'Sunrise Apartments',
  unit_identifier: '203',
  resident_name: 'Rahul Sharma',
  period_start: '2026-03-01',
  due_date: '2026-04-10',
  total_cents: SAMPLE_TOTAL_CENTS,
}

export const PARTIAL_PAYMENT_CENTS = 378_000

export const SAMPLE_RECEIPT: Pick<
  Receipt,
  'receipt_number' | 'amount_cents' | 'currency' | 'payment_method' | 'payment_date' | 'bill_number'
> = {
  receipt_number: 'REC-2026-000001',
  amount_cents: PARTIAL_PAYMENT_CENTS,
  currency: SAMPLE_CURRENCY,
  payment_method: 'UPI',
  payment_date: '2026-04-05',
  bill_number: SAMPLE_BILL.bill_number,
}

export const SAMPLE_UNITS = [
  { identifier: '201', status: 'Occupied', resident: 'Ananya Iyer', rent_cents: 1_150_000 },
  { identifier: '202', status: 'Vacant', resident: '—', rent_cents: 0 },
  { identifier: '203', status: 'Occupied', resident: 'Rahul Sharma', rent_cents: RENT_CENTS },
  { identifier: '204', status: 'Occupied', resident: 'Farah Khan', rent_cents: 1_250_000 },
]

export const SAMPLE_AGING: Array<{ key: AgingBucket; label: string; amount_cents: number; count: number }> = [
  { key: 'CURRENT', label: 'Current', amount_cents: 2_644_000, count: 2 },
  { key: '1_30', label: '1–30 days', amount_cents: 1_000_000, count: 1 },
  { key: '31_60', label: '31–60 days', amount_cents: 1_322_000, count: 1 },
  { key: '61_90', label: '61–90 days', amount_cents: 0, count: 0 },
  { key: '90_PLUS', label: '90+ days', amount_cents: 480_000, count: 1 },
]

/** Workflow stops for the ledger rail — the order records are created in. */
export const WORKFLOW = [
  { key: 'workspace', label: 'Workspace', detail: 'Sunrise Apartments' },
  { key: 'properties', label: 'Properties', detail: 'Building A · 4 units' },
  { key: 'units', label: 'Units', detail: 'Unit 203 · Occupied' },
  { key: 'residents', label: 'Residents', detail: 'Rahul Sharma · accepted invite' },
  { key: 'leases', label: 'Leases', detail: '₹12,000 / month' },
  { key: 'readings', label: 'Meter readings', detail: '12,450 → 12,610' },
  { key: 'bills', label: 'Bills', detail: 'BILL-2026-000001 · ₹13,780' },
  { key: 'payments', label: 'Payments', detail: 'UPI · ₹3,780' },
  { key: 'receipts', label: 'Receipts', detail: 'REC-2026-000001' },
  { key: 'aging', label: 'Aging', detail: '₹10,000 due · 1–30 days' },
] as const

/** The implemented plan limits (apps.billing Plan.max_workspaces /
 *  max_members_per_workspace, set by migrations 0013/0014). Prices are not
 *  shown: GET /api/plans/ requires sign-in, and the landing page never invents
 *  them (landing plan decision H-D1). Update here if the plan rows change. */
export const PLAN_LIMITS = [
  { name: 'Basic', workspaces: 2, members: 10 },
  { name: 'Pro', workspaces: 20, members: 20 },
] as const
