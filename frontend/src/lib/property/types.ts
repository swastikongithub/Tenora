/**
 * Response shapes of the property-billing API (apps/properties/serializers.py).
 * Money is integer minor units + currency; readings, multipliers and rates are
 * decimal STRINGS exactly as the API sends them — never parsed into floats for
 * arithmetic. The UI renders stored values; it never recomputes a charge.
 */

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type BillStatus = 'DRAFT' | 'PUBLISHED' | 'PARTIALLY_PAID' | 'PAID' | 'CANCELLED'
export type DisplayStatus = BillStatus | 'OVERDUE'
export type AgingBucket = 'CURRENT' | '1_30' | '31_60' | '61_90' | '90_PLUS'

export interface Property {
  id: string
  name: string
  code: string
  address_line_1: string
  address_line_2: string
  city: string
  state: string
  postal_code: string
  country: string
  is_active: boolean
  unit_count: number | null
  occupied_count: number | null
  created_at: string
}

export interface Unit {
  id: string
  property_id: string
  property_name: string
  identifier: string
  floor: string
  unit_type: string
  status: 'VACANT' | 'OCCUPIED' | 'MAINTENANCE' | 'INACTIVE'
  created_at: string
}

export interface Lease {
  id: string
  unit_id: string
  unit_identifier: string
  property_id: string
  property_name: string
  resident_id: string
  resident_name: string
  start_date: string
  end_date: string | null
  monthly_rent_cents: number
  security_deposit_cents: number | null
  status: 'DRAFT' | 'ACTIVE' | 'ENDED' | 'CANCELLED'
  created_at: string
}

export interface Resident {
  id: string
  user_id: string
  email: string
  display_name: string
  phone: string
  reference: string
  status: 'ACTIVE' | 'INACTIVE'
  active_lease: Lease | null
  created_at: string
}

export interface Meter {
  id: string
  unit_id: string
  unit_identifier: string
  property_name: string
  meter_number: string
  utility_type: 'ELECTRICITY'
  unit_of_measure: string
  multiplier: string
  is_active: boolean
  installed_at: string | null
  latest_reading: { reading_date: string; reading_value: string } | null
  created_at: string
}

export interface MeterReading {
  id: string
  meter_id: string
  meter_number: string
  unit_identifier: string
  reading_date: string
  reading_value: string
  source: string
  notes: string
  has_proof: boolean
  proof_content_type: string
  corrections: Array<{
    id: string
    original_value: string
    corrected_value: string
    reason: string
    actor_email: string | null
    created_at: string
  }>
  created_at: string
}

export interface Tariff {
  id: string
  utility_type: string
  rate_per_unit_cents: string
  effective_from: string
  effective_to: string | null
  is_active: boolean
  created_at: string
}

export interface BillingCycle {
  id: string
  period_start: string
  period_end: string
  status: 'OPEN' | 'CLOSED'
  closed_at: string | null
  created_at: string
}

export interface CycleException {
  code: string
  message: string
  blocking: boolean
  lease_id: string
  unit_id: string
  unit_identifier: string
  property_name: string
  resident_name: string
}

export interface CycleProgress {
  expected_bills: number
  meters_expected: number
  readings_entered: number
  bills_generated: number
  bills_draft: number
  bills_published: number
  bills_paid: number
  billed_cents: number
  collected_cents: number
  exceptions: CycleException[]
}

export interface Bill {
  id: string
  bill_number: string
  status: BillStatus
  display_status: DisplayStatus
  period_start: string
  period_end: string
  due_date: string
  currency: string
  property_id: string
  property_name: string
  unit_id: string
  unit_identifier: string
  resident_id: string
  resident_name: string
  subtotal_cents: number
  adjustments_cents: number
  total_cents: number
  amount_paid_cents: number
  amount_due_cents: number
  overdue_days: number
  aging_bucket: AgingBucket | null
  rent_cents: number
  electricity_cents: number
  electricity_units: string
  other_cents: number
  published_at: string | null
  created_at: string
  tenant_id?: string
  tenant_name?: string
}

export interface LineItem {
  id: string
  type: 'RENT' | 'ELECTRICITY' | 'MAINTENANCE' | 'OTHER_CHARGE' | 'DISCOUNT' | 'ADJUSTMENT' | 'LATE_FEE'
  description: string
  quantity: string | null
  unit_price_cents: string | null
  rate_per_unit_cents: string | null
  amount_cents: number
  meter_number: string
  opening_reading_id: string | null
  closing_reading_id: string | null
  opening_reading_value: string | null
  closing_reading_value: string | null
  opening_reading_date: string | null
  closing_reading_date: string | null
  multiplier: string | null
  units_consumed: string | null
  opening_has_proof: boolean
  closing_has_proof: boolean
  correction_id: string | null
}

export interface Payment {
  id: string
  bill_id: string
  bill_number: string
  resident_name: string
  unit_identifier: string
  period_start: string
  amount_cents: number
  currency: string
  payment_date: string
  method: 'CASH' | 'BANK_TRANSFER' | 'UPI' | 'CARD' | 'ONLINE' | 'OTHER'
  status: 'COMPLETED' | 'VOIDED'
  reference: string
  notes: string
  voided_at: string | null
  void_reason: string
  receipt_id: string | null
  receipt_number: string | null
  created_at: string
  tenant_name?: string
}

export interface Receipt {
  id: string
  receipt_number: string
  issued_at: string
  amount_cents: number
  currency: string
  resident_name: string
  unit_identifier: string
  property_name: string
  bill_id: string
  bill_number: string
  payment_id: string
  payment_method: string
  payment_status: 'COMPLETED' | 'VOIDED'
  payment_date: string
  payment_reference: string
  period_start: string
  tenant_name?: string
  issuer?: {
    name: string
    contact_email: string
    contact_phone: string
    address: string
    footer: string
  }
}

export interface BillCorrection {
  id: string
  kind: 'AMOUNT_ADJUSTMENT' | 'READING_CORRECTION'
  reason: string
  original_values: Record<string, unknown>
  corrected_values: Record<string, unknown>
  amount_delta_cents: number
  actor_email: string | null
  created_at: string
}

export interface BillDetail extends Bill {
  cycle_id: string
  lease_id: string | null
  resident_email: string
  cancelled_at: string | null
  cancellation_reason: string
  line_items: LineItem[]
  payments: Payment[]
  receipts: Receipt[]
  corrections: BillCorrection[]
}

export interface PeriodSummary {
  period: string
  billed_cents: number
  collected_cents: number
  outstanding_cents: number
  overdue_cents: number
  residents: number | null
  bills_issued: number
  bills_draft: number
  bills_paid: number
  bills_unpaid: number
  electricity_units: string
}

export interface AgingRow {
  bill_id: string
  bill_number: string
  resident_id: string
  resident_name: string
  unit_identifier: string
  property_name: string
  period_start: string
  due_date: string
  amount_due_cents: number
  currency: string
  overdue_days: number
  bucket: AgingBucket
  status: BillStatus
}

export interface AgingReport {
  total_outstanding_cents: number
  total_overdue_cents: number
  buckets: Array<{ key: AgingBucket; label: string; amount_cents: number; count: number }>
  rows: AgingRow[]
}

/** One month of GET /api/billing/reports/ (and the platform summary's `monthly`). */
export interface MonthlyReportRow {
  period: string
  billed_cents: number
  collected_cents: number
  outstanding_cents: number
  rent_billed_cents: number
  electricity_billed_cents: number
  other_billed_cents: number
  /** Collected by type counts PAID bills only; part-payments are `collected_unallocated_cents`. */
  rent_collected_cents: number
  electricity_collected_cents: number
  other_collected_cents: number
  collected_unallocated_cents: number
  electricity_units: string
  cash_received_cents: number
}

export interface ElectricityUnitRow {
  tenant_id: string
  tenant_name?: string
  property_name: string
  unit_identifier: string
  units: string
  amount_cents: number
}

export type AgingBucketTotal = { key: AgingBucket; label: string; amount_cents: number; count: number }

/** GET /api/account/billing-portfolio/ — one row per workspace the owner controls. */
export interface PortfolioWorkspace {
  id: string
  name: string
  slug: string
  is_active: boolean
  currency: string
  billed_cents: number
  collected_cents: number
  outstanding_cents: number
  overdue_cents: number
  bills_issued: number
  bills_draft: number
  bills_paid: number
  bills_unpaid: number
  total_outstanding_cents: number
  total_overdue_cents: number
  buckets: AgingBucketTotal[]
}

/** Totals are per currency — amounts in different currencies are never added. */
export interface PortfolioTotal {
  currency: string
  workspaces: number
  billed_cents: number
  collected_cents: number
  outstanding_cents: number
  overdue_cents: number
  total_outstanding_cents: number
  total_overdue_cents: number
  buckets: AgingBucketTotal[]
}

export interface BillingPortfolio {
  period: string
  workspaces: PortfolioWorkspace[]
  totals: PortfolioTotal[]
}

export interface OnboardingStep {
  key: string
  label: string
  done: boolean
}

export interface WorkspaceOverview {
  properties: number
  units: number
  occupied_units: number
  residents: number
  current_month: PeriodSummary
  overdue_bills: number
  open_cycle: BillingCycle | null
  onboarding: {
    steps: OnboardingStep[]
    completed: number
    total: number
    percent: number
    ready_to_bill: boolean
  }
}

export interface WorkspaceSettings {
  display_name: string
  contact_email: string
  contact_phone: string
  address: string
  receipt_footer: string
  currency: string
  due_days_after_period_end: number
  default_maintenance_cents: number
  updated_at: string
}

export interface Invitation {
  id: string
  tenant_id: string
  tenant_name: string
  email: string
  role: 'OWNER' | 'MEMBER'
  status: 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'CANCELLED' | 'EXPIRED'
  unit_id: string | null
  unit_identifier: string | null
  property_name: string | null
  message: string
  invited_by_email: string | null
  created_at: string
  expires_at: string
  responded_at: string | null
}

export interface AppNotification {
  id: string
  kind: string
  title: string
  body: string
  data: Record<string, string | number>
  tenant_id: string | null
  tenant_name: string | null
  read_at: string | null
  created_at: string
}

export interface WorkspaceUsage {
  plan_code: string | null
  plan_name: string | null
  members: { active: number; pending_invitations: number; used: number; limit: number }
}

export interface AccountUsage {
  plan_code: string | null
  plan_name: string | null
  workspaces: { used: number; limit: number }
  owned_workspaces: Array<WorkspaceUsage & { id: string; name: string }>
}

export interface AccountProfile {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string
  has_usable_password: boolean
  date_joined: string
  deletion_blockers: Array<{ id: string; name: string }>
}

export interface Residency {
  resident: Resident | null
  lease: Lease | null
  latest_bill?: Bill | null
  outstanding_cents?: number
  overdue_bills?: number
}
