/**
 * Landing-page motion (docs/TENORA_LANDING_PAGE_PLAN.md, proposal §E).
 *
 * One GSAP system, scoped to the landing root:
 *   - GSAP core + ScrollTrigger (three justified pinned/scrubbed sequences and
 *     one-shot reveals), SplitText (major headings), CustomEase (the two
 *     curves from the `animate` skill's tables — never approximated).
 *   - Lenis as the ONLY smooth-scroll engine, desktop fine-pointer only,
 *     driven by the GSAP ticker so ScrollTrigger and Lenis share one clock.
 *
 * Contract:
 *   - Every animated element's CSS default IS its final state. Nothing here runs
 *     under `prefers-reduced-motion: reduce` — no Lenis, pins, scrubs, splits
 *     or parallax — so reduced motion, a JS failure and a no-JS load all show
 *     the complete page.
 *   - `gsap.matchMedia` owns the breakpoint variants; crossing a breakpoint
 *     reverts the old variant before building the new one.
 *   - Cleanup (unmount, StrictMode's double effect, reduced-motion toggled on)
 *     reverts every tween, ScrollTrigger and split, destroys Lenis, removes the
 *     ticker callback and every listener. Tests pin this.
 */

import gsap from 'gsap'
import { CustomEase } from 'gsap/CustomEase'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import Lenis from 'lenis'
import { useEffect, type RefObject } from 'react'

import { useMediaQuery } from '../../components/use-media-query'

gsap.registerPlugin(ScrollTrigger, SplitText, CustomEase)

// animate skill, §5: strong ease-out for entrances, strong ease-in-out for
// on-screen movement.
const EASE_OUT = CustomEase.create('ledgerOut', '0.23,1,0.32,1')
const EASE_IN_OUT = CustomEase.create('ledgerInOut', '0.77,0,0.175,1')

export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

/** Exposed for tests and for focus-driven scrolling in the pinned rail. */
export const lenisRef: { current: Lenis | null } = { current: null }

export function useLandingMotion(rootRef: RefObject<HTMLElement | null>) {
  const reduce = useMediaQuery(REDUCED_MOTION_QUERY)

  useEffect(() => {
    const root = rootRef.current
    if (!root || reduce) return

    const mm = gsap.matchMedia(root)

    mm.add(
      {
        desktop: '(min-width: 1024px)',
        fine: '(hover: hover) and (pointer: fine)',
      },
      (context) => {
        const { desktop, fine } = context.conditions as { desktop: boolean; fine: boolean }
        const q = gsap.utils.selector(root)
        const splits: SplitText[] = []
        // Per-variant: a breakpoint change reverts this variant's listeners too.
        const listeners = new AbortController()

        // --- Smooth scroll: desktop + fine pointer only ---------------------
        let tick: ((time: number) => void) | null = null
        // Lenis needs ResizeObserver; without it, native scrolling is kept.
        if (desktop && fine && typeof ResizeObserver === 'function') {
          const lenis = new Lenis({ autoRaf: false, anchors: true })
          lenis.on('scroll', ScrollTrigger.update)
          tick = (time: number) => lenis.raf(time * 1000)
          gsap.ticker.add(tick)
          gsap.ticker.lagSmoothing(0)
          lenisRef.current = lenis
        }

        // --- Hero entrance ----------------------------------------------------
        const hero = gsap.timeline({ defaults: { ease: EASE_OUT } })
        hero.from(q('[data-hero-nav]'), { opacity: 0, duration: 0.3 })
        const heroHeading = q('[data-hero-heading]')[0]
        if (heroHeading) {
          const split = SplitText.create(heroHeading, { type: 'words', aria: 'auto' })
          splits.push(split)
          hero.from(split.words, { opacity: 0, yPercent: 40, duration: 0.6, stagger: 0.04 }, '<0.05')
        }
        hero
          .from(q('[data-hero-support]'), { opacity: 0, duration: 0.3 }, '-=0.3')
          .from(
            q('[data-bill-line]'),
            { clipPath: 'inset(0 100% 0 0)', duration: 0.45, stagger: 0.08 },
            '-=0.2',
          )
          .from(q('[data-bill-total]'), { opacity: 0, duration: 0.3 }, '-=0.15')
          .from(q('[data-hero-receipt]'), { opacity: 0, yPercent: 8, duration: 0.45 }, '-=0.2')
          .from(
            q('[data-hero-ledger]'),
            { scaleY: 0, transformOrigin: 'top center', duration: 0.6, ease: EASE_IN_OUT },
            '-=0.3',
          )

        // --- Hero pointer parallax (additive, ≤6px, fine pointers only) ------
        if (fine) {
          const heroRoot = q('[data-hero]')[0]
          const layers = q('[data-parallax]')
          const movers = layers.map((el) => ({
            x: gsap.quickTo(el, 'x', { duration: 0.6, ease: EASE_OUT }),
            y: gsap.quickTo(el, 'y', { duration: 0.6, ease: EASE_OUT }),
            depth: Number((el as HTMLElement).dataset.parallax) || 1,
          }))
          let active = true
          const settle = () => movers.forEach((m) => (m.x(0), m.y(0)))
          if (heroRoot && movers.length) {
            heroRoot.addEventListener(
              'pointermove',
              (event: PointerEvent) => {
                if (!active) return
                const rect = heroRoot.getBoundingClientRect()
                const nx = (event.clientX - rect.left) / rect.width - 0.5
                const ny = (event.clientY - rect.top) / rect.height - 0.5
                movers.forEach((m) => {
                  m.x(nx * 6 * m.depth)
                  m.y(ny * 6 * m.depth)
                })
              },
              { signal: listeners.signal, passive: true },
            )
            heroRoot.addEventListener('pointerleave', settle, { signal: listeners.signal })
            window.addEventListener('blur', settle, { signal: listeners.signal })
            document.addEventListener(
              'visibilitychange',
              () => {
                active = document.visibilityState === 'visible'
                if (!active) settle()
              },
              { signal: listeners.signal },
            )
            if (typeof IntersectionObserver === 'function') {
              const io = new IntersectionObserver(([entry]) => {
                active = entry.isIntersecting && document.visibilityState === 'visible'
                if (!active) settle()
              })
              io.observe(heroRoot)
              listeners.signal.addEventListener('abort', () => io.disconnect())
            }
          }
        }

        // --- Section headings: word reveal, once ----------------------------
        q('[data-split-heading]').forEach((heading) => {
          const split = SplitText.create(heading, { type: 'words', aria: 'auto' })
          splits.push(split)
          gsap.from(split.words, {
            opacity: 0,
            yPercent: 30,
            duration: 0.55,
            ease: EASE_OUT,
            stagger: 0.04,
            scrollTrigger: { trigger: heading, start: 'top 85%', once: true },
          })
        })

        // --- One-shot reveals, in reading order -----------------------------
        const reveals = q('[data-reveal]')
        if (reveals.length) {
          gsap.set(reveals, { opacity: 0, y: 16 })
          ScrollTrigger.batch(reveals, {
            start: 'top 88%',
            once: true,
            onEnter: (batch) =>
              gsap.to(batch, { opacity: 1, y: 0, duration: 0.5, ease: EASE_OUT, stagger: 0.06, overwrite: true }),
          })
        }

        q('[data-bar]').forEach((bar) => {
          gsap.from(bar, {
            scaleX: 0,
            transformOrigin: 'left center',
            duration: 0.7,
            ease: EASE_OUT,
            scrollTrigger: { trigger: bar, start: 'top 90%', once: true },
          })
        })

        // --- §2 problem: strike each old habit as it scrolls past -----------
        q('[data-strike-row]').forEach((row) => {
          const strike = row.querySelector('[data-strike]')
          const answer = row.querySelector('[data-answer]')
          const tl = gsap.timeline({
            scrollTrigger: { trigger: row, start: 'top 75%', end: 'top 45%', scrub: 0.6 },
          })
          if (strike) tl.from(strike, { scaleX: 0, transformOrigin: 'left center', ease: 'none' })
          if (answer) tl.from(answer, { opacity: 0, x: -12, ease: 'none' }, '<0.3')
        })

        // --- Desktop-only pinned sequences ----------------------------------
        if (desktop) {
          const rail = q('[data-rail]')[0]
          const track = q('[data-rail-track]')[0]
          if (rail && track) {
            rail.dataset.pinned = 'true'
            listeners.signal.addEventListener('abort', () => delete rail.dataset.pinned)
            // Horizontal travel, from rendered geometry. The track does not
            // start at the rail's left edge: it sits inside the centred Frame,
            // one content inset in (100px at 1440, 40px at 1024). Travelling
            // only `scrollWidth - railWidth` therefore left the last stop that
            // same inset past the right edge. Travel instead until the track's
            // right edge meets the Frame's right content edge — the mirror of
            // where its left edge starts. Measured from the Frame (never the
            // track, which is transformed mid-scrub), and re-measured on every
            // ScrollTrigger refresh via invalidateOnRefresh.
            const frame = track.parentElement as HTMLElement
            const distance = () => {
              const style = getComputedStyle(frame)
              return railTravelDistance({
                rail: rail.getBoundingClientRect(),
                frame: frame.getBoundingClientRect(),
                framePaddingLeft: parseFloat(style.paddingLeft) || 0,
                framePaddingRight: parseFloat(style.paddingRight) || 0,
                trackWidth: track.scrollWidth,
                railWidth: rail.clientWidth,
              })
            }
            gsap
              .timeline({
                scrollTrigger: {
                  id: 'workflow-rail',
                  trigger: rail,
                  start: 'top top',
                  end: () => `+=${distance() + window.innerHeight * 0.5}`,
                  pin: true,
                  scrub: 0.8,
                  invalidateOnRefresh: true,
                },
              })
              .to(track, { x: () => -distance(), ease: 'none', duration: 1 })
              .from(q('[data-rail-progress]'), { scaleX: 0, transformOrigin: 'left center', ease: 'none', duration: 1 }, 0)
              // Hold the finished state (last stop fully in view, line complete)
              // for the final stretch of the pin before it releases.
              .to({}, { duration: 0.15 })
          }

          const engine = q('[data-engine]')[0]
          const steps = q('[data-engine-step]')
          if (engine && steps.length) {
            const tl = gsap.timeline({
              scrollTrigger: {
                id: 'billing-engine',
                trigger: engine,
                start: 'top top',
                end: () => `+=${window.innerHeight * 1.6}`,
                pin: true,
                scrub: 0.8,
                invalidateOnRefresh: true,
              },
            })
            steps.forEach((step, i) => {
              if (i === 0) return
              tl.from(step, { opacity: 0.25, ease: EASE_IN_OUT }, i - 1)
              const link = step.querySelector('[data-engine-link]')
              if (link) tl.from(link, { scaleX: 0, transformOrigin: 'left center', ease: 'none' }, i - 1)
            })
          }
        }

        // Refresh measurements once fonts are in (Geist loads async).
        let cancelled = false
        document.fonts?.ready.then(() => {
          if (!cancelled) ScrollTrigger.refresh()
        })

        return () => {
          cancelled = true
          listeners.abort()
          splits.forEach((split) => split.revert())
          if (tick) gsap.ticker.remove(tick)
          gsap.ticker.lagSmoothing(500, 33)
          lenisRef.current?.destroy()
          lenisRef.current = null
        }
      },
    )

    return () => mm.revert()
  }, [rootRef, reduce])
}

/**
 * How far the workflow track must travel left so its last stop ends exactly at
 * the Frame's right content edge — mirroring where its first stop starts, at
 * the Frame's left content edge. Pure, so the geometry is unit-tested.
 *
 *   start inset = gap between rail's left edge and the Frame's content box
 *   end inset   = gap between the Frame's content box and rail's right edge
 *   travel      = start inset + track width + end inset − rail width
 */
export function railTravelDistance(g: {
  rail: { left: number; right: number }
  frame: { left: number; right: number }
  framePaddingLeft: number
  framePaddingRight: number
  trackWidth: number
  railWidth: number
}): number {
  const startInset = g.frame.left - g.rail.left + g.framePaddingLeft
  const endInset = g.rail.right - g.frame.right + g.framePaddingRight
  return Math.max(0, startInset + g.trackWidth + endInset - g.railWidth)
}

/** Scroll the pinned workflow rail so stop `index` is in view (keyboard users). */
export function scrollRailTo(index: number, count: number) {
  const trigger = ScrollTrigger.getById('workflow-rail')
  if (!trigger || count < 2) return
  const y = trigger.start + ((trigger.end - trigger.start) * index) / (count - 1)
  if (lenisRef.current) lenisRef.current.scrollTo(y, { immediate: true })
  else window.scrollTo({ top: y })
}
