# Deferred Addendum — Typography Swap to Geist

**Do not run this now.** C3b (light mode) is already in progress. This is saved for
a later, separate session — after C3b is committed, and likely after C4-C6 rather
than interrupting them, unless explicitly requested sooner.

---

Read `frontend/src/styles/theme.css` and every place font-family is referenced
(currently Inter via `@fontsource/inter`, per Stage C1).

## Objective

Swap the body/UI typeface from Inter to **Geist** (Vercel's typeface — free,
similar metrics/x-height to Inter, so this is a low-risk swap, not a redesign).
Optionally swap the existing monospace stack to **Geist Mono** for consistency
(IDs, event IDs, idempotency keys, JSON — per the `mono` type-scale token from C1).

This is a token-level change — one `font-family` value (plus its mono counterpart)
— not a component redesign. If C1's "no raw hex / no hardcoded values outside the
token file" discipline extends to font-family as well (verify), this should touch
`theme.css` and the font-loading import, and nothing else.

## Required Changes

1. Add Geist (and Geist Mono, if adopted) as a bundled dependency — same approach
   as `@fontsource/inter` in C1 (bundled, no third-party network request at
   runtime; the app must render with no external font CDN access, per C1's
   original constraint).
2. Update the `--text-*` type-scale tokens' font-family reference in `theme.css`.
3. Remove the now-unused `@fontsource/inter` dependency once nothing references it
   — confirm nothing else in the codebase (README, other config) still assumes
   Inter by name.
4. Verify every existing page and primitive (all 9 C1 primitives, Login, Register,
   Workspace, the app shell) still renders correctly — this is a font swap, but
   confirm no layout breaks from any metric differences between Inter and Geist
   (line-height, letter width in dense areas like Table cells and Badge labels).
5. Verify in both themes if light mode (C3b) has landed by the time this runs.
6. Screenshot before/after for at least: a page with heading + body text (Login),
   a dense data view (Table, once one exists — Members page in C4 or whatever's
   available at the time), and Badge/status pill text at small size (legibility
   check — Geist is slightly less "invisible" at small sizes than Inter per the
   original recommendation, worth confirming it still reads cleanly).

## Acceptance Criteria

1. npm run build clean.
2. npm test — all existing tests still pass (font swap shouldn't break any
   render assertion, but confirm).
3. npm run lint clean.
4. No raw font-family string outside the token file.
5. Screenshots confirming the swap looks correct across the pages/components
   listed above.
6. .venv/Scripts/python.exe manage.py test — unaffected, confirm anyway.

## Must NOT Do

- Do not touch component structure, spacing, or color tokens — font-family only.
- Do not add a third-party font CDN dependency.
- Do not run this session until explicitly told to — it is saved for later,
  not queued to run automatically after whatever's in progress finishes.
