# Sidebar CRUD — Design Spec

> Milestone: sidebar-crud

> Design-led spec (Testing Constitution). The design lead owns this intent; tests
> enforce it; code makes the tests pass. One line per behavior; each maps to a
> pinning test cited by name in the test's docstring.
> Status: APPROVED — creative director ratified; shipped.

## Intent (the design)

The sidebar IS the library's file tree. Users create, rename, move, and delete
folders and items directly in it, and the tree **and the selection** stay coherent
through every operation and through the live change-stream rebuilds. No operation on
a child ever mutates or mis-selects an ancestor.

## Behaviors (each → one pinning test)

Retagged 2026-09-18 (a Fabel review, filed as #4696/#4697, checked every `[OK]` claim
against the code and the test tree — this pass re-verified each one directly, reading the
actual test bodies rather than pattern-matching names, and updated tags/citations to match).
Both issues are already on this milestone (#291); no new issues were needed.

### Create
- `create.project.appears-and-is-selected` — **[PARTIAL]** (#5430) **Built 2026-10-04:** both File ›
  New Library… routes go through `LibraryManager.createProject(at:)`, which inserts one entry into
  `openLibraries` after Global, saves it, remembers its saved path for the next launch (the cause
  found: `saveLibrary` never re-saved the open list, which skips temporary packages, so a new
  project vanished at relaunch), and sets `createdProjectId`, which the sidebar selects through
  its click seam; `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`. Not
  pinned: the sidebar's own row rebuild and selection (view code, checked on screen). a project created in the app
  appears in the sidebar at once, as one row added in place (no reload), and is selected; setup then
  opens for it (`source.onboard.new-project-offers-setup`). Found 2026-10-04 by the maintainer: a
  new library did not appear in the sidebar. *Test:* creating a project through the real create
  path adds its row to the sidebar's store and selects it.
- `create.item.same-rule` — **[GAP]** (#4697) no dedicated "create item" (non-folder) handler
  mirrors `handleCreateNewFolder`/`createFolder`'s placement+select rule was found in
  `SidebarCreationHandlers.swift`; items appear to enter the tree by other paths (import,
  workflow/chain/schedule creation, each with its own bespoke selection logic), not a shared
  "new item follows the same rule as new folder" mechanism. Unverified as described.
- `create.folder.lands-under-context` — **[PARTIAL]** (#4697) two of three claims hold, one
  doesn't: placement under the selected folder is correct
  (`SidebarCreationHandlers.swift`'s `handleCreateNewFolder` sets `newFolderParentId` from
  the selection, `createFolder` honors it — an earlier fix landed for "previously existed but
  was never read"), and the new folder IS selected (`selectedItemId = "doc:\(newFolder.id)"`). But it
  does NOT enter rename mode — it shows a name-entry DIALOG (`showingNewFolderDialog`)
  before creation, and `createFolder` never expands the new parent afterward, so the
  freshly-selected row can be invisible (unexpanded) — the "phantom selection" #4697
  describes. No test covers any of this (#4697: zero sidebar UI tests exist).

### Read
- `read.tree.shows-all` — **[GAP]** (#4697) a rendering claim (every non-deleted child of an
  expanded folder is shown); no test — pure SwiftUI `List` rendering, and #4697 confirms
  zero sidebar UI/XCUITest files exist to pin it.
- `read.expand.persists` — **[GAP]** (#4697) no test asserts expand/collapse state or
  selection survives a change-stream rebuild. `SidebarExpandSubtreeTests` pins what gets
  DESCENDED/cached on expand/collapse, not whether that state survives a rebuild.
- `read.disclosure-triangle-visible-without-selection` — **[GAP]** (#3355) a folder/PDF with
  children must show its disclosure triangle as soon as it renders, not only after the user
  clicks it — today the triangle (and so the existence of nested children) is invisible until
  the row has been selected at least once, which reads as "no children" for anything not yet
  clicked. Distinct from `read.tree.shows-all` (which is about an EXPANDED folder's children
  rendering) — this is about the disclosure affordance existing before expansion is even
  attempted.
- `read.click-and-expand-are-timed-in-steps` — **[PARTIAL]** (#4228) a folder click and a chevron expand each log one `⏱` line split into steps, so a slow one names its slow part: the content load as fetch (engine, transport and decode; the engine's own time is its `PERF library.get_children` line), splice and render; the expand as fetch, wake (the sidebar observer), build (`SidebarItemBuilder`), index and render. Render is timed to the main thread's next turn, after the commit that draws the change. Only a document selection opens the selection → content interval: Trash, chat, a workflow and the rest never reach its end point, and one left open until the next click was logged as a 40 s click; an interval that is superseded now says it never reached its end point. *Test:* `InteractionProfileLapsTests`. The first reading in the real app is owed.
- `read.slow-turns-say-what-they-rebuilt` — **[PARTIAL]** (#4228) with `FICHERO_PRINT_CHANGES=1`, a run-loop turn that re-evaluates 20 or more view bodies logs one `◆ bodies this turn` line naming the views and how many times each ran (the window, content, library, sidebar and its rows, the pane heads, the library rows and tiles), so a click or a resize frame that rebuilds the window says what it rebuilt; the line also counts the UserDefaults changes in that turn (`UserDefaults N`), since every `@AppStorage` view re-evaluates on one. Always on: every live window resize logs `⏱ window live resize` with its frames, average frame and slowest frame. *Test:* `RenderTimingDiagnosticsTests`. The first reading in the real app is owed.
- `read.a-click-shows-its-folder-at-once` — **[GAP]** (#4228; owner 2026-11-11: "the crucial part to fix") a click on a sidebar folder highlights it at once and shows its contents without a visible wait: the window is updated once for the click and once when the rows land, not re-evaluated over and over. Baseline on 2026-11-11, measured by a fixed six-click session (synthesized clicks on row names, `read.click-and-expand-are-timed-in-steps` lines): about 2.3 s per click (selection commit 856–955 ms, selection → content 248–499 ms, load fetch 344–502 ms, load render 641–783 ms), with `ContentView` re-evaluated about nine times per click. Reducing the three pane-head `ViewThatFits` ladders to one rung, as an experiment, halved it (about 1.1 s). Done so far: recording a history entry no longer re-renders the window (`NavigationHistoryModel`, `NavigationHistoryModelTests`), the window no longer watches the document store (`DocumentStoreChangeObserver`, `ContentViewStoreObserverTests`), and unchanged settings are no longer rewritten on a click, taking a click's UserDefaults changes from thirteen to one (`DisplayAttributesStripRewriteTests`, `LibrarySortSettingsWriteTests`). Still to do: the pane-head ladders, the detail document written twice, the sidebar rows' fan-out. *2026-11-12:* a folder click changes the window's detail document ONCE: it cleared it first and then set the folder, two changes each running the whole detail cascade (seen in the NAVTRACE log, `detail.changed` A → nil → B). The clear is kept only for a folder that must be fetched (#795, `SidebarFolderDetail.plan`). *Test:* `SidebarFolderDetailTests`.
- `read.filter-never-hides-selection` — **[GAP]** (#4099) applying a sidebar filter must never
  hide the currently-selected row, even when the row no longer matches the filter text —
  losing the selected row out from under the user reads as the app forgetting what was open.
  No filter mechanism/test found for this specifically; distinct from the delete/rebuild
  selection-resilience behaviors above, which cover deletion and rebuild gaps, not filtering.

### Update — rename
- `rename.in-place` — **[GAP]** (#4697) `SidebarItemRow+Rename.swift`'s `commitRename` does
  commit on the editor's current text and `cancelRename()` on failure paths, but no test
  drives Return-commits / Esc-cancels — it's SwiftUI row state, and #4697 confirms zero
  sidebar UI tests exist.
- `rename.editable-at-once` — **[GAP]** (#6546; owner 2026-11-11) after Rename, the name is editable at once; today the text changes colour and only much later takes the caret.
- `rename.rejects-empty` — **[GAP]** (#4697) `commitRename` does
  `guard !newName.isEmpty else { renameState.cancelRename(); return }` — the guard is real,
  but untested; same zero-UI-tests gap.

### Update — move / reparent
- `move.onto-folder-reparents` — **[PARTIAL]** (#4697) the backend contract is proven —
  `TestDocumentMoveAction.test_move_effect_audit_and_undo` (`fichero-server/tests/unit/api/test_document_actions.py`)
  asserts `parent_id` actually changes and both parents' `child_count` events fire — but the
  client's drag-drop wiring (`SidebarItemRow+DropHandlers.swift`'s `processFolderDropItem` →
  the move dispatch) that triggers it from an actual sidebar drag has no test (zero sidebar
  UI tests, #4697).
- `move.onto-nonfolder-rejected` — **[OK]** `handleDropIntoFolder`
  (`SidebarItemRow+DropHandlers.swift:192-195`) guards `targetFolder.folderKind` and refuses
  (returns `false`, no-op) when the target isn't a folder; `folderKind` returns `nil` for a
  non-folder target. Pinned: `SidebarItemFactoryTests.folderKindDocumentFile`.
- `move.cross-library-rejected-not-silently-dropped` — **[GAP]** (#2397) dragging an item from
  one open library's sidebar tree onto another open library has no supported outcome today —
  neither a cross-library move nor an explicit, honest refusal; the drop appears to simply do
  nothing. Distinct from `move.onto-nonfolder-rejected`/`.no-cycle` (which cover in-library
  drop targets) — this is about the SOURCE and TARGET being different libraries entirely,
  which the move policy doesn't appear to consider at all yet.
- `move.no-cycle` — **[OK]** `SidebarMovePolicy.isValidTarget`
  (`SidebarItemRow+Helpers.swift:8-25`) walks the target's ancestor chain and refuses when
  the source appears in it (self, direct child, or deep descendant), bounded against a
  malformed cyclic chain. Pinned: `SidebarMovePolicyTests` (client); the backend
  independently rejects the same cases —
  `TestDocumentMoveAction.test_move_into_self_rejected`,
  `TestDocumentMoveAction.test_move_into_descendant_rejected`
  (`fichero-server/tests/unit/api/test_document_actions.py`).

- `move.drop-on-a-project-moves` — **[GAP]** (#6547; owner 2026-11-11, needs a decision) a plain drop of a folder onto its own project's header moves it to the project's root; only ⌥ copies. One such drop ran `document.duplicate`, then the sidebar re-rendered for a long time (279 rows in one turn); whether ⌥ was held is the open question.
- `move.self-drop-is-a-noop` — **[PARTIAL]** (#4980 stays open for the highlight half; refusal built in 13a34a779) dropping an item on itself is a drag that
  slipped, not a request (Finder does the same): no move is attempted, no alert is raised, and one
  log line (`DragDropLog.refused`) records it. `processFolderDropItem` refuses at validation with the
  ONE shared check `sidebarDropIsSelfTarget`, which the Library cell drop uses too, and
  `sidebarDropOutcomeMessage` never counts a self-drop as reportable, alone or among several dragged
  items. Pinned: `SidebarDropFeedbackTests.selfTargetCheck`, `.selfDropAloneIsSilent`,
  `.selfDropAmongMixedSelectionIsSilent`, `.selfDropNeverAppearsAlongsideARealRefusal`. Not pinned:
  the log line itself, and `processFolderDropItem`'s guard (a row method with no seam).
- `move.into-own-descendant-explains` — **[PARTIAL]** (#4980) dropping a folder into its own
  descendant is refused with a one-line explanation ("N would nest a folder inside itself"),
  unlike a self-drop: it is a real refusal the user should hear about. The message is pinned by
  `SidebarDropFeedbackTests.partialDropSummarises` and `.selfDropNeverAppearsAlongsideARealRefusal`;
  the tree walk that decides "descendant" (`SidebarItemRow.isDescendant`) has no direct test.
- `move.no-highlight-over-self` — **[GAP]** (#4980, kept open for this) a row must not light up as a
  drop target while the dragged item is over itself, so the drop is visibly not on offer. NOT built:
  SwiftUI drop validation cannot read the dragged item's identity synchronously and the app keeps
  no "currently dragged id"; it needs that plumbing and a screen to verify.
- `move.to-current-parent-writes-nothing` — **[OK]** (2026-09-26, f544626f0) moving a document into the
  parent it is already in must issue NO write: every move is an audited action, and a phantom "moved"
  entry in a research library's record is worse than none. The guard lives in
  `DocumentStore.moveDocument`, so the drag, the Move to Folder menu and the Library cell drop all
  share it. Pinned (suite `DocumentStoreReorderOutcomeTests`, executed):
  `DocumentStoreReorderOutcomeTests.testMovingADocumentIntoItsCurrentParentIssuesNoWrite`,
  `.testMovingARootDocumentToTheRootIssuesNoWrite`, and the control
  `.testMovingADocumentToAnotherParentStillAttemptsTheWrite`. Known limit: it trusts the
  cached parent.

### Library table columns
- `sidebar.table-columns-not-compiler-limited` — **[PARTIAL]** (#4482, legacy milestone fold,
  2026-09-19) the Library table's column set should be a product decision, not a side effect of
  SwiftUI's `TableColumnBuilder` capping at 10 direct children. Verified at HEAD:
  `LibraryView+TableColumns.swift`'s own comments confirm the cap was real and is now worked
  around by grouping columns to fit — `modifiedDate` and `size` are both back (restored,
  `customizationID`s `"modifiedDate"`/`"size"` present). Two of the original four dropped
  columns stay deliberately excluded, not forgotten: `path` (a local path is a lie on any host
  but the one that has it — the no-local-paths rule) and `artifacts` (overlaps the six
  per-type columns already shown; "wants a decision" per the code's own comment, not a bug).
  PARTIAL, not OK: the arity limit itself is solved and two real columns are back, but the
  `artifacts` question is still open and no test was found pinning either the restored columns
  or the arity workaround itself.
- `sidebar.table-chevron-level-with-first-line` — **[PARTIAL]** (#6473) in the Library Documents table a row's disclosure chevron sits level with the icon and the name's first line, whatever the row's height; it is not centred in a tall row. A row too short for the 3 pt icon inset keeps it centred. Test: `fichero/Tests/Unit/general/Views/LibraryTableDisclosureAlignmentTests.swift` (`chevronIsLevelWithIconTopOnOneAndFourLineRows`, the arithmetic only). Not built or run: the AppKit probe (`LibraryTableDisclosureAligner`) that moves the system's disclosure button is unseen, and the 3 pt inset is an estimate to check by eye.

### Delete
- `delete.subtree-only` — **[PARTIAL]** (#4697) deleting a folder cascades to exactly its
  descendants — proven by `TestDeleteDocument.test_delete_soft_deletes_children`
  (`fichero-server/tests/unit/api/test_routes_documents.py`), which asserts both the parent
  AND child end up soft-deleted from one parent-delete call. The INVERSE direction (deleting a
  CHILD never touches an ancestor or a sibling) is now pinned too, through the route and payload
  the sidebar sends (`fichero-server/tests/unit/api/test_sidebar_delete_and_undo_end_to_end_6175.py`, #6175). Still PARTIAL: the app-side half (the store dropping exactly
  those rows) is not asserted end to end.
- `delete.selection-safe` — **[PARTIAL]** (#4805, #4697) the "never resurrected" half is real and
  tested: `SidebarView.droppedRowIsMomentarilyMissing` treats a just-deleted row as gone, not
  a momentary rebuild gap, so it can't be resurrected into the selection. Pinned:
  `SidebarSelectionResilienceTests.testRecentlyDeletedRowIsNotResurrected`. The "moves
  to a safe target" half is now built for a ONE-item delete: `selectionAfterDelete` (the
  Finder rule: next sibling, else previous, else parent, else clears; #4805, ids fixed in
  ef5111c3d) reads the neighbours from `childrenCache` before the delete, and that row is never
  a delete target (`delete.after-delete-selection-is-never-a-delete-target`). A delete of
  several items clears the selection (`delete.multi-is-one-undo-step`). Still PARTIAL: the rule
  reads the cache, not the rows as drawn, and no UI test drives it (#4697).
- `delete.multi` — **[PARTIAL]** (#4696, #6175) a delete of several documents no longer
  refreshes per item: each library's documents run as one `UndoableChange.batch` with ONE
  trailing `documentStore.refresh()` (the engine's per-item `document.deleted` events patch the
  store in place meanwhile). "No whole-tree flash" still does not hold: that trailing refresh
  is a wholesale `loadCollections`, and saved searches, chats, workflows and automations in the
  selection still go one by one, each with its own reload.
- `delete.never-deletes-the-parent` — **[PARTIAL]** (#6175; owner bug 2026-10-26, data loss) deleting an item in the sidebar removes exactly the selected items and their descendants and NEVER an ancestor or a sibling. The engine never deletes upward, pinned through the call the sidebar makes (`fichero-server/tests/unit/models/test_deleting_a_child_leaves_ancestors_and_siblings_6175.py`) and through its route and payload, for an only child and one of several (`fichero-server/tests/unit/api/test_sidebar_delete_and_undo_end_to_end_6175.py`); the parent was lost in the app, where the selection moved to the parent after a delete and the next delete gesture acted on it (fixed by `delete.after-delete-selection-is-never-a-delete-target`, Swift uncompiled; the owner's device check is still owed).
- `delete.multi-selection-goes-together` — **[PARTIAL]** (#6535) a delete takes its rows out of the sidebar at once, before the engine is asked: a multi-selection goes together, as in Finder, not row by row as each `document.delete` lands (about 0.65 s apart). When every delete lands the store is not read again (the change stream reports the rest); that full refresh took 3.6 s on a two-item delete and reloaded the whole parent level. Only when the engine keeps a row is the store read again, so that row comes back. *Test:* `SidebarDeleteTests.aMultiSelectionLeavesTheStoreTogetherBeforeTheEngineIsAsked`. The owner's check on screen is owed.
- `sidebar.context-menu.acts-on-the-clicked-row` — **[OK]** (#6528) a row's context menu (Duplicate, Delete and the rest) acts on the row under the pointer, never on an ancestor, however deep it sits: an expanded group does not carry the menu, because its child rows sit inside it and SwiftUI gave a right-click on any of them to the outermost group, so the menu acted on the topmost expanded ancestor; the row's own label carries it, and a collapsed group still carries it over the chevron and indent strip. Finder rule for the target: a click inside a multi-selection acts on the whole selection (Duplicate copies every selected document), a click outside it acts on that row alone. *Test:* `SidebarContextTargetsTests.childRowActsOnItself` (`fichero/Tests/Unit/general/Models/SidebarContextTargetsTests.swift`).
- `sidebar.selection.highlight-first` — **[PARTIAL]** (#4228; owner ask 2026-11-11: "could the click happen instant, and then the rest fills in?") a click (or an arrow key) highlights its row at once, and the window's response (the view mode, the detail document, the folder load) follows after the highlight is drawn. The List's selection setter writes the highlight set at once and the routed primary through `SidebarSelectionState.routeAfterHighlight`, on a 10 ms timer, which fires only after the run loop has drawn; only the latest click routes, and a programmatic selection overrides one still waiting. The window watches the selection through `SidebarSelectionObserver`, not its own body, so the highlight alone does not re-render it. Measured in the app (2026-11-11, synthesized clicks and arrow keys): the highlight reached the screen 30–57 ms after the click (`⏱ sidebar selection commit … highlight`), where the whole commit had taken 700–1000 ms before. *Test:* `SidebarHighlightFirstTests`. The owner's check on screen is owed.
- `sidebar.selection.an-expanded-folder-selects-from-its-name` — **[PARTIAL]** (owner bug 2026-11-11, no issue number yet) a click on an expanded folder's name selects it, as on a closed one: plain, ⇧ (a range over its siblings) and ⌘ (add or remove). A draggable row's name is claimed by the drag machinery, so its click reaches only the row's own fallback, and #6534 had turned that off for an expanded row (its gesture sat over the child rows too), which left the name of every open folder unclickable; only the strip to its left worked. The fallback now also sits on the row's own label, which holds no child rows, and acts only while the row is expanded; the whole-row gesture acts only while it is closed, so exactly one acts and a ⌘-click toggles once (`sidebarExpandedLabelTapActs`). *Test:* `SidebarContextTargetsTests.expandedFolderNameTakesTheClick`. A plain click on an open folder's name confirmed on screen by the owner (2026-11-11); ⇧ and ⌘ on it not yet checked.
- `sidebar.selection.a-click-on-a-child-never-selects-its-parent` — **[OK]** (#6534) ⇧-click, ⌘-click and a plain click on a child row select, extend or toggle that row and never its parent, however deep it sits. A root row's fallback tap (the ⇧/⌘ path for rows whose drag payload owns label presses) sits on the whole row, and an expanded row's child rows are inside it, so a click on a child also reached the parent's handler: the parent joined the range, was toggled on by ⌘-click, or replaced the child on a plain click. An expanded row's fallback does nothing; the List's own selection handles its children. Nested rows have their own fallback, which extends a continuous range (⇧) or toggles the one clicked row on or off (⌘), as Finder does, through the same commit seam, and that is what lets a click on the name, not only to its left, multi-select. Confirmed from the log (`fallback tap on <parent>` fired for a click on a child). *Test:* `SidebarContextTargetsTests.expandedRowFallbackTapDoesNotAct` (`fichero/Tests/Unit/general/Models/SidebarContextTargetsTests.swift`). The owner's check on screen is owed.
- `delete.snapshot-so-undo-restores` — **[PARTIAL]** (built in the engine, before this line was written: `document.delete` records every row it soft-deletes WHOLE in its audit row's `before.documents`, the item and each descendant with its `parent_id` and `sort_order`, and its inverse `document.restore` re-saves those rows; a soft delete never touches artifacts, so nothing is read, embedded or drawn again. Tested through the app's routes: a batch deleted and undone as one set, and a folder put back from the Trash, return every row exactly, with no artifact made or changed, `fichero-server/tests/unit/api/test_sidebar_delete_and_undo_end_to_end_6175.py`. Not verified: that the audit row is kept until purge across retention, and undo after a restart) (#6175; owner ask 2026-10-26) every delete first records a snapshot (the items, their place, order and descendants) in the same action, so Undo (`ui/undo-everywhere.md`) and the Trash (`delete.trash-browsable`) restore them exactly where they were; the snapshot is kept until the person purges it.
- `delete.trash-browsable` — **[GAP]** (#2077) a deleted item is reachable in a browsable Trash
  surface (restore, or purge permanently) and soft-delete extends beyond Document to claim/
  entity/annotation/note/workflow. Verified: the backend routes exist for Document only
  (`GET /trash`, `POST /{doc_id}/restore`, `DELETE /{doc_id}/purge` — `documents.py:739,1585,
  1601`); no Swift Trash view exists (`grep -rl "TrashView" fichero/fichero/Views` = empty) and
  no other type has the soft-delete/restore/purge pattern. This is the FRONTEND-and-other-types
  remainder `delete.subtree-only`/`.selection-safe`/`.multi` above don't cover — those pin the
  Document-delete MECHANICS; this pins whether a deleted item can be found and undone again.
  **Designed in `safety/trash.md`** (`safety.trash.*`, revised 2026-10-10: a Trash per project
  and for the always-there project, the sidebar row, Put Back into Sources when the folder is
  gone, Empty Trash naming moved items, knowledge on trashed pages hidden not deleted), the
  Trash that `source/moving-between-projects.md`'s moves send their source to.

### Bottom bar (owner 2026-11-13, Xcode's navigator as the reference)

- `sidebar.bottom-bar.flush-in-sidebar-material` — **[PARTIAL]** (owner 2026-11-13) the sidebar's bottom bar sits at
  the sidebar's bottom edge inside the sidebar's own material, and the list scrolls under it: the bar is the list's
  bottom safe-area bar (`safeAreaBar(edge: .bottom)`), not a row stacked after the list, so the last rows pass beneath
  it and its grey is the sidebar's. On macOS one hairline above it and a hard scroll edge, as Xcode's navigator;
  iPad and iPhone keep their glass. *Built:* `SidebarView.standardSidebarContent`. *Not built:* a look on screen
  (scroll a long tree: rows pass under the bar). *Tests:* `Views/Sidebar/SidebarBottomBarPlacementTests.swift`.

- `sidebar.bottom-bar.plus-trash-filter` — **[GAP]** (owner 2026-11-13) the sidebar's bottom bar is the shared item-list
  bar (`panes.chrome.one-filter-pattern`) without Sort, as the sidebar keeps its own order (drag to arrange; owner
  2026-11-13): **+ · 🗑 · Metadata · Filter**, in one row. The − is the 🗑; the
  separate Entities button (◐) goes into the Filter menu; the filter is the shared field with the filter icon and its
  chevron, not the search loupe. *Not built.*
- `sidebar.filter-menu.shows-toggles` — **[GAP]** (owner 2026-11-13) the sidebar Filter's menu has toggles for what the
  sidebar shows: Entities and Claims (the project rows), Sources (folders only), Workflows, Models, Hosts. Toggles
  persist per window. The sidebar's **Metadata** (the bar's Metadata button) shows exactly three things, each
  switchable (owner 2026-11-13): the item count beside a folder or project, a project's sharing state, and a run in
  progress. Nothing else (no last-changed date). *Not built.*

### Legacy milestone fold — three issues redirected from "UX - Library & Reading Surface"

While folding `library-view-modes.md`'s pass 2, three sidebar-structure issues from that
legacy milestone were re-read against this spec instead — sidebar row mechanics and the
sidebar's own code health, not a Library view-mode question:

- `sidebar.rows.drag-from-the-row` — **[GAP]** (#6545) a sidebar row's drag comes from the row itself (a row-level item provider, as the Table's since #6538), so the List owns every click on a row's name and the hand-written fallback taps (#145, #6534, `fallbackTap`, `childFallbackTap`) can go.
- `sidebar.drag-session-consistent-across-row` — **[GAP]** (#713) dragging a row's icon/name
  versus dragging elsewhere on the row body should produce the SAME drag session inside a
  `DisclosureGroup` — today they diverge. Not verified as built.
- `sidebar.code-structure-consolidated` — **[GAP]** (#585) `SidebarItemRow` should split and
  the sidebar's several state managers should consolidate — a code-health ask, not a
  user-facing behavior, kept here as a GAP so it stays tracked rather than lost when its
  milestone folds.
- `sidebar.accessibility-pass` — **[GAP]** (#4164, #584) the sidebar has zero VoiceOver/accessibility
  coverage today (issue's own claim, not independently re-verified this pass).

## Delete, undo and backups (owner ruling 2026-10-26, #6175)

A delete is the one action in the sidebar that can lose a person's work, so it is specified end to end. Owner: sidebar CRUD
must also back up and undo. The first worked example below is the earlier fix of the same defect class (a just-deleted row
resolving to its parent); #6175 shows it came back or was never closed on every path, so the rules below are pinned on
EVERY path that deletes (sidebar row, context menu, Delete key, multi-select, drag to Trash, the toolbar, Services, the
engine route and the MCP/CLI tool), not on one.

- `delete.delete-means-move-to-trash` — **[GAP]** (#6175, #2077; owner 2026-10-26) Delete in the sidebar (and the menu, key,
  drag and MCP/CLI) never removes anything for good: it MOVES the items to Fichero's own Trash (a soft delete, the
  `deleted` state the engine already has), names itself "Move to Trash" and says so in the confirm. Items in the Trash are
  hidden from the library, search and every run, and their originals are untouched. Only the Trash removes for good: Delete
  Permanently and Empty Trash, each after a library snapshot and a second confirm (`safety.net.the-steps`). There is no
  path from a sidebar delete to a permanent one.
- `delete.target-is-the-selection-exactly` — **[BROKEN]** (#6175) what a delete acts on is the set of rows the person
  selected, resolved ONCE at the moment of the action to document ids, never re-derived later from the visible list, a
  focus row, a "momentarily missing" row or the parent. A selection that includes a folder and some of its children
  deletes the folder's subtree once. An empty selection deletes nothing. The ids sent are shown by the confirm step
  below, so a wrong target is visible before it happens.
- `delete.confirm-says-what-goes` — **[GAP]** (#6175) before anything is removed the app names it: "Delete 'Letters 1740'
  and the 12 items inside it?" (one line per top-level item, the count of descendants, the size of the originals NOT
  touched). A single item with no children may skip the sentence but never the undo. The default button is Cancel.
- `delete.snapshot-before-the-first-write` — **[GAP]** (#6175, `safety.net.the-steps`, `safety.net.no-snapshot-no-step`)
  the delete action first records a snapshot of exactly what it will remove: each item's row, readings, annotations,
  place (parent, order), descendants and their order, and the references to originals (never the originals). If the
  snapshot cannot be written, nothing is deleted and the app says why (disk, permission). The snapshot is part of the
  same audited action (`one-audited-action-layer`), so Undo, the Trash and the record all name the same step.
- `delete.undo-restores-in-place` — **[GAP]** (#6175, `undo-everywhere.md`) Edit > Undo after a delete puts every item
  back where it was (same parent, same order, same ids, children included) and selects them; Redo deletes them again. It
  works after the window is closed and the app restarted, for as long as the snapshot is kept (Trash retention),
  not only for the session. Undo never recreates an item that was since purged: it says so.
- `delete.trash-keeps-the-snapshot` — **[GAP]** (#2077) a deleted item sits in the browsable Trash (`delete.trash-browsable`)
  with its snapshot until the person purges it or the retention ends; Restore puts it back in place; Purge asks again
  and takes a library snapshot first (`safety.net.the-steps`).
- `delete.after-delete-selection-is-never-a-delete-target` — **[PARTIAL]** (built, tests RUN on the Air 2026-10-26: running them found that `performDelete` asked the Finder rule with the row's `doc:<id>` against raw sibling and parent ids, so it never found the row and the selection fell to a raw id that selects nothing; the rule now gets the rows' own ids, `SidebarDestination.document(id).serializedID`; `DeleteStateManager.inheritedSelectionId` is set where `performDelete` moves the selection and cleared by the next selection commit; `sidebarDeleteTargets` leaves it out of Delete, Backspace, Edit > Delete and the "-" count; Cancel is the Return default; not yet from the ROWS AS DRAWN rather than `childrenCache`, and a re-click of the already selected row does not clear it, which fails safe; the "-" button stays enabled on that row and does nothing, while Edit > Delete counts only what Delete would take, so it is disabled there (#6235); a second Delete of a row already in the Trash is done, not an error alert (#6235, `LibraryDeleteTargetsTests.testADocumentAlreadyInTheTrashIsDoneNotAnError`); a right-click on a row is an explicit gesture and is the exception: its menu deletes the clicked row) (#6175; Opus review `delete-parent-root-cause-2026-10-26.md`) after a delete the selection moves to the next sibling, else the previous, else the parent (the Finder rule, from the ROWS AS DRAWN, not from a cache that may be empty), and that selection is only a place to look: Delete, Backspace, the "-" button and Edit > Delete do nothing to it until the person selects it again by a fresh click; Return never confirms a delete by default (Cancel is the default). *Test:* `SidebarDeleteTests.deletingAnOnlyChildNeverMakesTheParentTheNextDeleteTarget`.
- `delete.what-is-shown-selected-is-what-is-deleted` — **[PARTIAL]** (built, Swift uncompiled; the diverging value is not proven without a run: Edit > Delete takes the focused Items list's selection when that pane has focus (`FocusedItemVerbs.target`), while the sidebar still draws its own row selected in grey; built so the person sees it before it happens: the Edit menu item NAMES the one item (`Delete “Parent”`), and both confirmations' messages already name it; not built: the Items list's title naming it (its file is over the lint length), the sidebar's batch confirmation listing names, a plain focus (not a selection) drawn for an app-made selection, and the run of the test below on a Mac) (#6175; owner 2026-10-26: the sidebar showed the CHILD selected while the app's real selection was the PARENT, so a delete took the parent) the rows drawn as selected in the sidebar, the selection the app holds and the set a delete acts on are ONE value: a delete takes exactly the rows the person sees selected, never a row the app selected on its own (the Preview's subject, an inherited parent, the row after a delete). Where the app moves the selection itself, the highlight moves with it, and an app-made selection is drawn as a plain focus, not as a selection a delete will use. The confirm sheet lists the rows it will delete, by name. *Test:* `SidebarDeleteTests.testTheRowsDrawnSelectedAreExactlyTheRowsDeleted` (select a child while the Preview shows another row; the delete set equals the drawn selection), run on a Mac (the Air/M4), not only compiled.
- `delete.multi-is-one-undo-step` — **[PARTIAL]** (built, the new grouping Swift uncompiled: `SidebarActions.performDelete(_:)` groups the selection with `sidebarDeleteBatches`; each library's documents, folders included, run through `UndoableChange.batch` as one step named "Move 3 Items to Trash", one refresh, nothing selected after; a row inside a folder that is also going is left to the folder (deleting it again 404'd and stopped the step part-way); the confirmation dialog calls it once; a batch that fails part-way still rebuilds the caches. Not built: a selection across two libraries is one step PER library, because a step belongs to one project (`WindowSteps`); saved searches, chats, workflows, chains and automations write no audit row, so they are deleted one by one and Cmd-Z does not bring them back. The engine half is tested end to end (one undo set restores the batch in place and order, `fichero-server/tests/unit/api/test_sidebar_delete_and_undo_end_to_end_6175.py`); not tested: a stubbed-engine Swift test that one Cmd-Z restores all) (#6175, #4696) a delete of several items is ONE undoable batch and one refresh: one Cmd-Z restores all of them. *Test:* `SidebarDeleteTests.theBatchStepIsNamedByHowManyItemsItHolds`, `.aMixedSelectionAcrossTwoLibrariesIsOneStepPerLibraryAndTheRestOneByOne`, `.aRowInsideAFolderThatIsAlsoGoingIsLeftToTheFolder`.
- `delete.which-pane-is-shown` — **[GAP]** (#6175) Edit > Delete and Cmd-Delete act on the pane that has focus, and the focused pane's selection is drawn distinctly (the sidebar's highlight is not always grey), so the person can see what a delete will take; the menu item names it ("Move 'Letters' to Trash"). *Test:* a focus test per pane.
(The rule that a delete never reaches the parent is the first bullet of this section.)
- `delete.automatic-backup-around-bulk-deletes` — **[GAP]** (#6175, `safety.net.what-a-snapshot-holds`) a delete of more
  than 25 items or more than one folder, and any Empty Trash, takes a whole-library snapshot first (cheap where the
  disk allows, `safety.net.cheap-where-the-disk-allows`), named "before deleting 40 items"; and the library keeps a
  daily snapshot while it is in use (`safety.net.the-steps`), so a bad day is recoverable to yesterday.
- `delete.every-path-same-action` — **[GAP]** (#6175, `four-architecture-rules`: logic in the engine) every route that
  deletes (sidebar, menu, key, MCP, CLI, workflow) calls the ONE engine delete action; the app sends the ids and
  nothing more; the cascade rule (descendants down, never up) lives in the engine and is tested there.

Test matrix (each row one test; engine tests run on a scratch library):
| Case | Expected |
|---|---|
| delete one leaf | its parent and siblings remain |
| delete a folder | its subtree goes, its parent and siblings remain |
| delete several siblings, one a folder | only those subtrees go |
| delete the last child of a folder | the (now empty) folder REMAINS |
| delete from each path (menu, key, drag, MCP, CLI) | same result and same snapshot |
| snapshot unwritable | nothing deleted, reason shown |
| Undo (same session, and after restart) | same parent, order, ids, children |
| purge then Undo | refused in words |
| 40 items | a named library snapshot exists first |

## First worked example (this PR — the delete behaviors)

Root cause (scoped): `SidebarView.droppedRowIsMomentarilyMissing` (the function this section
originally called `sidebarResilientSelection` — corrected 2026-09-18 to the name in the
actual code)
(`fichero/…/Sidebar/Sections/SidebarView+ViewComponents.swift`) treats a *just-deleted*
row as "momentarily missing" (indistinguishable from a lazy-rebuild gap) and re-adds
it to the selection, which then routes to the parent. Fix: a dedicated
`recentlyDeletedDocumentIds` signal on `DocumentStore` (set in `removeDocuments`), so
the resilience filter drops a genuinely-deleted row instead of resurrecting it.

Tests that pin the two delete behaviors:
1. **Unit (pure):** `droppedRowIsMomentarilyMissing` — a dropped id that is recently-deleted
   is NOT resurrected; a dropped id that is merely a rebuild gap IS kept. Pinned:
   `SidebarSelectionResilienceTests.testRecentlyDeletedRowIsNotResurrected` /
   `.testRebuildGapRowIsStillKept`. (`delete.selection-safe`)
2. **Store unit:** applying a `document.deleted` change drops those ids in place
   (`delete.subtree-only` local half) — proven by
   `ObservableDomainStoreTests.testApplyDeletedRemovesRowsInPlaceAcrossListsAndCache`;
   whether it ALSO records them into `recentlyDeletedDocumentIds` specifically is not
   directly asserted (2026-09-18 re-check — see `delete.subtree-only`'s [PARTIAL] tag above).
3. **UX (broad, Decision 9):** delete a child folder in the sidebar → assert the
   PARENT row still exists and is not the resurrected selection. **This UX test does not
   exist** (2026-09-18 re-check, #4697: zero sidebar UI/XCUITest files exist) — the spec
   promised it as "UX test 3" but it was never written.

Everything above the Delete section is the larger design, pinned in later waves —
NOT this PR.

## Sharing rows (ruled 2026-10-17)
Shared libraries appear in PROJECTS, not in a section of their own; the three behaviours live in `transport/library-sharing.md`: `sharing.sidebar.guest-row`, `sharing.sidebar.host-mark`, `sharing.sidebar.off-greys-row` (all [GAP] until built).

- `sidebar.guest-has-no-library-of-its-own` — **[PARTIAL]** (#6556; manager, 2026-11-12) a device whose engine is always another Mac's (an iPad or iPhone paired to a host) has no library of its own, so its sidebar shows only the host's: the always-there section is drawn only while it holds the host's paired library (`LibraryManager.adoptPairedRemoteLibrary`), never the device's own global package, which no engine serves. A Mac always draws its own. *Built:* `SidebarProjectSections.showsAlwaysThere`. *Test:* `AlwaysThereOnAGuestTests`. *Not seen:* the unpaired or not-yet-adopted iPad on screen; and the host's own always-there library still appears in the shared Mac's list, which `sharing.guest.machines-group`'s open-libraries rule (#6556) covers.

## Triaged from the backlog (2026-10-04)
- `sidebar.drag-identity-edges` — **[GAP]** (#4530) a foreign plain-text drag is not blamed as internal, a user folder named fichero-drag-* is not swallowed, and canonicalLibraryKey matching is case-insensitive.
- `sidebar.drop-on-content-pane-silent` — **[GAP]** (#4551) releasing an in-app library drag on the content pane is a silent no-op, never a modal Import Error (message still in ContentView+ActionsImport.swift).
- `onboarding.minimal-local-first` — **[GAP]** (#2719) First run uses a default library, asks only needed permissions, and every step is optional.
- `launch.opens-global-inbox` — **[GAP]** (#4017) Mac launch opens what the app had open straight into the main window with no library prompt or spinner; onboarding is a sheet.
- `launch.no-splash-ever` — **[GAP]** (#4261) The New/Open Library splash never appears for a user with saved libraries; connection/auth state shows inline in the sidebar.
- `launch.library-in-trash-leaves-the-reopen-list` — **[PARTIAL]** (#6377; built, Swift uncompiled) a saved library whose path lies inside a Trash folder (a volume's `.Trashes`, or `~/.Trash`) is dropped from the saved reopen list at launch with one log line, and is not asked of the engine again; a library moved to the Trash is not one the person has open. Whether the two live libraries the same volume refused are the socket-at-launch race (#6375) or lost bookmarks is not settled by this. Test: `LibraryTrashPathTests`.
- `launch.open-libraries-consistent-across-devices` — **[GAP]** (#2498) the sidebar on iOS/iPad lists the same open libraries the engine has open for the Mac, instead of only one.
- `sidebar.no-bottom-entity-activity-workflow-sections` — **[GAP]** (#4102) the sidebar no longer renders the bottom Activity/Entities/Workflows/Automations sections; libraries are listed as their own separate section.
- `launch.prunes-rejected-saved-library` — **[GAP]** (#4239) a saved library path the engine definitively rejects (403 roots) is pruned from the saved list and never retried in a session; UI-test libraries never persist into real preferences.
- `sidebar.row-heights-agree` — **[GAP]** (#4476) library rows and item rows reach the same height by one mechanism (today 2pt apart via two), per the 2026-08-02 decision document.
- `read.expand.streams-in-place-with-trailing-spinner` — **[GAP]** (#4564) opening a folder adds children in place with no entry animation, while a spinner shows at the trailing edge of the folder's own row (today it replaces the leading icon, SidebarRowLabelCore.swift:104).
- `read.expand.rows-below-move-once` — **[GAP]** (#4564; owner, on screen, 2026-11-11) opening or closing a folder moves the rows below it once, to their new place: no chevron flashes in from the left edge, the next folder's chevron does not bounce on open, and the chevrons below do not bounce on close; image rows arrive as folder rows do, in place. Leading theory, unconfirmed: a closed folder holds an invisible zero-height placeholder row (`disclosureContent`, #3355), and the swap between it and the child rows is animated as a delete plus an insert.
- `read.selecting-a-pdf-shows-its-pages` — **[PARTIAL]** (#6539; owner 2026-11-11) clicking a multi-page PDF in the sidebar shows its pages in the item list, as clicking a folder shows the folder's contents. It used to keep the level the PDF sits in, because `SidebarSourceOpen.plan` treated every file as a source that opens in its folder (#5428). A PDF with pages (`SidebarSourceOpen.listsItsPages`: a PDF with a child count) is no longer such a source, so it takes the container route; a PDF not split into pages yet still opens selected in its folder. This narrows `library.modes.the-view-follows-the-node` for PDFs. *Test:* `LibraryViewFollowsNodeTests.pagedPdfListsItsPages`, `pdfOpensInItsFolder`. Not yet seen in the running app.
- `read.keyboard.arrow-descends-into-library-header` — **[GAP]** (#4566) down and right arrow move from a selected library header into its children, without swallowing all arrows via onMoveCommand (#560).
- `read.keyboard.option-arrow-expands-collapses-subtree` — **[GAP]** (#4567) option-right expands and option-left collapses a row and all descendants, for every selected row (click versions exist: sidebarExpandSubtree/sidebarCollapseSubtree, keyboard not bound).
- `read.selection.modifier-click-on-any-row-name` — **[GAP]** (#4571) cmd/shift/option-click on the NAME extends selection for page (leaf) rows and the library header too, and shift-click above the anchor ranges upward; disclosure rows are fixed (22424f614).
- `sidebar.vocabulary-collection` — **[GAP]** (#3752) the user-visible and wire vocabulary is 'collection' everywhere; backend still serves api/routes/document/folders.py (folders.py is only a shim) with the folders tag and docType .folder.
- `sidebar.library-section-stable-placement` — **[GAP]** (#3336) the Library section (and any additional open libraries) renders in one stable position inside the sidebar column across launches and window states.
- `sidebar.ipad-rows-and-toggle-match-the-mac` — **[PARTIAL]** (#6557; owner, on an iPad mini, 2026-11-12) on the iPad every sidebar row has the leading symbol it has on the Mac: folders, Sources, the knowledge rows, Trash, and a shared Mac's library rows, which carry a project's symbol (`SharedLibraryRowView.systemImage`, the same as `LibrarySectionHeader.systemImage`). The navigation bar has the system sidebar toggle, so the sidebar can be hidden and brought back. Disclosure chevrons stay on the trailing edge, as in iPadOS's own sidebars (Files); a custom leading chevron would fold an open folder's children into one row and lose per-row selection (owner chose this, 2026-11-12). *Test:* `SharedMachineSectionsTests.aSharedLibraryRowCarriesTheProjectSymbol`. Seen on the iPad 2026-11-12: the toggle and the folder, knowledge and Trash icons were already drawn; the shared row's icon is new.
- `sidebar.ipad-rotation-does-not-rebuild` — **[GAP]** (#2408) rotating an iPad does not re-run SidebarItemBuilder.build or rebuild the split view; verify with the InteractionProfile log on a device, then fix.
- `sidebar.click-path-does-no-full-tree-walks` — **[PARTIAL]** (#4228) a sidebar click does no per-body full-forest walks (cached buckets, XOR signature, dictionary lookups landed in 9568619fb, d35a69f49); the window open/close beachball is not re-measured.
- `move.no-cycle-covers-every-kind` — **[BROKEN]** (#5064) the Move to Folder menu and the drag path use one circularity check that covers every item kind, not documents only.
- `dup.deep-tree-fits-the-memory-cap` — **[OK]** (#5100) duplicating a 1,050-deep tree completes inside DuckDB's 1.5 GB cap. *Built: measured, the memory was linear in rows but 1.35 MB a row from `INSERT … ON CONFLICT` held until commit (duckdb#26830); `Database.save` plain-INSERTs a new row (0.013 MB); the cap is unchanged. `test_new_rows_in_a_transaction_stay_small.py`, `test_duplicate_survives_trees_deeper_than_the_recursion_limit`.*
- `sidebar.expand-is-instant` — **[GAP]** (#5277) expanding a sidebar folder draws its children at once from a prefetched light listing and publishes per folder, not as a store-wide re-render (the one-level look-ahead landed in 3c696d7aa; the light listing and per-folder publish remain).
- `sidebar.one-selection-one-fetch` — **[BROKEN]** (#4995) one sidebar selection fetches the document, its children and thumbnails once (loadChildren and document fetch single-flight, handleSelection once); the four-builds half landed in 75ddc9d03.
- `sidebar.project.click-selects-and-inspects` **[PARTIAL]** (#5422) *Built 2026-10-04: the row's tap writes the project through `SidebarSelectionState.selectProject`; the Inspector routes a project selection (with nothing picked in the Library pane since) to `ProjectInspector` (name, location, counts from `GET /api/stats`, the saved recipe with Set Up…, sharing), a project click clears the pane's pick like a folder click (retiring #4299's carve-out), and the row's platter has one `listRowBackground` writer; `fichero/Tests/Unit/general/Views/Shell/ProjectRowInspectsTests.swift`. Not yet seen in the app: the test does not drive the real click or the drawn highlight.* Clicking a project row in the sidebar shows the row selected and switches the Inspector to the project itself: its name, location, recipe and Set Up…, sharing and counts. Tested through the real selection store.
- `sidebar.option-click-expands-everything` **[BROKEN]** (#5023): Option-clicking a library's disclosure triangle expands every folder and shows their children, visible rows first, without freezing, and no row is left with a spinner in place of its icon.
- `sidebar.project.has-a-sources-folder` **[PARTIAL]** (#5413) *Engine half built 2026-10-05: `importers/sources_folder.py` is the one rule. The library open (`DatabaseManager.get_database`, which also serves `POST /api/library`) gives a project its Sources folder once, reusing a live top-level folder already named Sources, and never re-makes one a person deleted; every import route that names no folder (`/api/ingest/file`, `/files`, `/folder`, `/xlsx`, `/api/documents/import`, `/import-batch`, the browser save) lands in it, making it again if it was deleted. Nothing already in a project moves. The global library (the always-there project) has one too (maintainer, 2026-10-10: a first launch shows its Sources). `fichero-server/tests/unit/importers/test_sources_folder.py`. App half 2026-10-05: nothing to build; Sources is an ordinary folder in the project's tree and the sidebar draws it like any other (no app code names it). Not yet seen in the app.* Every project has a folder named Sources, where new material lands when an import names no other folder. New projects are created with it and an existing project gets one when it next opens; nothing already in the project moves. The engine creates and chooses the folder; the app only shows it. Tested through the real engine route.
- `sidebar.knowledge.rows-only-when-non-empty` **[PARTIAL]** (#5413) *Engine half built 2026-10-05: `GET /api/stats/knowledge` returns each row's count (entities not merged away, claims, citations, references, interpretations, frameworks, patterns), one `COUNT(*)` each, to be asked again on `entity.*`, `claim.*`, `citation.*`, `reference.*` and `interpretation.*` change events; `fichero-server/tests/unit/api/test_knowledge_row_counts.py`. App half built 2026-10-05: one `KnowledgeRowCountsStore` per project reads the route through the generated client, is registered with the project's change stream, and on an event of one kind re-reads the route and writes only that kind's count, in place; `SidebarKnowledgeRowsNode` draws a row only when its count is above 0. `fichero/Tests/Unit/general/Views/Sidebar/SidebarKnowledgeRowsTests.swift`. Only Entities and Claims have a row today: Citations, References and the hermeneutic counts are read and kept, but have no project-wide table for a row to open. Not yet seen in the app: the tests drive the store and the row list, not the drawn sidebar.* A project's knowledge rows (Entities, Claims, Citations, the hermeneutic rows and the like) appear only when they hold at least one item, with counts from the engine, and a row appears live when its first item arrives.
- `sidebar.knowledge.bottom-bar-toggle` **[PARTIAL]** (#5413) *Built 2026-10-05: `SidebarKnowledgeRowsToggle` in `SidebarBottomToolbar`, its setting one `@AppStorage` key (`SidebarKnowledgeRows.shownKey`, on by default), drawn only when `SidebarKnowledgeRows.toggleIsShown` finds an open project with a non-empty row; `fichero/Tests/Unit/general/Views/Sidebar/SidebarKnowledgeRowsTests.swift` proves hide/show, the setting surviving a fresh read, and the control's absence. Not yet seen in the app.* One control in the sidebar's bottom bar hides or shows the non-empty knowledge rows. It remembers its setting and is shown only when at least one project has such a row. *Retired 2026-11-13 (owner, `sidebar.bar.plus-minus-filter-overflow`): the separate control goes; Entities and Claims is a toggle of the Filter field's menu (`sidebar.bar.filter-menu-toggles-what-the-sidebar-shows`), kept per window.*

### The bottom bar (owner 2026-11-13; Mac first)

> Xcode's navigator bar is the pattern: **+**, **−**, a **Filter** field whose line-in-circle glyph
> opens a menu, and nothing else; ⋯ only when the bar overflows. The bar's material, height and
> insets are `panes-workspaces.md`'s `panes.chrome.mac-bars-like-xcode`; the field is the one
> component every view's bar uses (`panes.bar.filter-field-like-xcode`). Names in Finder's order
> and long names cut in the middle are `library.sort.names-in-finder-order` and
> `library.names.truncate-in-the-middle` (#6571, on their own branch) and are not repeated here.

- `sidebar.bar.plus-minus-filter-overflow` — **[GAP]** (#4121, #5413; owner 2026-11-13) app, macOS. The sidebar's bottom bar is, left to right, **+** (the one `AddItemMenu`), **−** (remove the selection), the **Filter** field (`sidebar.bar.filter-field-like-xcode`), and at the far right **⋯** only when more is offered than fits; nothing else. The separate Entities toggle (`SidebarKnowledgeRowsToggle`, #5413) and the "?" glyph go: what the toggle switched is an entry of the Filter field's menu, and the help the "?" gave is each control's tooltip; the "?" fallback badge on rows (`SidebarRowLabelCore`) gives way to the row kind's own icon (ruling 2, `panes-workspaces.md` H). *Built:* + − and the field, laid out as Xcode's navigator 2026-11-11 (`SidebarBottomToolbar`); the knowledge toggle still sits between − and the field. *Not built:* the field's menu, the ⋯, the removal. *Tests:* `SidebarBottomToolbarTests` (to write: the bar's controls in order as a pure table; no Entities button; ⋯ only on overflow).
- `sidebar.bar.filter-field-like-xcode` — **[GAP]** (#4061; owner 2026-11-13) app. The field is `panes.bar.filter-field-like-xcode`'s: a rounded field with the filter glyph and its menu chevron on the left (today a magnifier, `SidebarBottomToolbar.filterField`), the typed text filtering rows by name as today (#4061), never hiding the selection (`read.filter-never-hides-selection`), a clear button only while there is text. *Tests:* `SidebarBottomToolbarTests` (to write: the field is the shared component; the clear button's presence).
- `sidebar.bar.filter-menu-toggles-what-the-sidebar-shows` — **[GAP]** (#5413; owner 2026-11-13) app. The chevron's menu is a list of check-marked toggles of what the sidebar lists, in this order: **Entities and Claims** (the knowledge rows; on by default), **Sources** (folders only: every project's folder tree with no page or image rows, so a long project reads as its folders; a PDF split into pages is shown as a folder is and its pages are hidden, ruling 3; on by default), **Workflows**, **Models**, **Hosts** (the shared Macs, today the sharing rows of `SharedMachineSections`, AND the compute hosts a project reaches, the clusters of `compute/`, ruling 5; on by default), and the **Metadata** section (`sidebar.bar.metadata-section`; off by default). A toggle off removes its rows from every project in the window, the always-there project's top section included. A toggle whose rows would be empty is dimmed with "None in this project" as its help, never hidden (the rule of `layers.toggle.empty-layer-says-so`, and what `sidebar.knowledge.rows-only-when-non-empty` already does for the rows). *Tests:* `SidebarFilterMenuTests` (to write: the entries and their order; each toggle's effect on the row list as a pure function; a dimmed empty toggle).
- `sidebar.bar.toggles-are-per-window` — **[GAP]** (#5413; owner 2026-11-13) app. The toggles are kept per window (scene storage), not per app: two windows on one project can list different sections; a new window starts from the defaults, a restored window from what it had (`source.panes.what-is-restored`); the typed filter text is not restored. *Tests:* `SidebarFilterMenuTests` (to write: two scenes, two states; a new scene's defaults).
- `sidebar.bar.metadata-section` — **[GAP]** (#5413; owner 2026-11-13, ruling 4 in `panes-workspaces.md` H: the proposed rows are kept) app and engine. Proposed: a **Metadata** section listing the project's facets as rows a click filters the Items by: **Document Types** (the registry's types, each with its count), **Tags**, **Languages** (from the cascade), **Dates** (by year, from the catalogue's normalised dates). People and places are not here: they are Entities. Each row is a saved filter, not a folder: clicking it shows the Items pane filtered (`panes.bar.one-filter-and-options-component`), the same as choosing that facet in the Items Filter field; the counts come from the engine (`GET /api/stats/facets`, beside `/api/stats/knowledge`) and refresh on the change stream. *Built:* nothing. *Tests:* `test_stats_facets.py` (to write), `SidebarMetadataRowsTests` (to write).

### Names after the cold-launch test (maintainer, 2026-10-10)

The project that is always there (on disk `global.fichero`, no data moves) has **no name** in the
UI (ruled final later the same day, replacing "My Project"; "Local", "Desk", "My Library" and "My
Project" were all tried and retired). The sidebar's top section has no heading row and shows its own
items directly, flush left: **Sources**, **Workflows**, **Models**, and its Entities/Claims rows only
when they hold something. Below, a section headed **Projects** lists the projects a person set up,
each expandable as before. Mail and Finder are the pattern: yours at the top, named collections
below. It cannot be closed, deleted or renamed; it has no row to do any of that from. The
window's panes are one word each: **Projects** (the sidebar) · **Items** (the middle pane, was
Library; its modes read Items › Icons / List / Columns / Canvas) · **Source** (the preview/editor
pane, was Preview) · **Inspector** · **Reader** · **Segments**. "Item List", "Browser", "Source
View" and "Source Preview" were rejected (the pane also edits, and "view source" reads as code).
People read Project, never Library (ruled 2026-10-03, restated 2026-10-10). Only the words people
read change; types, files and identifiers keep their names.

- `library.always-there-project.no-name` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* the always-there project has no name anywhere a person reads: `AlwaysThereProject.displayName` is empty for its package whatever was saved for it before (Local, Global, My Library, Desk, My Project, or a rename under the earlier ruling), so the sidebar, the window title and setup name nothing, and the registry's Open Recent list leaves it out (it is always open). "My Project" is gone from the always-there project's paths. The engine does not name it. Pinned by `fichero/Tests/Unit/general/App/ProjectNamingTests.swift` (`testTheAlwaysThereProjectHasNoName`). The breadcrumb, the window title, Activity and Run Workflow each handle the empty name (the four behaviours after `sidebar.projects-heading`).
- `library.always-there-project.never-renamed` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* the always-there project is never renamed: `LibraryManager.renameLibrary` refuses its id, and `ProjectRowMenuOffers` offers it no Rename (it has no row anyway). Pinned by `ProjectNamingTests.testTheAlwaysThereProjectIsNeverRenamed`.
- `sidebar.top-section-is-the-always-there-project` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* the sidebar's top section is the always-there project's own items (Sources, Workflows, Models, and its knowledge rows while non-empty) drawn at the top level with no heading row (`SidebarView.alwaysThereProjectItems`, split out by `SidebarProjectSections.split`); the rows are the same nodes with the same ids as under its old header, so selection and routing are unchanged, and ⌘A treats them as always visible. Pinned by `ProjectNamingTests.testTheTopSectionIsTheAlwaysThereProjectWithNoHeader`. *Not pinned: the drawn list. Lost with the header: dropping files onto the always-there project's root by its header row (dropping onto its Sources row still imports into Sources; between rows there is no file-drop target, as there never was for any project). Its row menu moved to the empty-area menu (`sidebar.top-section.empty-area-menu`).*
- `sidebar.projects-heading` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* below the top section, a `Section` headed **Projects** (`SidebarProjectSections.projectsHeading`, drawn in the platform's sidebar section-header style) lists every other open project in order, each a disclosure group as before; with no other project open the heading is not drawn. Pinned by `ProjectNamingTests.testTheProjectsHeadingListsTheOtherProjects`. *Not pinned: the drawn heading.*
- `sidebar.breadcrumb.no-root-for-unnamed-project` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* the breadcrumb's root is the project's name, and the always-there project has none, so its root segment is left out and the trail starts at the first folder ("Sources › File.pdf", never " › Sources › …"); `BreadcrumbBuilder` omits an empty `rootName` from both the string trail and the clickable segments. Pinned by `ProjectNamingTests.testTheBreadcrumbOmitsAnEmptyRoot`. *Not pinned: the drawn header.*
- `library.always-there-project.window-title` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* the window titles by project (`.navigationTitle` in `App/LibraryWindow.swift`); the always-there project's window reads **Fichero**, another project's its name, and a window with no project nothing (`AlwaysThereProject.windowTitle`). Pinned by `ProjectNamingTests.testTheAlwaysThereProjectsWindowIsTitledFichero`. *Not pinned: the drawn title bar.*
- `sidebar.run-workflow.no-heading-for-the-always-there-project` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* a row's Run Workflow menu groups the project's own workflows under the project's name; for the always-there project that group has no heading (an empty name is treated as no heading, not as "This Project"), below Global Defaults (`SidebarItemRow.ownWorkflowsHeading`). Pinned by `ProjectNamingTests.testRunWorkflowHasNoHeadingForTheAlwaysThereProject`. *Not pinned: the drawn menu.*
- `sidebar.top-section.empty-area-menu` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* a right-click in the sidebar's empty space (on no row) offers the always-there project's menu, what its header row offered: **New Folder** (at its root), **Import Files…**, **Edit Document Types…** and **Show in Finder** (macOS), never Rename, Close, Delete or Share; a row keeps its own menu (`AlwaysThereProjectMenu`, `SidebarView.alwaysThereProjectMenu`, through `contextMenu(forSelectionType:)` on the sidebar list). New Folder and Import are also on the bottom bar's + and Import menus. Pinned by `ProjectNamingTests.testTheEmptyAreaMenuOffersWhatTheHeaderRowDid`. *Not pinned: that the list menu appears on empty space and leaves the rows' own menus in place (needs the real window).*
- `library.always-there-project.never-closed` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* it has no row, so nothing offers to close, delete, share or rename it; `ProjectRowMenuOffers` refuses all four for it should a row ever be drawn, and File › Close Project is not offered for it. Pinned by `ProjectNamingTests`.
- `sidebar.project.opens-on-sources` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* a window that opens a project with no selection of its own selects the project's Sources folder, never Workflows; the project's store opens Sources rather than its first top-level folder (Default Workflows in the always-there project), and a project with no Sources opens its first top-level folder as before (`OpeningSelection`). Pinned by `ProjectNamingTests`. *Not pinned: the drawn highlight in the real window.*
- `sidebar.panes.one-word-names` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* the middle pane is Items (`ItemsPane.name`) in View › Show/Hide Items, the pane head, Settings, the mode label, the toolbar help and VoiceOver; the preview/editor pane reads Source (`SourcePane.name`) in View › Show/Hide Source, the View menu's Source submenu, the pane head, Settings and help; the sidebar pane is announced as Projects; App Intents' pane names are literals that match. The breadcrumb's root is the project's own name, not a pane name. Pinned by `ProjectNamingTests.testThePanesAreItemsAndSource`, `testTheBreadcrumbRootIsTheProjectsName`.
- `sidebar.project-never-library` **[PARTIAL]** (#5655) *Built 2026-10-10 (app), not yet seen:* no string a person reads in the app (the first literal of `Button`, `Text`, `Label`, `Menu`, `Section`, `Toggle`, `LabeledContent`, `ContentUnavailableView`, `.help`, `.accessibilityLabel`, `.accessibilityHint`, `.navigationTitle`, `.alert`, `.confirmationDialog`) says Library or Libraries; the one allowed phrase is "Library of Congress" (a name authority). Error and status messages built elsewhere were swept by hand. Pinned by `ProjectNamingTests.testNoUserVisibleStringSaysLibrary`.

## Future (ideas, not scheduled)
- (#1380) Mail-style sidebar: counts, multi-select combined view, favorites section, smart All groups
- (#1868) SF Symbol icon and color per library, folder and list in the sidebar
- (#1951) Status redesign (updated/bold-unread, no green check) and consistent light-blue selection
- (#4095) Adopt native .badge() for sidebar row counts instead of hand-drawn chrome; no .badge( usage in Views/Sidebar today; cosmetic.
- (#4169) Double-click opens per the new-tab/new-window setting; Command-double-click inverts it, for every object everywhere.
- (#4260) Audit sidebar, list, keyboard and menu behaviour against NetNewsWire as a reference implementation.
- (#3703) Entity drag to associate/merge/export: engine export landed (PR #3722) and entity rows are draggable, but drop-to-merge/associate is app-wide drag and drop vision

## Triaged from the August restart handoff (2026-10-17)
- `create.drop.folder-or-image-imports-like-the-menu` — **[GAP]** (#4520) a folder or an image dropped on the sidebar (Inbox or the library icon) imports exactly as the menu import does and does not pop back. Test: a new ExternalFileDropLoaderTests.swift in `fichero/Tests/Unit/` (to write).
- `read.import-updates-one-row-once` — **[GAP]** (#4522) importing one file updates one row, once: not a whole-sidebar redraw, and not twice (a direct reload plus a change-stream reload). Test: a new SidebarImportRefreshTests.swift in `fichero/Tests/Unit/` (to write).
- `sidebar.accessibility-identifiers` — **[PARTIAL]** (#5763) *Built 2026-10-17 (app), not yet seen:* every row, project header, the Projects heading and the list carry a stable identifier, spelled once in `SidebarAccessibilityID` (`sidebar.row.<id>`, `sidebar.project.<libraryId>`, `sidebar.projectsHeading`, `sidebar.trash.<libraryId>`, `sidebar.models.<libraryId>`, `sidebar.list`). *Test:* `SidebarAccessibilityIDTests` (the strings, and that each view applies its identifier). *Not built:* the XCUITest that finds the Sources row.
- `read.leaf.no-chevron` — **[PARTIAL]** (#5764) *Built 2026-10-17 (model pinned, not yet seen):* a leaf row (a page, an image, Trash, a model) is not a disclosure row and lines up with Sources and Workflows. `SidebarItem.isExpandable` is false for a page or image whatever its child count says; Trash and each trained model are plain rows. *Test:* `SidebarLeafRowsTests` (a multi-page PDF opens, an empty folder or childless PDF does not, and the invisible slot is built only for a row that opens). *Not built:* that the closed folder's slot draws one chevron and a leaf lines up with Sources cannot be seen from the model; needs a screen.
- `sidebar.top-section.order` — **[PARTIAL]** (#5655, #5764) each project's nodes after its items are knowledge rows, Models, Trash last (`SidebarProjectNode.order`), the always-there project's top section included. *Test:* `SidebarLeafRowsTests.nodeOrder`.
