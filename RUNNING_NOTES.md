# Sidebar owner — running notes

Branch `feat/sidebar-thorough`, worktree `~/code/fichero-worktrees/sidebar-thorough`.
Rules: no push/merge/GitHub-state/xcodebuild; commit-only as Claude; lightweight checks only.
Do NOT duplicate unintegrated workflow-node commits `6d20ae6c4` / `621c060b9`.

## Reviewed surfaces
- `SIDEBAR_STATUS.md` (lane/sidebar-ux handoff) — multi-select, chevron prefetch,
  one-list collapse, batch delete already landed there; follow-ups triaged below.
- `SidebarState.swift` + `SidebarStateTests.swift` — full read.
- `SidebarItemBuilder.swift` / `SidebarView+UnifiedLibrarySections.swift` — grep-level:
  `workflowItems` bucket is now LIVE (rendered via the workflow-mirror commits),
  so the old "dead bucket" cleanup note in SIDEBAR_STATUS is STALE. Do not delete.

## Decisions
- `unifiedSectionExpansionStates` confirmed dead (only self-references + one test):
  removed, with a stale-UserDefaults-key purge on init + regression test.
- SourceKit "cannot find type" diagnostics on single-file edits = known noise, ignore.

## Commits (this session)
- (pending) chore(sidebar): retire dead unified-section expansion persistence

## Validations
- `swiftc -parse` on both edited files: no syntax errors.
- grep: zero remaining `unifiedSectionExpansionStates` references.

## Active / next
- NEXT candidates (from SIDEBAR_STATUS "Still open"): #3390 PDF-drop UTType fix
  (build-in-the-loop — diagnosis says add `.fileURL` to accepted `.onDrop` types;
  risky blind), #2496 trailing affordance (visual, build-in-the-loop),
  #2397 cross-library drag, #2498 iOS/iPad parity (device-in-the-loop).
- Continue audit: contextual menus, keyboard nav, VoiceOver/accessibility,
  tooltips, macOS/iOS differences — not yet swept in this worktree.
