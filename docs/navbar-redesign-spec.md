# Claude Code Implementation Specification — Top Navbar Redesign

**Scope:** replace the left sidebar (`AppShell`/`Sidebar` from C2) with a horizontal
top navbar, following the Framer-reference layout: wordmark left, primary nav
center-left, workspace switcher + avatar-triggered account menu on the right. The
account menu uses an expanding overlay with backdrop blur and fade-in content,
matching the reference interaction shown.

**Not in scope:** any change to route content (Login/Register/Workspace stubs/route
structure), `AuthProvider`, `TenantProvider`, the query-key isolation mechanism, or
any backend file. This is a layout/chrome change only — the pages living inside the
shell don't change.

---

## 1. Objective

The current left-sidebar layout (built in C2) works correctly but the user wants a
top-navbar layout instead, styled after a reference (Framer's marketing-site nav):
wordmark, horizontal nav links, and an avatar on the right that expands into an
account menu with a blurred backdrop and fading-in items — not a plain dropdown box.

This is a real restructure of tested C2 infrastructure, not a five-minute CSS
change — treat it with the same care as C1a or C3b, not as a quick tweak.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/stage-c2-spec.md                     - original Sidebar/AppShell spec, section 4.5
docs/ui-design-specification.md C.1, C.2  - Nav component tokens, tenant switcher
                                             rules (must stay reachable at every
                                             breakpoint - this constraint does not
                                             relax just because the layout changes)
frontend/src/components/layout/           - AppShell, Sidebar, TenantSwitcher,
                                             UserMenu, ThemeToggle - everything being
                                             restructured or relocated
frontend/src/lib/tenant/, src/lib/auth/   - the hooks/context this UI consumes;
                                             confirm nothing here needs to change
frontend/src/components/Modal.tsx         - reuse its focus-trap/backdrop/
                                             Escape-closes logic for the account menu
                                             overlay rather than reimplementing it
```

Current state: Stage C3b + typography swap committed (bbcb63e), 156/156 frontend
tests, 70/70 backend. Sidebar-based shell is fully functional; this stage changes its
visual structure, not its underlying data flow.

## 3. Existing Functionality That Must Not Change

- `TenantProvider`, `AuthProvider`, `ThemeProvider`, the query-key isolation
  mechanism, `api-client.ts` - none of these are touched. This is a presentation
  restructure consuming the same hooks (useTenant, useAuth, useTheme) the Sidebar
  already used.
- Route content, ProtectedRoute's redirect logic, and the route stub pages -
  unchanged; they render inside whatever shell wraps them.
- The tenant switcher's actual behavior (list tenants, show role, switchTenant,
  cache isolation on switch) - unchanged. Only its visual container moves.
- All 156 frontend and 70 backend tests must still pass; existing Sidebar/
  TenantSwitcher/UserMenu tests will need rewriting to match the new structure
  (expected - not a regression, a planned test migration), but their assertions
  about behavior (not markup) should carry over.

## 4. Required Changes

### 4.1 Layout structure

Replace AppShell's left-sidebar + main-content-area layout with a top bar:
logo + wordmark on the left, primary nav links (Overview, Workspace, Members,
Subscription) center-left, workspace switcher + avatar on the right, page content
below spanning the full width.

- Left: wordmark (existing logo mark + "Billing Engine" text, reused as-is from the
  current Sidebar).
- Center-left: primary nav links, horizontal, active-route highlighted the same way
  the current Sidebar highlights (accent-subtle background + accent text - reuse the
  existing active-state styling, just laid out horizontally instead of vertically).
- Right: workspace switcher (kept visible and separate from the avatar menu - do not
  bury it inside the account dropdown; per UI spec C.2 it must stay reachable and
  prominent), then the avatar.

### 4.2 Avatar account menu - expanding overlay, not a plain dropdown

Per the Framer reference: clicking the avatar (a circle with the user's initial,
reusing the existing avatar styling from UserMenu) opens an overlay containing:
email (or the existing login-session/`/me/`-resolved display logic from C3,
unchanged), the ThemeToggle, and Logout.

Construction:
- Reuse Modal's underlying mechanics (focus trap, Escape closes, focus returns to
  the trigger avatar on close, backdrop click closes) - but positioned as an
  anchored panel near the avatar, not a centered dialog. If Modal isn't
  structurally reusable for an anchored (non-centered) overlay without awkward prop
  contortions, build a new AccountMenu component that duplicates only the necessary
  a11y mechanics (focus trap, Escape, role="menu"/aria-*) - don't force-fit Modal if
  it fights the component. Report which approach was taken and why.
- Backdrop: a blurred/dimmed scrim behind the overlay content, using the
  --color-scrim token added in C3b (already theme-aware, already correctly tuned
  for both dark and light).
- Content fade-in: the menu items should fade/slide in on open, not just snap into
  place - reuse Framer Motion (already a dependency from C3b's AuthArtPanel,
  contained to that panel and now extended to this one additional use) for a short,
  simple entrance transition. Respect prefers-reduced-motion - fully disabled, not
  slowed, same rule as every other motion in this project.
- Keyboard: full keyboard operability (Tab within the menu, Escape closes, focus
  returns to the avatar trigger), aria-expanded on the trigger, role="menu" +
  role="menuitem" on the content as appropriate.

### 4.3 Mobile behavior

Per UI spec C.7 (responsive rules) and the standing rule that the tenant switcher
must be reachable at every breakpoint:
- Below the tablet breakpoint, primary nav links collapse behind a hamburger menu
  (a simple toggled panel/drawer is fine - doesn't need the same overlay treatment
  as the account menu, though it can reuse the same underlying mechanics if
  convenient).
- The workspace switcher and avatar remain visible in the top bar at every
  breakpoint - never collapsed into the hamburger menu. This was an explicit C2
  requirement and still applies.
- Report the exact breakpoint behavior chosen and verify visually, same discipline
  as C1/C2's responsive work.

### 4.4 Remove/replace old components

- Sidebar.tsx and the old AppShell's sidebar-layout logic are replaced by
  TopNavbar.tsx (or equivalent naming) + a restructured AppShell.
- TenantSwitcher.tsx and UserMenu.tsx/ThemeToggle.tsx are relocated/restyled to fit
  the new horizontal context - their underlying logic (hooks consumed, event
  handlers) stays the same; only their container/positioning changes.
- Confirm nothing else in the codebase imports the old Sidebar directly in a way
  that would break - search before deleting.

## 5. Files Likely Affected

```
new:      frontend/src/components/layout/TopNavbar.tsx
          frontend/src/components/layout/AccountMenu.tsx (or wherever the avatar
          overlay logic lives, if not folded directly into TopNavbar)
          tests for the above
modified: frontend/src/components/layout/AppShell.tsx (restructured)
          frontend/src/components/layout/TenantSwitcher.tsx (restyled for horizontal
          context, logic unchanged)
          frontend/src/components/layout/UserMenu.tsx / ThemeToggle.tsx (relocated
          into the account menu, logic unchanged)
          existing tests for Sidebar/TenantSwitcher/UserMenu - rewritten to match
          new structure, same behavioral assertions
deleted:  frontend/src/components/layout/Sidebar.tsx (once TopNavbar fully replaces it)
```

No backend file.

## 6. Business Rules

- Tenant switching, isolation, and cache-key behavior are unchanged - this stage
  only moves where the switcher control lives, not what it does.
- Logout, theme toggling, and the /me/-resolved email display all keep their
  existing C3 logic - only their visual container changes.

## 7. Accessibility Requirements

- The account menu overlay: proper aria-expanded on the trigger, role="menu",
  keyboard-operable, focus trapped while open, focus restored to the avatar on
  close.
- Horizontal nav links: keyboard-reachable in a sensible tab order, visible
  focus-visible rings (existing token), active route indicated by more than color
  alone if practical (e.g. also a distinct weight/underline) - verify against the
  existing Sidebar's active-state treatment, which should already satisfy this;
  carry it over correctly rather than reinventing it.
- Mobile hamburger: keyboard-operable, proper aria-expanded/aria-controls.

## 8. Edge Cases

- Very long tenant names in the switcher - verify truncation/overflow behavior in
  the new horizontal context (there's less width than the old sidebar's dedicated
  switcher block).
- Many nav items on a narrow desktop window (not quite mobile) - verify the layout
  doesn't overlap or squeeze awkwardly; report how this is handled if it's a
  genuine edge case at common viewport widths.
- Account menu open, then a tenant switch happens (e.g. via a keyboard shortcut or
  some other path) - menu should close cleanly, not end up in a stale state.
- Switching theme while the account menu is open - same "must re-theme correctly"
  requirement as the Modal-open case verified in C3b.

## 9. Tests Required

- TopNavbar renders all expected nav items with correct active-route highlighting.
- AccountMenu (or equivalent): opens/closes correctly, traps focus, Escape closes,
  focus returns to the avatar trigger, backdrop click closes, aria-expanded toggles
  correctly.
- Reduced-motion: the fade-in entrance is disabled under prefers-reduced-motion.
- Tenant switcher: still functions identically (list, switch, isolation) - migrate
  existing behavioral tests rather than dropping coverage.
- Mobile: hamburger menu opens/closes, workspace switcher + avatar remain visible
  and functional at mobile width.

## 10. Acceptance Criteria

1. npm run build clean.
2. npm test - report exact count; migrated tests should cover everything the old
   Sidebar tests covered, plus new tests for the account menu and mobile hamburger.
3. npm run lint clean.
4. .venv/Scripts/python.exe manage.py test - still 70/70, unaffected.
5. Manual walkthrough, screenshotted, both themes: full navbar at desktop width,
   the account menu open (showing the blur/fade), mobile hamburger open, and the
   tenant switcher functioning (switch tenants if the test account has more than
   one).
6. Confirm no dead references to the deleted Sidebar.tsx remain anywhere in the
   codebase.
7. git status - no file outside frontend/.

## 11. Must NOT Do

- Do not change any route, page content, or backend file.
- Do not modify AuthProvider, TenantProvider, ThemeProvider, api-client.ts, or the
  query-key isolation mechanism.
- Do not hide the workspace switcher inside the avatar/account menu - it stays
  separately visible per 4.1/4.3.
- Do not drop test coverage for tenant-switching behavior just because the
  component tree changed - migrate the assertions, don't delete them.
- Do not add a new animation dependency - Framer Motion is already available from
  C3b; reuse it, don't reach for something else.
- Do not start C4.

---

## Workflow

Produce a plan first and wait for approval before writing code. Given the size
(new navbar, new account-menu overlay with real a11y mechanics, mobile hamburger,
relocating three existing components, test migration), propose a session split if
that makes sense - e.g. navbar structure + nav links first, then the account-menu
overlay + mobile behavior second.
