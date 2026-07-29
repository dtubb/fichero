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

### Focused test RUN RESULT (2026-07-25, manager-authorized)
Command run verbatim (from `fichero/`, slot verified free — no competing
xcodebuild/pytest):
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
**RESULT: exit 65 — BLOCKED AT COMPILE, zero sidebar assertions executed.**
The FicheroTests bundle fails to build on an UNRELATED pre-existing file:
```
fichero-tests/LastActionScopingTests.swift:20:54: error: type 'FicheroClient' has no member 'localhost'
fichero-tests/LastActionScopingTests.swift:21:54: error: type 'FicheroClient' has no member 'localhost'
```
Root cause (traced, not fixed — manager directed this lane NOT to repair):
`ee20b94fd` ("kill .localhost footgun", #4051/#4049) removed
`FicheroClient.localhost` (removal even source-locked by
`FicheroClientLocalhostRemovalTests.swift`) but left these two call sites in
`LastActionScopingTests.swift` — the commit-only-worker-never-compiled
failure mode. This blocks EVERY FicheroTests run, not just the sidebar
selection. Sidebar suites remain unexecuted; re-run the same command after
the owning lane repairs that file (likely fix: construct
`FicheroClient(libraryPath:)`/`(baseURL:)` like sibling tests do).

### Focused test command (for re-run after the blocker is repaired)
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

## Session 4 — focus-order + menu-routing audit
### Focus architecture (traced, read-only)
- `ContentView.focusedPane: @FocusState<PaneFocus?>` (.sidebar/.content/
  .preview/.inspector); `cyclePaneFocus` skips hidden panes. Sidebar is
  `.focusable().focused($focusedPane, equals: .sidebar).focusEffectDisabled()`
  (arrow-key row nav depends on it, #560). Entry points INTO panes: library
  edge arrows (left at column edge → sidebar), clicks (`onRequestFocus`),
  AppleScript panel commands, inspector events.
- GAP (deliberately NOT blind-fixed): no keyboard path OUT of the sidebar
  into content — LibraryView has onRequestNext/PreviousPaneFocus, SidebarView
  has no counterpart. The native fix would be `.onMoveCommand(.right)` on the
  sidebar List, but that risks intercepting the native up/down row navigation
  (#560 regression class) — build-in-the-loop only. GATE CHECK: with sidebar
  focused, try Tab / right-arrow-on-leaf; if neither reaches content, thread
  an `onRequestNextPaneFocus` callback like LibraryView's and eyeball #560.
### Menu routing gap FOUND + FIXED (this commit)
- Delete key used batch `handleDeleteSelection`, but Edit ▸ Delete (⌘⌫) and
  the bottom-toolbar minus used single-item `handleDeleteSelectedItem` → a
  multi-selection delete via menu/toolbar silently deleted ONLY the primary
  row. All three entry points now share `handleDeleteSelection`;
  `handleDeleteSelectedItem` removed. Source-locked test.
- Minor (noted, not churned): `SidebarSelectionInfo.canDelete/canRename` gate
  on the PRIMARY row only — a multi-selection with a non-deletable primary
  disables Edit ▸ Delete even though the Delete key would delete the rest.
### Header a11y / tooltip edges — audit CLOSED
- `LibrarySharingBadge`: has `.help` + `.accessibilityLabel` (role-aware). OK.
- Bottom toolbar: every icon-only control has `.help` + a11y label. OK.
- Location badge, header value/hint/tooltips: done in sessions 1–3. No edges left.

## Session 5 — rename/move behavior audit (read-only, Daniel's 4 questions)

### Q1 — Rename: which types?
- Gate: `SidebarItem.ItemType.canBeRenamed` (SidebarItemContextMenu.swift:131):
  YES = document(+folder), savedSearch, conversation, workflow, chain,
  schedule, trigger, libraryHeader. NO = comparison, batch, activityRun.
- Entry points: context menu → `RenameStateManager.startRename`; Return key
  (FocusedRenameButton, plain Return, Finder convention); NO double-click
  rename (removed, #612).
- Execution: `SidebarItemRow+Rename.swift` `performRename` → per-type service
  (documents → `documentStore.renameDocument`; search/chat/workflow/chain/
  schedule/trigger → respective services; libraryHeader →
  `libraryManager.renameLibrary`). Validation: trimmed non-empty, ≤
  `SidebarConstants.maxNameLength`; failures LOGGED ONLY (no user alert).

### Q2 — Move: which types, which interactions?
- Reorder drag (same list): `.moveDisabled(icon=="tray.fill" ||
  !supportsSidebarReorder)` (SidebarView+UnifiedRows.swift:203).
  `supportsSidebarReorder` (SidebarItem.swift:128): document/savedSearch/
  workflow/chain/folder = yes; conversation/comparison/schedule/trigger/
  batch/activityRun/libraryHeader = no. Inbox (tray.fill) never drags.
- Re-parent drop onto folder rows: `routeMove` (SidebarItemRow+Helpers.swift:295)
  dispatches by id prefix — document → `moveDocumentToFolder` (shared #3014
  executor), savedSearch → `updateSavedSearch(folderPath:)`, conversation →
  `moveToFolder`, workflow → `workflowStore.moveWorkflow`. chain/schedule/
  trigger: NO move handler (debug log, silent no-op).
- Compact (iPhone) context menu "Move to Folder" shares the same executor +
  `SidebarMovePolicy` filter. Library-header drop = reparent to root.
  Errors surface via `sidebarState.dropErrorMessage` alert (#3027).

### Q3 — No-op / cycle moves
- UI: `SidebarMovePolicy.isValidTarget` (SidebarItemRow+Helpers.swift:15)
  rejects self and any descendant target (ancestor-chain walk, bounded);
  unit-locked in SidebarMovePolicyTests. Moving a child UP to its immediate
  parent is ALLOWED and re-issues the same-parent move → backend re-save
  (parent unchanged, `updated_at` churn; "Move to Folder" menu also LISTS the
  current parent). Reorder no-ops return nil (`sidebarReorderedDocIds*`).
- ENGINE: `move_document_impl` (documents.py:1831) checks ONLY parent-exists.
  ⚠️ NO self-parent check, NO descendant-cycle check, NO no-op short-circuit,
  NO lock check. Engine tests (test_document_actions.py:276-320) cover happy/
  root/404/400 only — no cycle case.

### Q4 — Protected items (Default Workflows + mirrors)
- Engine mirrors every workflow into the doc tree (`db/__init__.py:2616` area,
  `node_kind` workflow, `prototype_key="workflow"`); system presets sit under
  the seeded "Default Workflows" container (`_seed_default_workflows_container`,
  deterministic id) with `attributes.read_only=true, scope=global`.
- ⚠️ Engine docstring (db/__init__.py:2630): "read_only is descriptive only in
  Phase 1 — nothing in the write API enforces it yet (see report to Daniel)."
  KNOWN gap, re-confirmed: move/rename/delete of the container or mirrors is
  NOT refused by the engine. Re-seed re-asserts the container's NAME on next
  open ("a user rename shouldn't stick") but does NOT reset `parent_id` — a
  user MOVE of the container PERSISTS across reopens.
- UI on this branch: mirrors/container are ordinary `.document` rows —
  `canBeRenamed`/`canBeDeleted` = true, draggable (only Inbox is drag-blocked).
  The unintegrated `fix/4058-sidebar-workflow-nodes` commits (6d20ae6c4/
  621c060b9) add mirror RENDERING under Default Workflows; they do not add
  move/rename protection either.

### ⚠️ CONFIRMED INVARIANT GAPS — reported, NOT fixed (per instructions)
1. **Engine accepts cycle-creating moves**: `PUT /documents/{id}/move` with
   `parent_id == doc_id` (or any descendant) succeeds — the subtree becomes
   unreachable, and `cleanup_orphan_documents_impl` (documents.py:1636) DELETES
   unreachable rows → a client bug or raw API call can silently destroy a
   subtree. UI's SidebarMovePolicy is the only guard, and it is client-side
   only. Proposed fix (awaiting go-ahead): ancestor-walk guard in
   `move_document_impl` raising 400, + regression tests mirroring
   SidebarMovePolicyTests; ~15 lines, no contract change.
2. **Default Workflows lock unenforced** (known Phase-1, engine docstring says
   a report to Daniel exists): mirrors + container accept move/rename/delete
   from both UI and API; container moves persist. Decision needed: enforce
   `attributes.read_only` in document.move/rename/delete actions, and/or
   UI-side `canBeRenamed/canBeDeleted/moveDisabled` for
   `prototype_key=="workflow"`+`read_only` rows.

## Session 6 — full-row hit-testing + multi-selection drag audit (read-only)

### Click selection hit-testing — SOLID
- Selection = native `List(selection: Set)` + `.tag(item.destination)`
  (SidebarView+UnifiedRows.swift:204); row container has
  `.contentShape(Rectangle())` (UnifiedRows:197) and the label is
  full-width + `.contentShape` (`fullWidthLabel`, SidebarItemRow.swift:235).
  Text/Image are `.allowsHitTesting(false)` (#713) so no sub-region steals
  clicks; #645/#1165 tap fallback bails on ⌘/⇧ (Presentation+Body:44) so
  modifier selection stays native. ⌥-click is reserved by the chevron path
  (expand-subtree) and falls through to plain select on the row body. OK.

### Drag source — per-row `.draggable(SidebarDragID)`
- `.draggable` sits on the ROW CONTAINER (UnifiedRows:198, childrenList
  Drop.swift:139), not inside the label — NSTableView row-drag arms across
  the whole row (#711). Inbox rows advertise a sentinel `SidebarDragID(id:"")`.
- Multi-selection drag: plumbing is array-shaped end-to-end —
  `.dropDestination(for: SidebarDragID.self)` receives `[ids]`, the
  NSItemProvider row-drop path iterates all providers
  (handleRowDrop → internalTextOnly collects every string id), and all four
  handlers take id arrays. Payload order = AppKit's row enumeration (visual
  top-to-bottom, not click order) feeding `sidebarReorderedDocIdsWithInsert`
  order-preserving. DEVICE CHECK (cannot verify statically): dragging a
  SELECTED row actually lifts the whole selected set with per-row
  Transferables, and drag from an UNSELECTED row lifts only that row
  without disturbing the selection (expected NSTableView default).
- Inbox-in-multi-drag is safe by construction: the "" sentinel is filtered
  at every consumer (`hasPrefix("doc:")` in both insertion handlers;
  `SidebarItemKind("")==.unknown` → skipped in drop-into/beside). Verified.

### Mixed / protected / non-movable selections
- Reorder (`.onMove`): `sidebarUnifiedRowsReorderKind` (UnifiedRows:6)
  requires uniform kind + contiguous kind-block, else BAILS silently —
  mixed-kind multi-reorder shows the system insertion indicator then snaps
  back with no feedback (log only). `.moveDisabled` blocks non-reorderable
  KINDS but cannot block mixed SELECTIONS.
- Drop-into-folder (`handleDropIntoFolder`, DropHandlers.swift:389): per-item
  filters (cross-section, self, cycle) → PARTIAL APPLICATION: valid subset
  moves, rest silently skipped, no aggregate "N of M moved" feedback.
- Protected: workflow mirrors/Default Workflows have no drag/move block
  (session 5 gap #2 — unchanged).

### Intra-parent reorder vs cross-parent move — correctly split
- Same list: `.onMove` → kind-specific reorder endpoints (sortOrder only).
- Cross-parent: `.dropDestination` insertion (root UnifiedRows:72 / nested
  Drop.swift:142) → `moveSidebarDocumentsTransactionally` + optimistic
  reorder; onto-folder drops → `routeMove` (no ordering). Same-parent drag
  via insertion path self-heals: insert helper dedupes, backend gets a
  same-parent move (no-op) + reorder.

### Failure / no-op feedback
- Failures surface via `sidebarState.dropErrorMessage` alert everywhere
  (moves #3027, transactional batches, external imports #2384). GOOD.
- Silent no-ops (log-only, by design but unreviewed UX): mixed-kind reorder
  bail; cross-section/cycle/self skips; chain/schedule/trigger routeMove
  (no handler); rename failures (session 5).

### ⚠️ FINDING (code/comment divergence — reported, NOT fixed)
- `sidebarDropHighlight`'s doc comment (SidebarItemRow.swift:51-58) says it
  is "placed on the OUTER expression of a SidebarItemRow body branch so it
  covers the full List row — including the DisclosureGroup chevron/indent
  area that fullWidthLabel alone can't reach". In current code the highlight
  AND `.onDrop` AND `.contextMenu` are attached to `folderLabel`/`leafLabel`
  INSIDE the DisclosureGroup label (Presentation+Body.swift:166-192) — so
  for expandable rows the chevron/indent strip is likely NOT a drop target,
  shows no highlight, and has no context menu on right-click. Either a
  refactor moved the modifiers inward (regression vs stated intent) or the
  comment is stale. Minimal fix candidate: move highlight+onDrop to the
  DisclosureGroup branch of `bodyContent` — but that makes the EXPANDED
  children region part of the parent's drop/context surface (child rows'
  own handlers win, but the gaps between them may not), so it needs a build
  to eyeball. DEVICE CHECK first: drag a file over a folder row's chevron
  area and right-click the indent strip; fix only if confirmed dead.

## Session 7 — Option-drag duplicate + Make Alias capability matrix

### CORRECTION to session 5, gap #2
Workflow WRITE routes DO enforce the Default Workflows lock:
`_reject_if_read_only` (workflows.py:911) → 403 "Default workflows are
read-only; duplicate to edit" on update/delete. The db/__init__.py:2630
docstring ("nothing in the write API enforces it") is STALE for workflow
routes. What remains unenforced is the DOCUMENT-tree side: document.move/
rename/delete on the mirror rows and the container itself (gap #1's
move_document_impl does no lock check). Gap #2 narrows to: enforce
`attributes.read_only` in DOCUMENT actions (or UI-block those rows).

### Capability matrix (source-backed)
| Capability | Engine/API | Client service | Sidebar UI |
|---|---|---|---|
| Duplicate document/folder | ❌ none (no `document.duplicate` action/route) | ❌ | ❌ |
| Duplicate workflow | ✅ `workflow_store.duplicate` + route; presets: "duplicate to edit" is the BLESSED path (403 message) | ✅ `WorkflowStore.duplicateWorkflow` | ❌ (only WorkflowListView menus, not sidebar rows) |
| Duplicate saved search | ✅ `duplicate_saved_search` (search/core.py:1428) | ❌ not wrapped | ❌ |
| Duplicate conversation | ✅ `duplicate_conversation_impl` (chat.py:1091) | ❌ not wrapped | ❌ |
| Alias / reference node | ✅ full model: `node_aliases.py` — `Document(node_kind="alias", alias_target_id:)`, `make_alias`/`resolve_alias`; stable target id; dangling → raises (no silent fallback); no content copy; no cycle risk (no parent-edge to target). REST surface = bookmarks only (`POST /api/bookmarks`, prototype_key="bookmark"; list/resolve; `bookmark.create` action) | ✅ `BookmarkService.createBookmark(targetId:name:parentId:)` | ❌ sidebar has no Make Alias; client `Document` model is ALIAS-UNAWARE (no `node_kind`/`alias_target_id` fields decoded) — an alias row would render/behave as a plain doc and select the alias, not resolve to its target |
| Alias semantics on target rename | Name is COPIED at creation (`make_alias`), not live-synced — matches Finder (alias keeps its own name) | — | — |
| Alias semantics on target delete | `resolve_alias` → `DanglingAliasError` → bookmark resolve 404 (loud, correct) ; alias row itself deletable as a normal Document | — | — |
| Option-drag copy (cursor + payload) | n/a | n/a | ❌ SwiftUI `.draggable`/`.dropDestination` exposes NO modifier/operation-mask API — the green ⊕ copy cursor requires NSDraggingSession's sourceOperationMask (custom drag stack, FORBIDDEN). Half-native variant (read `NSApp.currentEvent.modifierFlags` in the drop handler) gives copy BEHAVIOR without the cursor affordance — and documents have no duplicate endpoint anyway |

### Minimal gaps per operation
- **Duplicate document/folder**: needs a NEW engine action (`document.duplicate`
  — deep-copy row ± artifacts policy decision) before ANY UI. Not a wiring job.
- **Duplicate workflow (sidebar)**: pure wiring — context-menu "Duplicate" on
  `.workflow` rows → existing `workflowStore.duplicateWorkflow`. Also the
  correct UX answer for read-only Default presets (engine's own 403 says so).
- **Make Alias**: engine+service exist; blocked by client alias-UNAWARENESS —
  wiring a menu item would create alias rows the sidebar renders as broken
  plain docs (select alias-doc, no target resolution, no alias badge). Needs:
  decode `node_kind`/`alias_target_id` on client `Document`, alias-aware row
  (Finder alias badge — `ingestBadge` pattern already does exactly this),
  selection resolves to target (route via `alias_target_id`; dangling → error
  surface). Medium slice, NOT sidebar-only emulation — it uses the real model.
- **Option-drag copy**: no native SwiftUI path to the copy cursor; defer until
  either Apple API or an approved AppKit introspection layer; behavior-only
  variant possible but violates "cursor affordance" expectation — NOT proposed.

### PROPOSAL (awaiting manager direction, per instructions — no code touched)
1. **Smallest high-confidence wiring**: sidebar context-menu "Duplicate" for
   workflow rows (existing `duplicateWorkflow` store call, mirrors
   WorkflowListView+Views.swift:180). One menu item + focused test. Also
   surfaces the blessed duplicate-to-edit path for locked presets.
2. Next (medium, needs design nod): client alias-awareness + "Make Alias" via
   `bookmark.create` (real alias nodes, no sidebar-only emulation).
3. Engine `document.duplicate` and Option-drag copy: file as engine/UX design
   work respectively — out of sidebar-lane scope.

## Session 8 — read-only verification of the two open findings
(Proposal 1 — sidebar workflow Duplicate wiring — remains PAUSED pending
Daniel's explicit confirmation in-conversation; nothing implemented.)

### Mirror-row document-action gap: VERIFIED across all three write paths
- `update_document_impl` (documents.py:1756) — rename via `name` field; no
  `attributes.read_only` / `node_kind` / `prototype_key` check.
- `delete_document_impl` (documents.py:1966) — soft-deletes the WHOLE subtree
  (`_descendant_document_ids`); no lock check. Consequence sharpened: deleting
  the Default Workflows CONTAINER soft-deletes every mirror row inside it in
  one call. The Workflow objects themselves live in separate storage and
  survive; whether re-seeding resurrects soft-deleted mirror rows (does
  `_save_workflow_document`'s `self.get` see deleted rows / clear
  `deleted_at`?) is runtime behavior — engine-lane question, untested.
- `move_document_impl` (documents.py:1831) — verified session 5.
- Contrast: workflow ROUTES enforce the lock (`_reject_if_read_only`, 403).
  The document-tree surface is the only unprotected side. Gap #2 stands,
  precisely scoped.

### Chevron-strip finding: CONFIRMED REGRESSION (not a stale comment)
- `abfe523ef` (Daniel, 2026-04-16, "drop-highlight covers full List row, not
  just label width (#571)") deliberately moved `sidebarDropHighlight` to the
  OUTER expression of each `bodyContent` branch — commit message explicitly:
  "covering the full row including chevron area". The comment I flagged is
  that commit's documentation.
- By the `df1286369` file-split (#1703), the highlight (+ `.onDrop`,
  `.contextMenu`) was back INSIDE the DisclosureGroup label (`folderLabel`) —
  i.e. a refactor between #571 and #1703 regressed the placement; the comment
  survived. Practical impact today is narrower than the original #571 bug
  (fullWidthLabel is maxWidth-infinity inside the label), but the
  chevron/indent strip of expandable rows is a dead zone for drop highlight,
  drop target, and right-click.
- Status: confirmed real regression of documented intent. Fix (re-hoist the
  three modifiers to the outer branch) still needs a build to eyeball the
  expanded-children interaction — queued for the gate, NOT changed now per
  instructions.

## MILESTONE-READY SOURCE LIST (for manager triage — no GitHub state touched)
Every confirmed finding / proposed follow-up, classified under exactly one of
SIDEBAR / ENGINE / LIBRARY. "Safe for sidebar worker" = this lane, commit-only,
lightweight checks; otherwise needs the named owner.

### ENGINE
1. **Cycle guard on document.move** (audit gap #1)
   - Outcome: raw API/client bug can no longer orphan a subtree (move into
     self/descendant currently succeeds; orphan cleanup then DELETES it).
   - Layer: `fichero-server/src/fichero_server/api/routes/document/documents.py`
     `move_document_impl` (:1831) + `tests/unit/test_document_actions.py`.
   - Prereq: none. ~15 lines, no contract change.
   - Acceptance: move(doc→self) → 400; move(folder→own descendant) → 400;
     move(child→its current parent) still 200; existing move tests green.
   - Owner: ENGINE (sidebar worker must not touch; full guardrail suite).
2. **Enforce Default Workflows lock on DOCUMENT actions** (gap #2, verified
   across update/delete/move — workflow routes already 403 via
   `_reject_if_read_only`)
   - Outcome: mirrors + container can't be renamed/moved/soft-deleted via the
     document tree; container move no longer persists across reopen.
   - Layer: same documents.py impls; check `attributes.read_only` /
     `node_kind`; decide 403-vs-silent for subtree delete cascade.
   - Prereq: decision — enforce in engine only, or also UI-block (see
     SIDEBAR #4). Engine wins either way (UI can't protect the raw API).
   - Acceptance: rename/move/delete on container + one mirror → 403; normal
     doc rows unaffected; re-open keeps container at root.
   - Owner: ENGINE.
3. **document.duplicate action/route** (capability matrix: absent)
   - Outcome: documents/folders can be duplicated at all (prereq for any
     sidebar Duplicate/Option-drag-copy for docs).
   - Layer: new audited action in documents.py (+ artifacts/children copy
     policy decision), OpenAPI regen, client service wrapper.
   - Prereq: design decision on deep-copy scope. Acceptance: duplicate leaf →
     new id, same content, same parent, name "copy" suffix; duplicate folder →
     policy-defined; undo restores; contract tests.
   - Owner: ENGINE (client wrapper = LIBRARY follow-on).

### LIBRARY (client shared model/store layer)
4. **Real alias support in the client** (capability matrix)
   - Outcome: Finder-style aliases work: alias rows render with an alias
     badge, selecting one opens its TARGET, dangling aliases surface an error
     (engine model `node_aliases.py` + `POST /api/bookmarks` +
     `BookmarkService` all exist; client `Document` is alias-unaware).
   - Layer: `fichero/fichero/Models/Document.swift` (decode `node_kind`,
     `alias_target_id`), selection routing (SidebarView+SelectionHandling /
     ContentView), row badge (reuse `ingestBadge` pattern in
     SidebarItemRow+Label.swift), then a "Make Alias" context-menu item.
   - Prereq: none technically; design nod on badge + dangling-alias UX.
   - Acceptance: alias row shows badge; click routes to target; target
     deleted → visible error not silent no-op; rename alias ≠ rename target;
     unit tests on routing helper + source-locked badge test.
   - Owner: LIBRARY owner (model is shared app-wide); the final context-menu
     item alone is safe for the sidebar worker AFTER the model lands.

### SIDEBAR (safe for this lane unless noted)
5. **Workflow-row "Duplicate" context-menu wiring** (PAUSED for Daniel's
   explicit OK)
   - Outcome: right-click a workflow → Duplicate; also the blessed
     duplicate-to-edit path for locked presets (engine 403 message).
   - Layer: `SidebarItemContextMenu.swift` / `SidebarItemRow+Presentation.swift`
     → existing `WorkflowStore.duplicateWorkflow` (mirrors
     WorkflowListView+Views.swift:180).
   - Prereq: Daniel's confirmation. Acceptance: menu item on `.workflow` rows
     only; duplicate appears after store reload; focused test on menu factory/
     source-lock. Safe for sidebar worker.
6. **Whole-row drop/context target — chevron-strip regression** (#571
   regression, confirmed via abfe523ef → pre-#1703 refactor)
   - Outcome: drop highlight, drop target, and right-click work on the full
     row of expandable folders including chevron/indent strip.
   - Layer: `SidebarItemRow+Presentation+Body.swift` — re-hoist
     `sidebarDropHighlight`/`.onDrop`/`.contextMenu` to the outer
     `bodyContent` branch.
   - Prereq: BUILD-IN-THE-LOOP — must eyeball expanded-children region
     (parent surface vs child rows' own handlers). Acceptance: drag-over
     chevron highlights + drops; right-click indent shows menu; drops on an
     expanded child still hit the child; #571 stays fixed.
   - Owner: sidebar worker AT THE GATE (not blind).
7. **Multi-item drag policy — feedback for partial/no-op drops**
   - Outcome: mixed-kind reorder snap-backs and partially-applied folder
     drops (valid subset moved, rest skipped) stop being silent; user sees
     "moved N of M" / a reason, per prefer-raise-over-silent-fallback.
   - Layer: `SidebarView+UnifiedRows.swift` (`handleUnifiedRowsMove` bail),
     `SidebarItemRow+DropHandlers.swift` (`handleDropIntoFolder` skips) →
     `sidebarState.dropErrorMessage` (existing surface).
   - Prereq: none. Acceptance: unit tests on a pure skip-summary helper;
     mixed drop surfaces a message; clean drops stay silent.
   - Safe for sidebar worker.
8. **Focus handoff — keyboard path OUT of the sidebar**
   - Outcome: keyboard-only users can move focus sidebar → content (today:
     into-sidebar exists via library edge-arrows; outbound path unverified).
   - Layer: `SidebarView+ViewComponents.swift` + a callback threaded from
     `ContentView` (`cyclePaneFocus`), mirroring LibraryView's
     onRequestNext/PreviousPaneFocus.
   - Prereq: DEVICE CHECK FIRST (Tab / right-arrow-on-leaf may already work
     natively); `.onMoveCommand` on the List risks the #560 arrow-nav
     regression class — build-in-the-loop.
   - Owner: sidebar worker AT THE GATE.
9. **Option-drag copy** (capability matrix: no native path)
   - Outcome (if ever): ⌥-drag shows copy cursor and duplicates into target.
   - Layer: blocked — SwiftUI exposes no drag operation-mask API; the copy
     cursor needs a custom AppKit drag stack (forbidden); docs also lack a
     duplicate endpoint (ENGINE #3 prereq).
   - Recommendation: DEFER (park as design/platform-watch; behavior-only
     modifier sniffing rejected — no cursor affordance). Not for any worker.
10. **Device-only validation bundle** (run at the manager's build gate)
    - Live PDF drag: row highlight + import (#3390; optionally retest `.item`
      alone). Folder double-click vs disclosure toggle. Container double-tap
      not delaying single clicks. Hover affordance: no relayout, no
      drag/selection fight. Double-click on empty sidebar area. Multi-select
      drag lifts whole set / unselected row lifts only itself; payload order.
      Sidebar Tab/right-arrow focus exit (feeds #8). Chevron-strip dead zone
      repro (feeds #6). Shift-range across library boundaries (old handoff).
    - Owner: manager + sidebar worker together at the gate; these gate #6/#8
      and close #3390.

### READY-TO-FILE ISSUE TITLES (manager creates/updates GitHub — NOT this lane)
Numbers reference the entries above (full outcome/files/acceptance there).
| # | Proposed issue title | Suggested labels / milestone | Depends on |
|---|---|---|---|
| 1 | Engine: reject cycle-creating document.move (self/descendant parent → 400) | engine, type:bug, P1 (data-loss vector) / Engine hardening | — |
| 2 | Engine: enforce Default Workflows read_only on document update/delete/move | engine, type:bug / Engine hardening | decision: delete-cascade 403 vs skip |
| 3 | Engine: add audited document.duplicate action (deep-copy policy + contract) | engine, type:feature / post-decision | design: copy scope |
| 4 | Library: alias-aware client Document + target-resolving selection + alias badge | client:swiftui, type:feature / Library View | design nod (badge + dangling UX) |
| 5 | Sidebar: workflow-row context-menu Duplicate (reuse WorkflowStore.duplicateWorkflow) | client:swiftui, type:feature / Sidebar View | Daniel's explicit OK (paused) |
| 6 | Sidebar: restore full-row drop/context target incl. chevron strip (#571 regression) | client:swiftui, type:bug / Sidebar View | build gate (#10) |
| 7 | Sidebar: surface partial/no-op multi-item drop results ("moved N of M") | client:swiftui, type:bug / Sidebar View | — |
| 8 | Sidebar: keyboard focus handoff out of sidebar (thread cyclePaneFocus callback) | client:swiftui, type:bug / Sidebar View | device check (#10); #560 risk |
| 9 | Design: Option-drag copy — parked (no native SwiftUI operation-mask API) | type:design, deferred | #3; platform watch |
| 10 | Gate: sidebar device-validation bundle (PDF drop, dbl-click, hover, multi-drag, focus, chevron) | type:test / next build gate | gates #6, #8; closes #3390 |

Dependency spine: #3 → any document Duplicate UI / #9 · #4 → "Make Alias"
menu item · #10 → #6, #8 · #5 → only Daniel's confirmation.
Dispatchable immediately in this lane: #7 (and #5 once confirmed).

## Session 9 — full implementation pass (Daniel: "implement all of this")
Decisions from Daniel: folder duplicate = DEEP COPY; focus exit =
right-arrow-on-leaf. AppKit allowed but iOS/visionOS must compile (all new
UI code is SwiftUI; platform bits stay `#if os(macOS)`-gated).

### Commits (in order)
- `1650dae5e`/`4dada8eeb`/`ee55e0c57`/pieces of `6d3761f21`+`1ad9f06cb` —
  FicheroTests bundle compile blockers repaired (.localhost sweep ×4 files,
  main-actor test, ItemCategory case, SidebarActions constructors).
- `5c311c4c8` workflow Duplicate + multi-item drop feedback ("Moved N of M").
- `759b3a1b9` ENGINE cycle guard on document.move (400 self/descendant).
- `6d3761f21` ENGINE Default Workflows lock on document update/move/delete
  (403; locked containers refuse new children; stale docstring fixed).
- `1ad9f06cb` #571 restoration: drop/context/highlight on outer
  DisclosureGroup (chevron strip live again).
- `66426f94e` AppKit-import guardrail fix (SwiftUI re-exports AppKit).
- `49e26bb72` ENGINE document.duplicate (deep subtree copy, "<name> copy",
  locked nodes 403, undo = delete copy). Client wrapper deferred until the
  release-flow OpenAPI regen (route not yet in committed spec — parity check
  green; contracts 9/9 tolerate app>spec).
- `89a23835c` ENGINE re-seed resurrects soft-deleted workflow mirrors
  (red→green test; pre-lock DBs healed on next open).
- `d65b562ad` Edit ▸ Delete count-aware ("Delete N Items", any-deletable
  gate) + rename failures alert.
- `a0cd2bcb0` right-arrow-on-leaf focus handoff via .onKeyPress pass-through
  (NOT .onMoveCommand — #560 class).
- `95d253b32` Duplicate menu parity: saved searches + conversations.
- `77f7981ec` Finder aliases: Document decodes node_kind/alias_target_id,
  alias badge, selection resolves target via backend fetch (dangling →
  "Alias Can't Be Opened" alert), Make Alias via bookmarks surface.

### Test evidence
- FicheroTests EXECUTION blocked by pre-existing #3902 (test-plan/scheme
  mismatch; runner hung, needs GUI session): compile-stage is fully GREEN as
  of run 7 (all earlier blockers were compile errors, now cleared) and a
  final `xcodebuild build-for-testing` validates the head commit. Suite
  EXECUTION must happen at the manager's GUI gate (#3902 fix first).
- Engine: test_document_actions + test_db + test_routes_documents =
  275 passed; contracts suite 9 passed; test_fresh_launch_authz +
  test_contract_models green (153 batch).
- Guardrails: 4 pre-existing failures only (dead_files:+Workflow.swift,
  docs_publication, mac_app_store_target outputPath — looks release-critical,
  unmerged_work). Nothing new from this branch.

### Gate eyeball additions (on top of the session-2/6 lists)
- Alias: badge legibility; alias click opens target; dangling alert; Make
  Alias lands beside original (bookmark node visibility in tree).
- Duplicate menu on workflow/search/chat rows; duplicated item appears.
- Right-arrow on leaf moves focus to content; folder arrows unchanged (#560).
- Edit ▸ Delete title/count with mixed selections; Rename-failure alert.

## Session 10 — Option-drag copy (Daniel authorized AppKit/UIKit)
- `531323ed4` Finder ⌥-drag copy, no drag-stack surgery:
  - ⌥ sampled AT DROP TIME: `NSEvent.modifierFlags` (macOS) /
    `GCKeyboard` hardware keyboard (iPadOS/visionOS) — SwiftUI drop
    callbacks expose no modifiers. `SidebarDropOperation.swift`
    (allowlisted in check_appkit_imports with rationale).
  - Copy routes through audited `document.duplicate` via the existing
    `invokeAction` path (no OpenAPI regen needed). ENGINE: optional
    `parent_id` on duplicate — cross-folder copies keep their name
    (Finder suffixes only same-folder), cycle-guard reuse (copy into own
    subtree = recursion onto own output → 400), locked target → 403.
  - Documents only; other kinds keep move under ⌥ (no targeted endpoint).
  - Copy-mode affordance: scoped `flagsChanged` monitor (lives only while
    a row is targeted) tints the drop highlight GREEN under ⌥.
- Validation: engine 141 green (7 new duplicate cases);
  `build-for-testing` EXIT 0 / zero errors at head; guardrails unchanged
  (4 pre-existing); lint clean (DropHandlers file_length pre-existing).
- GATE EYEBALL (added): ⌥-drop copies on macOS + iPad-with-keyboard; green
  tint appears, and whether flagsChanged updates it LIVE mid-drag (behavior
  correct regardless — key re-read at drop); ⌥ on insertion drops (between
  rows) still MOVES — deliberate v1 scope.
- Optional follow-ups (not queued): ⌥-copy on insertion drops; "Duplicate"
  on document-row context menus (trivial now via invokeAction).

## Session 11 — insertion-line grammar + independent bug review (FINAL)
- `8a24b677c` full Finder drag grammar at the insertion line (⌥ copy /
  ⌘⌥ alias / plain move, positioned via snapshot-diff; engine to_root;
  purple alias tint; document-row Duplicate menu).
- `b85c102e8` self-review hardening (MainActor helpers, monitor teardown on
  disappear, alias-of-alias flattening ×3 paths, stale-selection guard,
  refresh-on-partial-failure).
- `0848c696e` independent code-review findings applied:
  1. mirror resurrection GATED on is_system (user deletes stay deleted);
  2. folder-drop banner counts REAL awaited copy/alias outcomes
     ("Dropped N of M (… K failed)" + specific error appended);
  3. iterative subtree copy (recursion-limit-proof, test at limit+50).
  Reviewer verified clean: monitor lifecycle, duplicate cycle guard,
  to_root wiring, insertion-drop error paths; its alias-race finding was
  already fixed in b85c102e8.
- Validation: engine 191 green (document actions + db) + 142 (routes batch
  earlier); build-for-testing green at every commit (final run at
  0848c696e pending at write time — recorded below when landed).
- STATUS: all requested features implemented; all identified bugs fixed.
  Remaining = manager gate items only (#3902 test execution, eyeball list,
  merges, OpenAPI regen, pre-existing guardrail failures).

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
