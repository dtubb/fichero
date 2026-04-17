# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `51475b07`).

**Active worktrees:**
- `~/code/fichero-0.0.2` — sidebar robustness + code review cleanup, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (on hold)

**Status:** Session 4 continued into deep sidebar code review and cleanup. Full audit at `agent-work/proposals/sidebar-review-2026-04-17.md`. ~250 LOC of dead code deleted; 3 real bugs found and fixed; drop-target hit-testing restructured to cover chevron/indent (fix for #598).

## Session 4 — full tally (continuing from session 3's end at `39cf4504`)

33+ commits on `0.0.2`. Highlights:

**Regression fixes from Daniel's device testing:**
- `97863771` revert drop highlight (hypothesis 1 for #598)
- `8eeabee3` revert image pinch v1 (#599 root cause)
- `044add35` **fix**: `.mov` drag-drop via UTI-agnostic filter (#600)
- `170150e0` **fix**: image pinch v2 — gesture-state gate (#596 reopened→closed)
- `cab67180` **fix**: Actual Size button respects TIFF pixel dimensions (#599 secondary)

**Code review cleanup:**
- `9fe669c6` delete ~250 LOC of dead sidebar code (3 full files, 3 functions, 2 view modifiers, 6 constants, 1 dead param — all with zero references)
- `1aeef8bd` **fix**: chain ID format mismatch (`chain-<id>` → `chain:<id>`); cross-section rejection in `handleDropBesideItem`
- `31b6c53a` **fix**: #598 drop-target hit-testing — modifiers now attach to outer `rowShape` (not inside DisclosureGroup's label closure), so chevron/indent hovers register
- `78b45ae8` refactor: hoist `LibrarySectionHeader` body into sub-ViewBuilders (fixes SourceKit timeout flagged by review)
- `51475b07` chore: unify Logger subsystems on bundle-matched `com.tubb.Fichero`

**Infra:**
- `1aa58bb9` chore(deps): `npm audit fix` in site/ — 9 Dependabot alerts resolved (#601 closed)
- `1c2acc9c` / `c025e685` accessibility pass on rows + library headers (#584, Step 10)

## Issues status

**Closed:** #588, #596, #601.

**Awaiting Daniel's device-verification on the next launch:**
- `#598` sidebar drag-drop routing — fixed via `31b6c53a` hit-region restructure
- `#599` image pinch + TIFF 1:1 — fixed via `170150e0` + `cab67180`
- `#600` `.mov` drag-drop — fixed via `044add35`

**Open, not yet touched:**
- `#520` Sparkle auto-update
- `#580` DropDelegate between-row drops (plan Step 7, HIGH RISK)
- `#583` sidebar test coverage remainder (5 tests)
- `#585` meta-ticket — most sub-items now shipped; the tracking umbrella
- `#589` kreuzberg cache cwd
- `#590` PDF hover magnifier
- `#591` / `#592` PDF scroll→grid/inspector (may be superseded by #595)
- `#593` Preview-style swipe nav (0.0.3)
- `#594` contract test infra
- `#595` PDF swipe navigation (awaits Daniel's design go-ahead)
- `#597` link/copy/sync corner badge

## Sidebar directory — current state

File count: **30** (down from 33 — deleted `SidebarEnvironment.swift`, `SidebarView+Environment.swift`, `SidebarView+DropHandlers.swift`).

Dead-code audit by `agent-work/proposals/sidebar-review-2026-04-17.md` items:
- ✅ Rec 1 — delete dead code (3 files + 3 functions + 2 modifiers + 6 constants + 1 param)
- ✅ Rec 2 — fix `chain-<id>` to `chain:<id>`
- ⏭️ Rec 3 — add automation observers (skipped; `AutomationServiceGenerated` is stubbed with no `@Published` state to observe; backend routes not registered in `main.py`)
- ⏭️ Rec 4 — refactor `unifiedLibrarySection` to stop duplicating `onFileDrop` closure (deferred; low-priority)
- ✅ Rec 5 — cross-section rejection in `handleDropBesideItem`

## Sidebar plan status (unchanged from previous entry except where noted)

- ✅ Step 1 — JPG picker
- ✅ Step 2 — extractActualId
- ✅ Step 3 — sortOrder field
- ✅ Step 5 — (backend routes already existed)
- ⚠️ Step 6 — Reverted, superseded by the cleaner outer-row restructure in `31b6c53a`
- ⚠️ Step 8 — Partial: double-click rename ✅; F2/Return keyboard deferred
- ✅ Step 9 — Cross-section folder drops
- ✅ Step 10 — Accessibility pass (rows + headers)
- ⚠️ Step 11 — Partial: sortOrder + SidebarItemKind + folderKind tests ✅; 5 more from the plan pending
- ⛔ Step 7 — Not started (HIGH RISK, needs throwaway prototype)
- ⛔ Step 4 — Not started (blocks on Step 7)
- ⛔ Step 12 — Not started

## Test Health

**Swift Testing suite:** all sidebar-adjacent tests green — 70+ passing across `SidebarItemFactoryTests`, `SidebarItemBuilderTests`, `SidebarItemKindTests`, `IDPrefixStrippingTests`, `CircularDropDetectionTests`, `DropURLValidationTests`, `DragDropModelTests`, plus the PDF and image regression guards.

## Next Session — Start Here

1. **Daniel: relaunch + verify** #598, #599, #600 are resolved on device per the commits above.
2. **If #598 is now visually correct** (drop highlight lights up anywhere on a folder row, drop actually moves items to the hovered target) — close it.
3. **Remaining high-value work for 0.0.2 polish** (in priority order):
   - Step 8 completion: Return/F2 keyboard rename trigger (context-menu keyboard shortcut approach is the path of least SwiftUI friction)
   - Rec 4: deduplicate `onFileDrop` closure in `unifiedLibrarySection` + drop the `swiftlint:disable function_body_length`
   - Step 7 (#580) DropDelegate between-row drops — HIGH RISK, needs throwaway prototype first
4. **When backend automation routes land** (main.py registration), wire the missing `schedules` / `triggers` Combine observers per review Rec 3.

## Persistent agents (still addressable via SendMessage)

- `bug-intake` — 0.0.2 bug filing
- `feature-future-intake` — 0.0.3+ feature filing

Use `bug: …` / `future: …` prefix next session to route.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). 0.0.3 (Wire: Search v1) waits. Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-17 (session 4 — deep sidebar review + cleanup)* — 33+ commits on 0.0.2 combined sessions 3+4. ~250 LOC of sidebar dead code removed. Drop-target hit-testing restructured for #598. Chain ID bug + cross-section drop-beside silent failure fixed. Image pinch retry via gesture-state gate (#596). TIFF 1:1 zoom respects pixel dimensions. `.mov` drag-drop works via UTI-agnostic filter. All three hot regressions (#598/#599/#600) await Daniel's device-verification.
