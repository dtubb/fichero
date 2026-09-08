# Sidebar CRUD — Design Spec

> Design-led spec (Testing Constitution). The design lead owns this intent; tests
> enforce it; code makes the tests pass. One line per behavior; each maps to a
> pinning test cited by name in the test's docstring.
> Status: DRAFT — awaiting design-lead (Daniel) approval before tests/code.

## Intent (the design)

The sidebar IS the library's file tree. Users create, rename, move, and delete
folders and items directly in it, and the tree **and the selection** stay coherent
through every operation and through the live change-stream rebuilds. No operation on
a child ever mutates or mis-selects an ancestor.

## Behaviors (each → one pinning test)

### Create
- `create.folder.lands-under-context` — a new folder is created under the
  current folder (or at root if none), is selected, and enters rename mode.
- `create.item.same-rule` — a new item follows the same placement + select + rename rule.

### Read
- `read.tree.shows-all` — every non-deleted child of an expanded folder is shown.
- `read.expand.persists` — expand/collapse state and selection survive a
  change-stream rebuild (no flked selection, no collapse on unrelated events).

### Update — rename
- `rename.in-place` — rename commits on Return, cancels on Esc.
- `rename.rejects-empty` — an empty name is rejected; the row keeps its old name.

### Update — move / reparent
- `move.onto-folder-reparents` — dragging a folder/item onto a folder reparents it.
- `move.onto-nonfolder-rejected` — a drop onto a leaf is rejected, no-op.
- `move.no-cycle` — a folder cannot be dropped into its own descendant.

### Delete — **FIRST TO PIN (this PR)**
- `delete.subtree-only` — deleting a folder/item soft-deletes ONLY that item and its
  descendants; **no ancestor is ever deleted or modified.** (Backend already correct —
  `_descendant_document_ids` descends only; this pins it against regression.)
- `delete.selection-safe` — after a delete, selection moves deterministically to a
  safe EXISTING target (the parent folder; else nearest sibling; else clears). The
  just-deleted row is **never** resurrected into the selection nor routed to — so a
  child delete never lands you on / re-selects its parent by side effect.
- `delete.multi` — a multi-select delete removes exactly the selected subtrees;
  untouched rows keep referential identity (no whole-tree flash).

## First worked example (this PR — the delete behaviors)

Root cause (scoped): `sidebarResilientSelection`
(`fichero/…/Sidebar/Sections/SidebarView+ViewComponents.swift`) treats a *just-deleted*
row as "momentarily missing" (indistinguishable from a lazy-rebuild gap) and re-adds
it to the selection, which then routes to the parent. Fix: a dedicated
`recentlyDeletedDocumentIds` signal on `DocumentStore` (set in `removeDocuments`), so
the resilience filter drops a genuinely-deleted row instead of resurrecting it.

Tests that pin the two delete behaviors:
1. **Unit (pure):** `sidebarResilientSelection` — a dropped id that is recently-deleted
   is NOT resurrected; a dropped id that is merely a rebuild gap IS kept. (`delete.selection-safe`)
2. **Store unit:** applying a `document.deleted` change drops those ids and records
   them as deleted, not merely "changed". (`delete.subtree-only` local half)
3. **UX (broad, Decision 9):** delete a child folder in the sidebar → assert the
   PARENT row still exists and is not the resurrected selection. (`delete.selection-safe`
   end-to-end)

Everything above the Delete section is the larger design, pinned in later waves —
NOT this PR.
