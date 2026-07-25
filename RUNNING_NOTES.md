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

## Session 2 — authorized deferred slices (Daniel)
- `daf864672` #3390 PDF drop: RUNTIME-VERIFIED that public.file-url DOES conform
  to public.item — the in-code root-cause comment was wrong and is corrected.
  Explicit `.fileURL`/`.data` acceptance kept (library-header precedent); added
  the exact Finder-PDF provider-shape regression test.
- `7d2d2fc4c` double-click → open primary selected row in new tab/window via
  WindowOpener (#1685), honoring system "Prefer tabs"
  (`NSWindow.userTabbingPreference == .always`). Gesture on the List CONTAINER
  (per-row TapGesture(count:2) breaks selection, #612); mirrors the library
  table's shipped contract (#3364). Pure helpers `sidebarAuxiliaryOpenTarget` +
  `sidebarOpenPrefersTab`, unit-tested.
- (pending) #2496 trailing hover open-affordance: always-in-layout button
  (opacity/hit-test gated → no hover relayout), same action as double-click,
  `.help` tooltip, `accessibilityHidden` (VO/keyboard equivalent = context-menu
  Open items). Visibility rule `sidebarRowShowsOpenAffordance` unit-tested.

### Native-power audit (this batch)
- VoiceOver: row label/hint/value unchanged; new button hidden with documented
  equivalent (context-menu Open in New Tab/Window); double-click likewise.
- Tooltips: new icon-only button has `.help` (dynamic Tab/Window wording).
- Keyboard: Delete/Escape unchanged. GAP (follow-up): no ⌘-shortcut/menu-bar
  command for Open in New Tab/Window — would need FocusedCommandButtons wiring.
- Multi-selection: double-click acts on the routed primary only; selection set
  untouched. Drag/drop: unchanged; affordance is hover-gated hit-testing over
  a ~16pt frame only.

### MANAGER build-gate eyeball list (device-only validations — not guessed)
1. Live PDF drag onto a row: isTargeted highlight + import lands (#3390).
   Optional: retest whether `.item` alone now suffices (comment corrected).
2. Double-click a FOLDER row: check interplay with DisclosureGroup
   expand-toggle (NSOutlineView double-click default) — if it both expands and
   opens a window, gate the handler to non-expandable rows.
3. Container-level double-tap must not delay/steal single-click selection
   (library-table precedent #3364 suggests it's fine).
4. Hover affordance: no row relayout/re-truncation on hover, button clicks
   don't fight row selection/drag, visual weight OK (Every-Frame-Perfect).
5. Double-click on empty sidebar area below rows fires for the current primary
   selection (library table has the same trait) — confirm acceptable.

## Session 3 — keyboard/menu discoverability + header a11y + tooltips
- `aae876669` File > Open in New Tab (⌘⌥O) / Open in New Window (⌘⌥⇧O) for the
  focused sidebar's primary selection, via SidebarActions focused values +
  WindowOpener. File-menu window region folded into one Group (10-arity #3347).
  Closes the keyboard GAP flagged in session 2's audit.
- (pending) header a11y + tooltips: `isCurrentLibrary` was accent-tint-only →
  now spoken via accessibilityValue ("current library"), pure helper tested;
  full-name `.help` tooltips on library headers and item rows (rows disable
  the tooltip during inline rename via the empty-string idiom).

### Focused test command (RUN WHEN MANAGER FREES THE HEAVY SLOT — not before)
From `fichero/` (test bundle target = FicheroTests, scheme = FicheroTests):
```
xcodebuild test -scheme FicheroTests -destination 'platform=macOS' \
  -only-testing:FicheroTests/SidebarOpenAffordanceTests \
  -only-testing:FicheroTests/SidebarRowAccessibilityTests \
  -only-testing:FicheroTests/SidebarDeleteAlertsTests \
  -only-testing:FicheroTests/SidebarStateTests \
  -only-testing:FicheroTests/SidebarDropProviderClassificationTests \
  -only-testing:FicheroTests/SidebarSelectionTests \
  -only-testing:FicheroTests/SidebarMovePolicyTests
```
(Last two are pre-existing suites adjacent to my changes — cheap insurance.
NOTE: swift-testing suites (`struct` + @Test) may need the suite name without
the class-style prefix if -only-testing doesn't match; fall back to running
the FicheroTests scheme filtered with `-only-testing:FicheroTests` whole-bundle
if the selective filters skip everything, and record the actual result here.)

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
