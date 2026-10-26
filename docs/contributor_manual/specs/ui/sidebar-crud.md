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
- `delete.never-deletes-the-parent` — **[PARTIAL]** (#6175; owner bug 2026-10-26, data loss) deleting an item in the sidebar removes exactly the selected items and their descendants and NEVER an ancestor or a sibling. The engine never deletes upward, pinned through the call the sidebar makes (`fichero-server/tests/unit/models/test_deleting_a_child_leaves_ancestors_and_siblings_6175.py`); the parent was lost in the app, where the selection moved to the parent after a delete and the next delete gesture acted on it (fixed by `delete.after-delete-selection-is-never-a-delete-target`, Swift uncompiled; the owner's device check is still owed).
- `delete.snapshot-so-undo-restores` — **[GAP]** (#6175; owner ask 2026-10-26) every delete first records a snapshot (the items, their place, order and descendants) in the same action, so Undo (`ui/undo-everywhere.md`) and the Trash (`delete.trash-browsable`) restore them exactly where they were; the snapshot is kept until the person purges it.
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
- `delete.after-delete-selection-is-never-a-delete-target` — **[PARTIAL]** (built, Swift uncompiled: `DeleteStateManager.inheritedSelectionId` is set where `performDelete` moves the selection and cleared by the next selection commit; `sidebarDeleteTargets` leaves it out of Delete, Backspace, Edit > Delete and the "-" count; Cancel is the Return default; not yet from the ROWS AS DRAWN rather than `childrenCache`, and a re-click of the already selected row does not clear it, which fails safe; the "-" button stays enabled on that row and does nothing; a right-click on a row is an explicit gesture and is the exception: its menu deletes the clicked row) (#6175; Opus review `delete-parent-root-cause-2026-10-26.md`) after a delete the selection moves to the next sibling, else the previous, else the parent (the Finder rule, from the ROWS AS DRAWN, not from a cache that may be empty), and that selection is only a place to look: Delete, Backspace, the "-" button and Edit > Delete do nothing to it until the person selects it again by a fresh click; Return never confirms a delete by default (Cancel is the default). *Test:* `SidebarDeleteTests.testDeletingAnOnlyChildNeverMakesTheParentTheNextDeleteTarget`.
- `delete.what-is-shown-selected-is-what-is-deleted` — **[PARTIAL]** (built, Swift uncompiled; the diverging value is not proven without a run: Edit > Delete takes the focused Items list's selection when that pane has focus (`FocusedItemVerbs.target`), while the sidebar still draws its own row selected in grey; built so the person sees it before it happens: the Edit menu item NAMES the one item (`Delete “Parent”`), and both confirmations' messages already name it; not built: the Items list's title naming it (its file is over the lint length), the sidebar's batch confirmation listing names, a plain focus (not a selection) drawn for an app-made selection, and the run of the test below on a Mac) (#6175; owner 2026-10-26: the sidebar showed the CHILD selected while the app's real selection was the PARENT, so a delete took the parent) the rows drawn as selected in the sidebar, the selection the app holds and the set a delete acts on are ONE value: a delete takes exactly the rows the person sees selected, never a row the app selected on its own (the Preview's subject, an inherited parent, the row after a delete). Where the app moves the selection itself, the highlight moves with it, and an app-made selection is drawn as a plain focus, not as a selection a delete will use. The confirm sheet lists the rows it will delete, by name. *Test:* `SidebarDeleteTests.testTheRowsDrawnSelectedAreExactlyTheRowsDeleted` (select a child while the Preview shows another row; the delete set equals the drawn selection), run on a Mac (the Air/M4), not only compiled.
- `delete.multi-is-one-undo-step` — **[PARTIAL]** (built, Swift uncompiled: `SidebarActions.performDelete(_:)` runs several documents of one library through `UndoableChange.batch`, named "Move 3 Items to Trash", one refresh, nothing selected after; the confirmation dialog calls it once; not tested end to end: a stubbed-engine test that one Cmd-Z restores all) (#6175, #4696) a delete of several items is ONE undoable batch and one refresh: one Cmd-Z restores all of them. *Test:* `SidebarDeleteTests.testBatchDeleteIsOneUndoStep`.
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
- `dup.deep-tree-fits-the-memory-cap` — **[OK]** (#5100) duplicating a 1,050-deep tree completes inside DuckDB's 1.5 GB cap. *Built: measured, the memory was linear in rows but 1.35 MB a row from `INSERT … ON CONFLICT` held until commit (duckdb#26830); `Database.save` plain-INSERTs a new row (0.013 MB); the cap is unchanged. `test_new_rows_in_a_transaction_stay_small.py`, `test_duplicate_survives_trees_deeper_than_the_recursion_limit`.*
- `sidebar.expand-is-instant` — **[GAP]** (#5277) expanding a sidebar folder draws its children at once from a prefetched light listing and publishes per folder, not as a store-wide re-render (the one-level look-ahead landed in 3c696d7aa; the light listing and per-folder publish remain).
- `sidebar.one-selection-one-fetch` — **[BROKEN]** (#4995) one sidebar selection fetches the document, its children and thumbnails once (loadChildren and document fetch single-flight, handleSelection once); the four-builds half landed in 75ddc9d03.
- `sidebar.project.click-selects-and-inspects` **[PARTIAL]** (#5422) *Built 2026-10-04: the row's tap writes the project through `SidebarSelectionState.selectProject`; the Inspector routes a project selection (with nothing picked in the Library pane since) to `ProjectInspector` (name, location, counts from `GET /api/stats`, the saved recipe with Set Up…, sharing), a project click clears the pane's pick like a folder click (retiring #4299's carve-out), and the row's platter has one `listRowBackground` writer; `fichero/Tests/Unit/general/Views/Shell/ProjectRowInspectsTests.swift`. Not yet seen in the app: the test does not drive the real click or the drawn highlight.* Clicking a project row in the sidebar shows the row selected and switches the Inspector to the project itself: its name, location, recipe and Set Up…, sharing and counts. Tested through the real selection store.
- `sidebar.option-click-expands-everything` **[BROKEN]** (#5023): Option-clicking a library's disclosure triangle expands every folder and shows their children, visible rows first, without freezing, and no row is left with a spinner in place of its icon.
- `sidebar.project.has-a-sources-folder` **[PARTIAL]** (#5413) *Engine half built 2026-10-05: `importers/sources_folder.py` is the one rule. The library open (`DatabaseManager.get_database`, which also serves `POST /api/library`) gives a project its Sources folder once, reusing a live top-level folder already named Sources, and never re-makes one a person deleted; every import route that names no folder (`/api/ingest/file`, `/files`, `/folder`, `/xlsx`, `/api/documents/import`, `/import-batch`, the browser save) lands in it, making it again if it was deleted. Nothing already in a project moves. The global library (the always-there project) has one too (maintainer, 2026-10-10: a first launch shows its Sources). `fichero-server/tests/unit/importers/test_sources_folder.py`. App half 2026-10-05: nothing to build; Sources is an ordinary folder in the project's tree and the sidebar draws it like any other (no app code names it). Not yet seen in the app.* Every project has a folder named Sources, where new material lands when an import names no other folder. New projects are created with it and an existing project gets one when it next opens; nothing already in the project moves. The engine creates and chooses the folder; the app only shows it. Tested through the real engine route.
- `sidebar.knowledge.rows-only-when-non-empty` **[PARTIAL]** (#5413) *Engine half built 2026-10-05: `GET /api/stats/knowledge` returns each row's count (entities not merged away, claims, citations, references, interpretations, frameworks, patterns), one `COUNT(*)` each, to be asked again on `entity.*`, `claim.*`, `citation.*`, `reference.*` and `interpretation.*` change events; `fichero-server/tests/unit/api/test_knowledge_row_counts.py`. App half built 2026-10-05: one `KnowledgeRowCountsStore` per project reads the route through the generated client, is registered with the project's change stream, and on an event of one kind re-reads the route and writes only that kind's count, in place; `SidebarKnowledgeRowsNode` draws a row only when its count is above 0. `fichero/Tests/Unit/general/Views/Sidebar/SidebarKnowledgeRowsTests.swift`. Only Entities and Claims have a row today: Citations, References and the hermeneutic counts are read and kept, but have no project-wide table for a row to open. Not yet seen in the app: the tests drive the store and the row list, not the drawn sidebar.* A project's knowledge rows (Entities, Claims, Citations, the hermeneutic rows and the like) appear only when they hold at least one item, with counts from the engine, and a row appears live when its first item arrives.
- `sidebar.knowledge.bottom-bar-toggle` **[PARTIAL]** (#5413) *Built 2026-10-05: `SidebarKnowledgeRowsToggle` in `SidebarBottomToolbar`, its setting one `@AppStorage` key (`SidebarKnowledgeRows.shownKey`, on by default), drawn only when `SidebarKnowledgeRows.toggleIsShown` finds an open project with a non-empty row; `fichero/Tests/Unit/general/Views/Sidebar/SidebarKnowledgeRowsTests.swift` proves hide/show, the setting surviving a fresh read, and the control's absence. Not yet seen in the app.* One control in the sidebar's bottom bar hides or shows the non-empty knowledge rows. It remembers its setting and is shown only when at least one project has such a row.

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
