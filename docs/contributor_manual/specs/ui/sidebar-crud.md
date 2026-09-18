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
- `move.no-cycle` — **[OK]** `SidebarMovePolicy.isValidTarget`
  (`SidebarItemRow+Helpers.swift:8-25`) walks the target's ancestor chain and refuses when
  the source appears in it (self, direct child, or deep descendant), bounded against a
  malformed cyclic chain. Pinned: `SidebarMovePolicyTests` (client); the backend
  independently rejects the same cases —
  `TestDocumentMoveAction.test_move_into_self_rejected`,
  `TestDocumentMoveAction.test_move_into_descendant_rejected`
  (`fichero-server/tests/unit/api/test_document_actions.py`).

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
