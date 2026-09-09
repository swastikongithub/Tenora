/**
 * The visual panel for the auth pages (Login / Register / Verify), redesigned
 * for the Tenora system (Sessions 1–2 language: flat wordmark, the composed
 * `text-edge` register, hairline geometry, restraint).
 *
 * It is a BRAND / CONTEXT panel, not a marketing page. Composition (the
 * Session 3 design, unchanged):
 *   - the flat Tenora wordmark + the `<Overline>` eyebrow, top-left (branding)
 *   - a quiet geometric backdrop — a masked hairline grid and two faint
 *     concentric arcs over a single soft accent wash.
 *   - the editorial statement, lower-left: an oversized headline (`<p>`,
 *     deliberately NOT a heading — the form column's "Sign in" is the page's
 *     one `<h1>`) in the `text-statement` register + a short accent rule. On
 *     the full-height (xl) split it sits low, so the planes read as the
 *     middle layer between it and the top-left branding. This text is REAL
 *     page content, outside the aria-hidden layer, so a screen reader reaches
 *     it.
 *
 * MOTION — restored verbatim from the pre-Session-3 implementation (commit
 * f09b65c): three overlapping angular planes (`.authart__plane--1/2/3`),
 * gradient-filled polygons, each drifting on its OWN Framer keyframe track
 * (its own path / amplitude / period, `repeatType: 'mirror'`, `easeInOut`) so
 * the movement reads as parallax depth — the front plane travels furthest, the
 * back one least. Nothing else moves. Fully DISABLED — not slowed — under
 * `prefers-reduced-motion`, detected with our own `use-media-query` (NOT
 * framer's `useReducedMotion`, which caches for the tab's lifetime); the planes
 * still render, they just hold still. `data-motion` on the root reflects the
 * path taken. These planes sit on TOP of the Session 3 backdrop — they replace
 * nothing.
 *
 * Colour is tokens only; per-theme wash / line / plane strength is a handful of
 * `--authart-*` custom properties defined locally (the documented exception to
 * "theme.css owns raw values" — opacity / mix values specific to this one
 * decorative component).
 */

import { motion, type Transition } from 'framer-motion'

import { Overline } from '../components'
import { cn } from '../lib/cn'
import { Wordmark } from '../components/layout/Wordmark'
import { useMediaQuery } from '../components/use-media-query'

const DEFAULT_EYEBROW = 'Multi-tenant billing'
const DEFAULT_HEADLINE = 'Every charge, every tenant, accounted for.'

const TUNING = `
.authart {
  /* Session 3 backdrop tuning */
  --authart-wash: color-mix(in srgb, var(--color-accent-600) 16%, transparent);
  --authart-grid: color-mix(in srgb, var(--color-primary) 6%, transparent);
  --authart-ring: color-mix(in srgb, var(--color-accent-500) 24%, transparent);

  /* Drifting-plane tuning — restored from the pre-Session-3 implementation. */
  --authart-plane-fill-a: var(--color-accent-600);
  --authart-plane-fill-b: var(--color-accent-500);
  --authart-plane-stroke: color-mix(in srgb, var(--color-accent-500) 55%, transparent);
  --authart-plane-1-opacity: 0.42;
  --authart-plane-2-opacity: 0.34;
  --authart-plane-3-opacity: 0.55;
}
[data-theme='light'] .authart {
  --authart-wash: color-mix(in srgb, var(--color-accent-600) 9%, transparent);
  --authart-grid: color-mix(in srgb, var(--color-primary) 5%, transparent);
  --authart-ring: color-mix(in srgb, var(--color-accent-600) 14%, transparent);

  /* Light mode reads flat without tonal help. Depth here comes ONLY from a
     wider back-to-front opacity ramp, a firmer plane edge so overlaps separate,
     and a restrained soft shadow on the two forward planes (below) — no new
     shapes, no glow, no extra saturation. Dark mode is untouched. */
  --authart-plane-stroke: color-mix(in srgb, var(--color-accent-600) 42%, transparent);
  --authart-plane-1-opacity: 0.2;
  --authart-plane-2-opacity: 0.27;
  --authart-plane-3-opacity: 0.42;
}
/* Forward planes lift off the ground in light mode — a tight, low-opacity
   NEUTRAL shadow (not an accent glow). Dark mode keeps its flat stacking. */
[data-theme='light'] .authart__plane--2 {
  filter: drop-shadow(0 1px 2px color-mix(in srgb, var(--color-primary) 7%, transparent));
}
[data-theme='light'] .authart__plane--3 {
  filter: drop-shadow(0 2px 5px color-mix(in srgb, var(--color-primary) 9%, transparent));
}

/* Angular planes — positioned relative to the aria-hidden decor layer; the
   polygon inside each stretches to the box (preserveAspectRatio="none"),
   stroke kept constant via non-scaling-stroke. Verbatim from f09b65c. */
.authart__plane {
  position: absolute;
  pointer-events: none;
  overflow: visible;
  will-change: transform;
}
.authart__plane--1 {
  top: -10%;
  right: -16%;
  width: 78%;
  height: 72%;
  opacity: var(--authart-plane-1-opacity);
}
.authart__plane--2 {
  top: 22%;
  right: -6%;
  width: 56%;
  height: 52%;
  opacity: var(--authart-plane-2-opacity);
}
.authart__plane--3 {
  top: 10%;
  left: 46%;
  width: 42%;
  height: 40%;
  opacity: var(--authart-plane-3-opacity);
}
.authart__plane polygon {
  stroke: var(--authart-plane-stroke);
  stroke-width: 0.75;
  vector-effect: non-scaling-stroke;
}

/* Tablet band (768–1279: the short, wide top banner). The desktop plane
   geometry is proportioned for a TALL box; on a wide-short one each plane's
   box is enlarged past 100% height and pulled up with a negative top offset so
   the visible slice reads as a proportioned facet. Verbatim from f09b65c. */
@media (min-width: 768px) and (max-width: 1279.98px) {
  .authart__plane--1 {
    top: -90%;
    right: -18%;
    width: 50%;
    height: 320%;
  }
  .authart__plane--2 {
    top: -10%;
    right: 6%;
    width: 36%;
    height: 260%;
  }
  .authart__plane--3 {
    top: -40%;
    left: 42%;
    width: 28%;
    height: 220%;
  }
}
`

/** Repeating ease-in-out drift; period varies per plane. (f09b65c) */
const drift = (duration: number): Transition => ({
  duration,
  repeat: Infinity,
  repeatType: 'mirror',
  ease: 'easeInOut',
})

/** Angular plane definitions — points in each plane's own 0-100 box. Hand-placed
 *  so tests and screenshots are deterministic. Front plane (3) drifts furthest,
 *  back plane (1) least → parallax. Verbatim from f09b65c. */
const PLANES = [
  {
    cls: 'authart__plane--1',
    gradient: 'authart-plane-grad-1',
    points: '8,22 96,4 82,86 18,74',
    stops: [
      { offset: '0%', color: 'var(--authart-plane-fill-a)', opacity: 0.85 },
      { offset: '100%', color: 'var(--authart-plane-fill-b)', opacity: 0.12 },
    ],
    animate: { x: [-8, 6, -8], y: [6, -10, 6], scale: [1, 1.03, 1] },
    period: 32,
  },
  {
    cls: 'authart__plane--2',
    gradient: 'authart-plane-grad-2',
    points: '4,14 92,30 78,96 22,60',
    stops: [
      { offset: '0%', color: 'var(--authart-plane-fill-b)', opacity: 0.7 },
      { offset: '100%', color: 'var(--authart-plane-fill-a)', opacity: 0.1 },
    ],
    animate: { x: [10, -12, 8], y: [-8, 12, -6], scale: [1.02, 1, 1.04] },
    period: 24,
  },
  {
    cls: 'authart__plane--3',
    gradient: 'authart-plane-grad-3',
    points: '12,8 88,20 72,92 30,64',
    stops: [
      { offset: '0%', color: 'var(--authart-plane-fill-b)', opacity: 0.5 },
      { offset: '100%', color: 'var(--authart-plane-fill-b)', opacity: 0.04 },
    ],
    animate: { x: [-16, 18, -10], y: [12, -14, 10], scale: [1, 1.06, 1] },
    period: 19,
  },
]

export interface AuthArtPanelProps {
  className?: string
  /** Small uppercase label above the headline. */
  eyebrow?: string
  /** Oversized editorial statement — never a numeric claim. */
  headline?: string
}

export function AuthArtPanel({
  className,
  eyebrow = DEFAULT_EYEBROW,
  headline = DEFAULT_HEADLINE,
}: AuthArtPanelProps) {
  // Our own `use-media-query`, not framer's `useReducedMotion` (which caches for
  // the tab's lifetime). Defaults to `true` (assume reduced) when matchMedia is
  // unavailable. (f09b65c behaviour.)
  const reduce = useMediaQuery('(prefers-reduced-motion: reduce)')

  return (
    <div
      data-motion={reduce ? 'reduced' : 'full'}
      className={cn(
        'authart relative flex flex-col justify-between overflow-hidden bg-base',
        'px-8 py-8 lg:px-14 lg:py-12',
        className,
      )}
    >
      <style>{TUNING}</style>

      {/* Decorative backdrop — aria-hidden. */}
      <div
        aria-hidden="true"
        className="authart__decor pointer-events-none absolute inset-0"
      >
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'radial-gradient(ellipse 72% 62% at 12% 26%, var(--authart-wash), transparent 70%)',
          }}
        />
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 400 600"
          preserveAspectRatio="xMidYMid slice"
          fill="none"
        >
          <defs>
            <radialGradient id="authart-fade" cx="26%" cy="24%" r="90%">
              <stop offset="0%" stopColor="#000" />
              <stop offset="55%" stopColor="#000" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#000" stopOpacity="0" />
            </radialGradient>
            <mask id="authart-mask">
              <rect width="400" height="600" fill="url(#authart-fade)" />
            </mask>
          </defs>

          {/* a barely-there hairline grid — texture, faded to the edges */}
          <g
            mask="url(#authart-mask)"
            stroke="var(--authart-grid)"
            strokeWidth="1"
          >
            {[80, 160, 240, 320].map((x) => (
              <line key={`v${x}`} x1={x} y1="0" x2={x} y2="600" />
            ))}
            {[120, 240, 360, 480].map((y) => (
              <line key={`h${y}`} x1="0" y1={y} x2="400" y2={y} />
            ))}
          </g>

          {/* two concentric arcs — a quiet architectural sweep */}
          <circle
            cx="72"
            cy="176"
            r="236"
            stroke="var(--authart-ring)"
            strokeWidth="1"
          />
          <circle
            cx="72"
            cy="176"
            r="330"
            stroke="var(--authart-ring)"
            strokeWidth="1"
            opacity="0.6"
          />
        </svg>

        {/* Drifting planes — restored from f09b65c, layered over the backdrop. */}
        {PLANES.map((plane) => (
          <motion.svg
            key={plane.cls}
            className={`authart__plane ${plane.cls}`}
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            animate={reduce ? undefined : plane.animate}
            transition={reduce ? undefined : drift(plane.period)}
          >
            <defs>
              <linearGradient id={plane.gradient} x1="0" y1="0" x2="1" y2="1">
                {plane.stops.map((stop) => (
                  <stop
                    key={stop.offset}
                    offset={stop.offset}
                    stopColor={stop.color}
                    stopOpacity={stop.opacity}
                  />
                ))}
              </linearGradient>
            </defs>
            <polygon points={plane.points} fill={`url(#${plane.gradient})`} />
          </motion.svg>
        ))}
      </div>

      {/* Real page text — outside the aria-hidden layer.
          Branding (wordmark + eyebrow) holds the TOP-LEFT. The editorial
          statement + rule drop to the LOWER field on the full-height (xl)
          split, so the drifting planes read as the middle/background layer
          between them. Tablet/mobile keep the whole stack near the top. */}
      <div className="relative">
        <Wordmark />
        <Overline as="p" tone="accent" className="mt-1">
          {eyebrow}
        </Overline>
      </div>

      <div className="relative mt-4 max-w-[30rem] xl:mt-0 xl:pt-[40vh]">
        <p className="text-balance text-display tracking-edge text-primary xl:text-statement">
          {headline}
        </p>
        <div aria-hidden="true" className="mt-6 h-px w-12 bg-accent-500" />
      </div>
    </div>
  )
}
