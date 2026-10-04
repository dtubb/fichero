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

### Delete
- `delete.subtree-only` — **[PARTIAL]** (#4697) deleting a folder cascades to exactly its
  descendants — proven by `TestDeleteDocument.test_delete_soft_deletes_children`
  (`fichero-server/tests/unit/api/test_routes_documents.py`), which asserts both the parent
  AND child end up soft-deleted from one parent-delete call. The INVERSE direction this
  behavior also claims — deleting a CHILD never touches an ancestor — is not directly
  asserted by any test (the algorithm only ever descends, so it's structurally unlikely to
  regress, but "unlikely by construction" isn't "pinned").
- `delete.selection-safe` — **[PARTIAL]** (#4805, #4697) the "never resurrected" half is real and
  tested: `SidebarView.droppedRowIsMomentarilyMissing` treats a just-deleted row as gone, not
  a momentary rebuild gap, so it can't be resurrected into the selection. Pinned:
  `SidebarSelectionResilienceTests.testRecentlyDeletedRowIsNotResurrected`. The "moves
  deterministically to a safe target — parent, else sibling, else clears" half is FALSE as
  written: `SidebarActions.swift:177` always clears (`selectedItemId = nil`); there is no
  parent/sibling fallback in the code today. Decided (manager, under the standing Finder-like
  principle): the spec's claim stands and the code is the bug — selection moves to the next
  sibling, else the previous, else the parent, else clears. Tracked by #4805.
- `delete.multi` — **[BROKEN]** (#4696) "no whole-tree flash" does not hold while #4696's H2
  stands: `SidebarActions.swift:224` (and `:85`) call `documentStore.refresh()`
  unconditionally per item in a batch-delete loop — a wholesale `loadCollections` per
  deleted item, not the one-splice-then-one-rebuild the behavior promises.
- `delete.trash-browsable` — **[GAP]** (#2077) a deleted item is reachable in a browsable Trash
  surface (restore, or purge permanently) and soft-delete extends beyond Document to claim/
  entity/annotation/note/workflow. Verified: the backend routes exist for Document only
  (`GET /trash`, `POST /{doc_id}/restore`, `DELETE /{doc_id}/purge` — `documents.py:739,1585,
  1601`); no Swift Trash view exists (`grep -rl "TrashView" fichero/fichero/Views` = empty) and
  no other type has the soft-delete/restore/purge pattern. This is the FRONTEND-and-other-types
  remainder `delete.subtree-only`/`.selection-safe`/`.multi` above don't cover — those pin the
  Document-delete MECHANICS; this pins whether a deleted item can be found and undone again.

### Legacy milestone fold — three issues redirected from "UX - Library & Reading Surface"

While folding `library-view-modes.md`'s pass 2, three sidebar-structure issues from that
legacy milestone were re-read against this spec instead — sidebar row mechanics and the
sidebar's own code health, not a Library view-mode question:

- `sidebar.drag-session-consistent-across-row` — **[GAP]** (#713) dragging a row's icon/name
  versus dragging elsewhere on the row body should produce the SAME drag session inside a
  `DisclosureGroup` — today they diverge. Not verified as built.
- `sidebar.code-structure-consolidated` — **[GAP]** (#585) `SidebarItemRow` should split and
  the sidebar's several state managers should consolidate — a code-health ask, not a
  user-facing behavior, kept here as a GAP so it stays tracked rather than lost when its
  milestone folds.
- `sidebar.accessibility-pass` — **[GAP]** (#4164, #584) the sidebar has zero VoiceOver/accessibility
  coverage today (issue's own claim, not independently re-verified this pass).

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

## Triaged from the backlog (2026-10-04)
- `sidebar.drag-identity-edges` — **[GAP]** (#4530) a foreign plain-text drag is not blamed as internal, a user folder named fichero-drag-* is not swallowed, and canonicalLibraryKey matching is case-insensitive.
- `sidebar.drop-on-content-pane-silent` — **[GAP]** (#4551) releasing an in-app library drag on the content pane is a silent no-op, never a modal Import Error (message still in ContentView+ActionsImport.swift).
- `onboarding.minimal-local-first` — **[GAP]** (#2719) First run uses a default library, asks only needed permissions, and every step is optional.
- `launch.opens-global-inbox` — **[GAP]** (#4017) Mac launch opens what the app had open straight into the main window with no library prompt or spinner; onboarding is a sheet.
- `launch.no-splash-ever` — **[GAP]** (#4261) The New/Open Library splash never appears for a user with saved libraries; connection/auth state shows inline in the sidebar.
- `launch.open-libraries-consistent-across-devices` — **[GAP]** (#2498) the sidebar on iOS/iPad lists the same open libraries the engine has open for the Mac, instead of only one.
- `sidebar.no-bottom-entity-activity-workflow-sections` — **[GAP]** (#4102) the sidebar no longer renders the bottom Activity/Entities/Workflows/Automations sections; libraries are listed as their own separate section.
- `launch.prunes-rejected-saved-library` — **[GAP]** (#4239) a saved library path the engine definitively rejects (403 roots) is pruned from the saved list and never retried in a session; UI-test libraries never persist into real preferences.
- `sidebar.row-heights-agree` — **[GAP]** (#4476) library rows and item rows reach the same height by one mechanism (today 2pt apart via two), per the 2026-08-02 decision document.
- `read.expand.streams-in-place-with-trailing-spinner` — **[GAP]** (#4564) opening a folder adds children in place with no entry animation, while a spinner shows at the trailing edge of the folder's own row (today it replaces the leading icon, SidebarRowLabelCore.swift:104).
- `read.keyboard.arrow-descends-into-library-header` — **[GAP]** (#4566) down and right arrow move from a selected library header into its children, without swallowing all arrows via onMoveCommand (#560).
- `read.keyboard.option-arrow-expands-collapses-subtree` — **[GAP]** (#4567) option-right expands and option-left collapses a row and all descendants, for every selected row (click versions exist: sidebarExpandSubtree/sidebarCollapseSubtree, keyboard not bound).
- `read.selection.modifier-click-on-any-row-name` — **[GAP]** (#4571) cmd/shift/option-click on the NAME extends selection for page (leaf) rows and the library header too, and shift-click above the anchor ranges upward; disclosure rows are fixed (22424f614).
- `sidebar.vocabulary-collection` — **[GAP]** (#3752) the user-visible and wire vocabulary is 'collection' everywhere; backend still serves api/routes/document/folders.py (folders.py is only a shim) with the folders tag and docType .folder.
- `sidebar.library-section-stable-placement` — **[GAP]** (#3336) the Library section (and any additional open libraries) renders in one stable position inside the sidebar column across launches and window states.
- `sidebar.ipad-rotation-does-not-rebuild` — **[GAP]** (#2408) rotating an iPad does not re-run SidebarItemBuilder.build or rebuild the split view; verify with the InteractionProfile log on a device, then fix.
- `sidebar.click-path-does-no-full-tree-walks` — **[PARTIAL]** (#4228) a sidebar click does no per-body full-forest walks (cached buckets, XOR signature, dictionary lookups landed in 9568619fb, d35a69f49); the window open/close beachball is not re-measured.
- `move.no-cycle-covers-every-kind` — **[BROKEN]** (#5064) the Move to Folder menu and the drag path use one circularity check that covers every item kind, not documents only.
- `dup.deep-tree-fits-the-memory-cap` — **[BROKEN]** (#5100) duplicating a 1,050-deep tree completes inside DuckDB's 1.5 GB cap.
- `sidebar.expand-is-instant` — **[GAP]** (#5277) expanding a sidebar folder draws its children at once from a prefetched light listing and publishes per folder, not as a store-wide re-render (the one-level look-ahead landed in 3c696d7aa; the light listing and per-folder publish remain).
- `sidebar.one-selection-one-fetch` — **[BROKEN]** (#4995) one sidebar selection fetches the document, its children and thumbnails once (loadChildren and document fetch single-flight, handleSelection once); the four-builds half landed in 75ddc9d03.
- `sidebar.project.click-selects-and-inspects` **[BROKEN]** (#5422): clicking a project row in the sidebar shows the row selected and switches the Inspector to the project itself: its name, location, recipe and Set Up…, sharing and counts. Tested through the real selection store.

## Future (ideas, not scheduled)
- (#1380) Mail-style sidebar: counts, multi-select combined view, favorites section, smart All groups
- (#1868) SF Symbol icon and color per library, folder and list in the sidebar
- (#1951) Status redesign (updated/bold-unread, no green check) and consistent light-blue selection
- (#4095) Adopt native .badge() for sidebar row counts instead of hand-drawn chrome; no .badge( usage in Views/Sidebar today; cosmetic.
- (#4169) Double-click opens per the new-tab/new-window setting; Command-double-click inverts it, for every object everywhere.
- (#4260) Audit sidebar, list, keyboard and menu behaviour against NetNewsWire as a reference implementation.
- (#3703) Entity drag to associate/merge/export: engine export landed (PR #3722) and entity rows are draggable, but drop-to-merge/associate is app-wide drag and drop vision
