/**
 * A small, hand-rolled horizontal bar chart — docs/platform-admin-spec.md §4.6.
 *
 * Deliberately NOT a charting-library dependency: the same reasoning that kept
 * GSAP / Three.js / Lottie out of the AuthArtPanel work. Two chart shapes on
 * one internal page don't justify a package. This one component is reused three
 * times (subscription-status counts, plan distribution, monthly signups) — the
 * spec frames that as "two charts" at the panel level, which still holds.
 *
 * Every bar carries a visible text label AND its numeric value rendered as SVG
 * `<text>` — never colour-only, matching this project's accessibility
 * discipline. A zero-data set (a fresh, tenant-less deployment — spec §8)
 * renders an explicit empty message, not a collapsed 0-height chart.
 */

export interface BarDatum {
  label: string
  value: number
}

interface PlatformBarChartProps {
  title: string
  data: BarDatum[]
  /** Shown when `data` is empty or every value is 0. */
  emptyLabel?: string
}

// SVG user-space geometry. `width="100%"` scales it to the container; the
// viewBox keeps the internal proportions fixed.
const VIEW_W = 320
const ROW_H = 30
const LABEL_W = 116
const TRACK_X = LABEL_W + 6
// Reserve a strip at the right for the numeric label so the longest bar (which
// always equals `max`) doesn't push its own value past the viewBox edge.
const VALUE_W = 26
const TRACK_W = VIEW_W - TRACK_X - VALUE_W
const BAR_H = 16

export function PlatformBarChart({ title, data, emptyLabel }: PlatformBarChartProps) {
  const max = data.reduce((m, d) => Math.max(m, d.value), 0)
  const isEmpty = data.length === 0 || max === 0

  return (
    <figure className="m-0">
      <figcaption className="text-caption font-medium text-secondary">
        {title}
      </figcaption>

      {isEmpty ? (
        <p className="mt-3 text-body text-secondary">
          {emptyLabel ?? 'No data yet.'}
        </p>
      ) : (
        <svg
          className="mt-3 w-full"
          viewBox={`0 0 ${VIEW_W} ${data.length * ROW_H}`}
          role="img"
          aria-label={`${title}: ${data
            .map((d) => `${d.label} ${d.value}`)
            .join(', ')}`}
        >
          {data.map((d, i) => {
            const y = i * ROW_H
            const barW = max === 0 ? 0 : (d.value / max) * TRACK_W
            return (
              <g key={d.label}>
                <text
                  x={0}
                  y={y + ROW_H / 2}
                  dominantBaseline="middle"
                  className="fill-[var(--color-secondary)] text-[11px]"
                >
                  {d.label}
                </text>
                <rect
                  x={TRACK_X}
                  y={y + (ROW_H - BAR_H) / 2}
                  width={Math.max(barW, d.value > 0 ? 2 : 0)}
                  height={BAR_H}
                  rx={3}
                  fill="var(--color-accent-600)"
                />
                <text
                  x={TRACK_X + Math.max(barW, 2) + 5}
                  y={y + ROW_H / 2}
                  dominantBaseline="middle"
                  className="fill-[var(--color-primary)] text-[11px] font-medium"
                >
                  {d.value}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </figure>
  )
}
