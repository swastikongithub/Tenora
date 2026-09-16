/**
 * Which plan change the UI should offer — a MIRROR of the backend's
 * `PlanChangePolicy`, never the enforcement itself. The server refuses an
 * illegal change whatever this file says; this exists so a customer sees why a
 * card is unavailable instead of clicking it and collecting an error.
 *
 * Tier comes from the plan code's prefix (`BASIC_MONTHLY` -> BASIC), exactly as
 * the backend reads it, and an unrecognised prefix is treated as unavailable
 * rather than guessed — the same fail-closed direction.
 */

const TIER_ORDER: Record<string, number> = { BASIC: 1, PRO: 2 }

export type PlanChangeKind = 'current' | 'upgrade' | 'blocked'

export interface PlanChangeVerdict {
  kind: PlanChangeKind
  /** Shown on the card. Empty for the plan already subscribed to. */
  note: string
}

function tierOf(code: string): string {
  return String(code).split('_')[0].toUpperCase()
}

export function classifyPlanChange(
  currentCode: string,
  targetCode: string,
): PlanChangeVerdict {
  if (currentCode === targetCode) {
    return { kind: 'current', note: '' }
  }

  const current = TIER_ORDER[tierOf(currentCode)]
  const target = TIER_ORDER[tierOf(targetCode)]
  if (!current || !target) {
    return {
      kind: 'blocked',
      note: 'Not available for this workspace. Contact support to change your plan.',
    }
  }
  if (target > current) {
    return { kind: 'upgrade', note: 'Payment required to upgrade' }
  }
  if (target < current) {
    return {
      kind: 'blocked',
      note: 'Downgrading isn’t supported yet. Cancel to stop billing at the end of the period.',
    }
  }
  return {
    kind: 'blocked',
    note: 'Changing billing cycle isn’t supported yet. Contact support to switch.',
  }
}
