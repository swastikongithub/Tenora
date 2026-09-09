# Addendum — AuthArtPanel: Abstract Floating Elements

**Context:** A video reference was reviewed (frame-by-frame) for login-page
inspiration. It uses a continuously-scrolling stack of stat cards ("Total Sales
$527.8K", "Engagement +78.12%", a testimonial with a photo and name). This was
rejected in full — not just the testimonial/photo (violates the no-real-people rule)
but the entire scrolling-stat-card mechanism, because it's structurally built around
fabricated metrics. Removing the fake numbers would leave empty rectangles endlessly
cycling, which reads as broken, not clean. The mechanism and the violation aren't
separable here, so the whole concept is out — not "cards with real data," not
"cards with placeholder data," no stat cards at all.

**What's actually being added instead:** one or two purely abstract, non-numeric
shapes with slow, independent Framer Motion drift, layered over the existing
gradient/grain/grid `AuthArtPanel`. This keeps the visual interest and motion
sophistication that made the reference worth looking at, without any claim about the
product's data.

---

## Required changes

1. Add 1-2 abstract floating elements to `AuthArtPanel`, layered above the existing
   gradient/grain/grid, below the drift blooms in z-order (or wherever reads best —
   use judgment, report the choice):
   - **No text. No numbers. No icons implying a specific metric or feature.** Pure
     geometric/silhouette shapes — e.g. a rounded-rectangle outline, a simple abstract
     line-path shape, or a soft-edged panel silhouette. Think "the ghost of a UI
     element," not "a UI element with the content removed."
   - Token-driven only: `bg-overlay` (with an opacity modifier, e.g. `bg-overlay/60`,
     if a glassmorphism-style translucency is wanted — Tailwind's opacity modifiers
     work on custom tokens the same as built-ins, no new token needed for this),
     `border-subtle` for any outline, existing shadow tokens if depth is wanted.
   - Independent slow drift per shape via Framer Motion — different timing/path per
     element, not a single uniform loop. Same reduced-motion requirement as the rest
     of the panel: fully disabled (not slowed) under `prefers-reduced-motion`.
   - Must work in both themes — verify the translucency/outline approach reads
     correctly on both the dark and light gradient backgrounds, not just one.
2. **Fix a token bug found during review:** if anywhere in the login/register flow
   uses `text-primary` as the label color on the primary button's `accent-600` fill,
   correct it to the `--color-on-accent` token added in Session C3b-1 specifically to
   fix this exact contrast failure in light mode (near-black text on a purple fill
   drops to ~3.5:1, below AA). Check `Button.tsx`'s primary variant and
   `AuthLayout.tsx`'s wordmark glyph — both were already fixed in C3b-1's report, but
   verify no new code from AuthArtPanel work reintroduced the bug.
3. Screenshot the final panel, both themes, showing the abstract shapes in motion
   (a couple of frames a few seconds apart is enough to show drift, doesn't need to
   be a video).

## Must NOT do

- No numeric or statistical content of any kind in these shapes.
- No text, icons, or imagery suggesting a specific product feature or metric.
- No photos, avatars, or testimonial-style content, per the existing hard constraint.
- Do not add Google/social sign-in — unrelated to this addendum but restating since
  the rejected reference included it.

---

## Workflow

This folds into the currently in-progress Stage C3b Session 2 (`AuthArtPanel` work,
§4.5 of `docs/stage-c3b-spec.md`) — not a separate session. If Session 2 is
mid-flight, incorporate this before finalizing and screenshotting the panel. If
Session 2 has already completed and moved on, treat this as a small follow-up: plan
first, then implement, same as any other change.
