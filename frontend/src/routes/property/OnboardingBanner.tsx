import { Link } from 'react-router-dom'

import type { WorkspaceOverview } from '../../lib/property/types'

/** Setup progress (plan §18 / §43.8), shown until the workspace is ready to bill. */
export function OnboardingBanner({ overview }: { overview: WorkspaceOverview }) {
  const { onboarding } = overview
  return (
    <div className="mb-6 rounded-lg border border-subtle bg-raised p-4" aria-label="Setup progress">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-label font-medium text-primary">Finish setting up this workspace</p>
          <p className="text-caption text-secondary">
            {onboarding.completed} of {onboarding.total} steps · {onboarding.percent}%
          </p>
        </div>
        <Link to="/onboarding" className="text-label text-accent-500 underline">
          Continue setup
        </Link>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-overlay"
        role="progressbar"
        aria-valuenow={onboarding.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Setup progress"
      >
        <div className="h-full bg-accent-600" style={{ width: `${onboarding.percent}%` }} />
      </div>
    </div>
  )
}
