# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `429bcb18` + local revert pending commit).

**Active worktrees:**
- `~/code/fichero-0.0.2` — sidebar UX polish + regression hardening; Daniel actively testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (on hold — two-ahead rule)

**Status:** 30 commits on 0.0.2 across today's session(s). Sidebar drag/drop/select is reliable; top-level cross-hierarchy drops work (drag folder out of parent → reorder at library root). Daniel reverted the nested-level cross-hierarchy handler — reason untracked, likely a regression in testing. Nested-to-nested reorder remains a parked item.

## Issues status

**Progressed this session:**
- `#612` sidebar drag/drop/select — resolved, Daniel verbal "working good."
- `#610` Finder folder drop flattens — fixed (`14146f8e`).
- `#605` click-then-wait — partial: off-main decode + thumbnail cache.
- `#607` between-row reorder — TOP-LEVEL reorder + cross-hierarchy out-to-root work (`c6317de9`, `4dd9d310`, `85985325`, `2a400cc9`, `855cb5f2`). Nested-to-nested reordered-beside still not supported.

**Still open on 0.0.2:**
- `#613` context-menu Delete no-op
- `#615` sidebar mode-icon rail min width
- `#609` toolbar "Run Workflow" doesn't execute
- `#608` Finder-style sidebar polish (includes right-hover chevron wish)
- `#604` preview magnifier 25% cap
- `#603` ingest mode badges
- Nested insertion lines (inside DisclosureGroup) — parked; SwiftUI List doesn't render insertion indicators inside DisclosureGroup content.

## Test Health

**Swift tests:** 253 pass / 13 pre-existing #594 fixture failures. Includes `SidebarActionsEqualityTests` + `SidebarSelectionInfoEqualityTests` regression guards.

**Python tests:** 1793 pass / 21 skipped.

## Next Session — Start Here

1. **Verify the top-level cross-hierarchy drop still works** after the nested-revert checkpoint — drag a nested folder out to library root between two siblings. Should reparent + place at insertion offset.
2. **If nested-to-nested reorder matters** — it was reverted in this session; `429bcb18` is in git history if you want to re-introduce and iterate (or reconstruct from scratch with different tradeoffs). The known limitation: SwiftUI doesn't paint insertion lines inside DisclosureGroup content, so the drop works functionally but invisibly.
3. **Remaining sidebar UX work** — right-hover chevron on category headers (would require replacing DisclosureGroup entirely, per the feedback memory), Finder-style polish (#608), mode-icon rail width (#615).
4. **Flip to untouched bugs** — #613 (Delete no-op), #609 (Run Workflow), #604 (magnifier cap).
5. **Debug HUD is still in the sidebar** (yellow bar). Remove the `sidebarDebugHUD` block + its call site in `SidebarView+ViewComponents.swift` when Daniel's ready for production-feel testing.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). 0.0.3 (Wire: Search v1) waits. Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-18 (mini-session follow-up)* — Top-level cross-hierarchy insertion drop shipped (`855cb5f2`). Nested-level variant shipped then reverted (`429bcb18` in history, revert pending commit). 30 commits total on 0.0.2 today.
