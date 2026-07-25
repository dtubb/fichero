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
- `511b3a0b9` chore(sidebar): retire dead unified-section expansion persistence
- `0b2b4a832` feat(sidebar): make context-menu Delete selection-aware
- `57bc7e03d` fix(sidebar): speak touch-appropriate VoiceOver hints on iOS
  (`sidebarRowAccessibilityHint` platform-conditional; rows previously told
  iOS VoiceOver users to "Right-click"/"Double-click"; new
  SidebarRowAccessibilityTests locks both branches)

## Selection-aware context-menu Delete (SIDEBAR_STATUS "deferred" item, logic half)
- #3390 PDF drop: ALREADY FIXED on this branch (`dropTypes` includes `.fileURL`/`.data`).
- Rows already have VoiceOver label/hint/value (#584) — good a11y baseline.
- New pure helper `sidebarContextDeleteTargets(clicked:selection:)` in
  SidebarViewExtensions.swift: click inside multi-selection → whole deletable
  selection ("Delete N Items"); outside → clicked row only; all-non-deletable
  batch → falls back to clicked row (keeps disabled state honest).
- `SidebarItemContextMenu` gains `deleteTargets` (default [] → [item]), so the
  preview/other call sites are unaffected. Downstream confirm dialog +
  performDelete loop were already batch-capable (Delete-key path).
- Batch open-in-tabs half remains deferred (window-opening, build-in-the-loop).

## Validations
- `swiftc -parse` on all edited files: no syntax errors.
- swiftlint at fichero/ root (real config): 0 violations on edited files.
- grep: zero remaining `unifiedSectionExpansionStates` references.
- SourceKit single-file "cannot find type" diagnostics = known noise.
- 5 new unit tests for `sidebarContextDeleteTargets` (inside/outside/single/
  mixed-deletability/all-non-deletable) + stale-key purge test. NOT run here
  (no xcodebuild per mandate) — manager runs FicheroTests at the gate.

## Active / next
- Audit swept so far: state persistence, delete paths, contextual menus,
  row accessibility (label/hint/value), drop UTTypes. NOT yet swept:
  keyboard navigation beyond Delete/Escape, tooltips coverage on truncated
  rows, section-header a11y, macOS/iOS structural differences.
- Deferred (needs build/device at manager gate, per mandate no xcodebuild):
  #2496 trailing hover affordance, #2397 cross-library drag,
  #2498 iOS/iPad library parity, batch open-in-tabs (window-opening).
- MANAGER: `.help("Export (not yet wired)")` in SidebarBottomToolbar.swift:196
  is a shipped-looking dead button — worth an issue/triage decision (I won't
  touch GitHub state).
