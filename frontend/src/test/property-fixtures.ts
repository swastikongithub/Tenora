/**
 * Property-billing fixtures and MSW handlers. Shapes mirror
 * apps/properties/serializers.py exactly (money as integer minor units,
 * decimals as strings).
 */

import { http, HttpResponse } from 'msw'

import type {
  AgingReport,
  AppNotification,
  Bill,
  BillDetail,
  Invitation,
  Paginated,
  Residency,
  WorkspaceOverview,
  WorkspaceUsage,
} from '../lib/property/types'
import { apiUrl } from './fixtures'

export const page = <T,>(results: T[]): Paginated<T> => ({ count: results.length, next: null, previous: null, results })

export const BILL: Bill = {
  id: 'bill-1',
  bill_number: 'BILL-2026-000001',
  status: 'PUBLISHED',
  display_status: 'OVERDUE',
  period_start: '2026-03-01',
  period_end: '2026-03-31',
  due_date: '2026-04-10',
  currency: 'INR',
  property_id: 'prop-1',
  property_name: 'Sunrise Building A',
  unit_id: 'unit-203',
  unit_identifier: '203',
  resident_id: 'res-1',
  resident_name: 'Rahul Sharma',
  subtotal_cents: 1378000,
  adjustments_cents: 0,
  total_cents: 1378000,
  amount_paid_cents: 0,
  amount_due_cents: 1378000,
  overdue_days: 12,
  aging_bucket: '1_30',
  rent_cents: 1200000,
  electricity_cents: 128000,
  electricity_units: '160.000',
  other_cents: 50000,
  published_at: '2026-04-01T09:00:00Z',
  created_at: '2026-04-01T08:00:00Z',
}

export const BILL_DETAIL: BillDetail = {
  ...BILL,
  cycle_id: 'cycle-1',
  lease_id: 'lease-1',
  resident_email: 'rahul@example.com',
  cancelled_at: null,
  cancellation_reason: '',
  line_items: [
    {
      id: 'line-rent', type: 'RENT', description: 'Rent — March 2026', quantity: '1.000', unit_price_cents: '1200000.0000',
      rate_per_unit_cents: '1200000.0000', amount_cents: 1200000, meter_number: '', opening_reading_id: null, closing_reading_id: null,
      opening_reading_value: null, closing_reading_value: null, opening_reading_date: null, closing_reading_date: null,
      multiplier: null, units_consumed: null, opening_has_proof: false, closing_has_proof: false, correction_id: null,
    },
    {
      id: 'line-elec', type: 'ELECTRICITY', description: 'Electricity — March 2026 (meter ELEC-203)', quantity: '160.000',
      unit_price_cents: '800.0000', rate_per_unit_cents: '800.0000', amount_cents: 128000, meter_number: 'ELEC-203',
      opening_reading_id: 'reading-open', closing_reading_id: 'reading-close', opening_reading_value: '12450.000',
      closing_reading_value: '12610.000', opening_reading_date: '2026-02-28', closing_reading_date: '2026-03-31',
      multiplier: '1.0000', units_consumed: '160.000', opening_has_proof: false, closing_has_proof: true, correction_id: null,
    },
    {
      id: 'line-maint', type: 'MAINTENANCE', description: 'Maintenance — March 2026', quantity: '1.000', unit_price_cents: '50000.0000',
      rate_per_unit_cents: '50000.0000', amount_cents: 50000, meter_number: '', opening_reading_id: null, closing_reading_id: null,
      opening_reading_value: null, closing_reading_value: null, opening_reading_date: null, closing_reading_date: null,
      multiplier: null, units_consumed: null, opening_has_proof: false, closing_has_proof: false, correction_id: null,
    },
  ],
  payments: [],
  receipts: [],
  corrections: [],
}

export const AGING: AgingReport = {
  total_outstanding_cents: 4348000,
  total_overdue_cents: 4348000,
  buckets: [
    { key: 'CURRENT', label: 'Current', amount_cents: 0, count: 0 },
    { key: '1_30', label: '1–30 days', amount_cents: 1378000, count: 1 },
    { key: '31_60', label: '31–60 days', amount_cents: 1820000, count: 1 },
    { key: '61_90', label: '61–90 days', amount_cents: 1150000, count: 1 },
    { key: '90_PLUS', label: '90+ days', amount_cents: 0, count: 0 },
  ],
  rows: [
    { bill_id: 'b3', bill_number: 'BILL-3', resident_id: 'r3', resident_name: 'Priya', unit_identifier: '301', property_name: 'A', period_start: '2026-01-01', due_date: '2026-02-10', amount_due_cents: 1150000, currency: 'INR', overdue_days: 74, bucket: '61_90', status: 'PUBLISHED' },
    { bill_id: 'b2', bill_number: 'BILL-2', resident_id: 'r2', resident_name: 'Aman', unit_identifier: '104', property_name: 'A', period_start: '2026-02-01', due_date: '2026-03-10', amount_due_cents: 1820000, currency: 'INR', overdue_days: 37, bucket: '31_60', status: 'PUBLISHED' },
    { bill_id: 'b1', bill_number: 'BILL-1', resident_id: 'r1', resident_name: 'Rahul', unit_identifier: '203', property_name: 'A', period_start: '2026-03-01', due_date: '2026-04-10', amount_due_cents: 1378000, currency: 'INR', overdue_days: 12, bucket: '1_30', status: 'PUBLISHED' },
  ],
}

export const OVERVIEW: WorkspaceOverview = {
  properties: 1,
  units: 4,
  occupied_units: 2,
  residents: 2,
  current_month: {
    period: '2026-03', billed_cents: 1378000, collected_cents: 0, outstanding_cents: 1378000, overdue_cents: 1378000,
    residents: 2, bills_issued: 1, bills_draft: 0, bills_paid: 0, bills_unpaid: 1, electricity_units: '160.000',
  },
  overdue_bills: 1,
  open_cycle: null,
  onboarding: {
    steps: [
      { key: 'workspace', label: 'Create workspace', done: true },
      { key: 'property', label: 'Create a property', done: true },
      { key: 'units', label: 'Add units', done: true },
      { key: 'residents', label: 'Invite residents', done: true },
      { key: 'tariff', label: 'Configure electricity rate', done: false },
      { key: 'leases', label: 'Assign leases', done: false },
    ],
    completed: 4,
    total: 6,
    percent: 67,
    ready_to_bill: false,
  },
}

export const INVITATION: Invitation = {
  id: 'inv-1',
  tenant_id: 'tenant-c',
  tenant_name: 'Sunrise Apartments',
  email: 'me@example.com',
  role: 'MEMBER',
  status: 'PENDING',
  unit_id: 'unit-203',
  unit_identifier: '203',
  property_name: 'Sunrise Building A',
  message: 'Welcome!',
  invited_by_email: 'owner@sunrise.test',
  created_at: '2026-03-01T00:00:00Z',
  expires_at: '2026-03-15T00:00:00Z',
  responded_at: null,
}

export const NOTIFICATION: AppNotification = {
  id: 'n-1',
  kind: 'BILL_PUBLISHED',
  title: 'Your March 2026 bill is ready',
  body: 'Unit 203 · due 10 Apr 2026.',
  data: { bill_id: 'bill-1' },
  tenant_id: 'tenant-b',
  tenant_name: 'Beta LLC',
  read_at: null,
  created_at: '2026-04-01T09:00:00Z',
}

export const USAGE_AT_LIMIT: WorkspaceUsage = {
  plan_code: 'BASIC',
  plan_name: 'Basic',
  members: { active: 9, pending_invitations: 1, used: 10, limit: 10 },
}

export const RESIDENCY: Residency = {
  resident: {
    id: 'res-1', user_id: 'u-1', email: 'rahul@example.com', display_name: 'Rahul Sharma', phone: '', reference: '',
    status: 'ACTIVE', active_lease: null, created_at: '2026-01-01T00:00:00Z',
  },
  lease: {
    id: 'lease-1', unit_id: 'unit-203', unit_identifier: '203', property_id: 'prop-1', property_name: 'Sunrise Building A',
    resident_id: 'res-1', resident_name: 'Rahul Sharma', start_date: '2026-01-01', end_date: null,
    monthly_rent_cents: 1200000, security_deposit_cents: null, status: 'ACTIVE', created_at: '2026-01-01T00:00:00Z',
  },
  latest_bill: BILL,
  outstanding_cents: 1378000,
  overdue_bills: 1,
}

export const json = (path: string, body: unknown, status = 200) =>
  http.get(apiUrl(path), () => HttpResponse.json(body as object, { status }))

/** Quiet defaults for the chrome every authenticated page mounts (bell, settings). */
export const shellHandlers = () => [
  json('/notifications/unread-count/', { unread: 0 }),
  json('/workspace/settings/', {
    display_name: 'Alpha', contact_email: '', contact_phone: '', address: '', receipt_footer: '', currency: 'INR',
    due_days_after_period_end: 10, default_maintenance_cents: 50000, updated_at: '2026-01-01T00:00:00Z',
  }),
]
