/**
 * Route-level code splitting (landing plan decision H-D5).
 *
 * `lazyPage(() => import('./X'), 'X')` returns a component that loads module
 * `./X` on first render and renders its named export inside a local Suspense
 * boundary. Pages sharing a module share one chunk. The boundary is local on
 * purpose: a suspending page never blanks the app shell or navbar around it.
 *
 * The fallback is an empty, aria-busy block — no text, no role — so it never
 * competes with a page's own loading states for a screen reader's (or a
 * test's) attention.
 */

import { createElement, lazy, Suspense, type ComponentType } from 'react'

const fallback = createElement('div', { 'aria-busy': true, className: 'min-h-[40vh]' })

export function lazyPage<M extends Record<string, unknown>, K extends keyof M & string>(
  load: () => Promise<M>,
  name: K,
) {
  const Lazy = lazy(async () => ({ default: (await load())[name] as ComponentType<Record<string, unknown>> }))
  function LazyPage(props: Record<string, unknown>) {
    return createElement(Suspense, { fallback }, createElement(Lazy, props))
  }
  LazyPage.displayName = `Lazy(${name})`
  return LazyPage
}
