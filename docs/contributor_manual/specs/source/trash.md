# The Trash — Design Spec (#2077)

> Milestone: Library View
> Manual: TBD — a section of "Organising a project": where deleted items go; the Trash row at the end
> of each project; putting an item back; emptying the Trash; what happens to the people and statements
> on a page in the Trash; items a move sent there.
>
> **Status: DRAFT — 2026-10-10.** Issues: #2077 (Trash UI and soft delete for the remaining types),
> tracked with the transfer spec by #5657. Sibling of `source/moving-between-projects.md`: a move between
> projects sends its source to the source's Trash, so the Trash comes first in that spec's build order.
> Answers `delete.trash-browsable` in `ui/sidebar-crud.md`. Claims about the code are **VERIFIED** at
> `52b7b1f65` with a path, or **INFERRED**.

## Intent

Deleting in Fichero is never final by accident. A deleted item goes to its project's Trash, where a
person can see what went, when, who sent it and from where, and put it back where it was. Only Empty
Trash (or Delete Immediately on one item) removes something for good, and only after the person has
read, in words, how many items that is. Each project has its own Trash, because each project is its own
file; the always-there project (My Project) has one too.

## Ruled 2026-10-10 (the maintainer)

- **Each project has its own Trash, and so does the always-there project.** It is a row named Trash at
  the end of each project's section in the sidebar; the always-there project's is at the end of the
  top section.
- **A move between projects sends the source's items to the source's Trash** after the target's copy is
  verified (`source/moving-between-projects.md`), labelled as moved.

## What exists today (VERIFIED at `52b7b1f65`)

Paths under `fichero-server/src/fichero_server/api/routes/document/documents.py`.

- **Soft delete.** `delete_document_impl` (`:2879`, action `document.delete`) stamps `deleted_at` and
  `deleted_by` on a node and every descendant and keeps snapshots for undo; the node keeps its
  `parent_id`, so where it was is known.
- **The listing.** `GET /api/documents/trash` (`list_deleted_documents`, `:822`) lists soft-deleted
  documents, readable ones only, with paging. It lists **every** deleted row, a deleted folder's
  descendants beside the folder (INFERRED from `_list_documents(only_deleted=True)`), and carries no
  reason (such as "moved to <project>").
- **Put back.** `POST /api/documents/{doc_id}/restore` (`restore_document_subtree_impl`, `:1806`,
  action `document.restore`) clears the stamps on the node and its subtree. It does not check that the
  old parent is still live: an item whose folder was itself deleted or purged comes back under a parent
  that is not shown (VERIFIED: `restore_documents_impl`, `:2973`, sets no parent).
- **Delete for good.** `DELETE /api/documents/{doc_id}/purge` (`:1854`, `document.purge`) snapshots
  the library first and refuses if it cannot (#5070), deletes artifacts, embeddings and the knowledge
  graph rows resting on the subtree (`_cascade_delete_kg_rows`, `:1729`, each a reversible
  `MutationLog`), then the rows. There is no "empty the whole Trash" route.
- **Knowledge on trashed pages is not hidden.** No knowledge-graph read filters claims or entities by
  whether their source document is in the Trash (INFERRED: no `deleted_at` check on documents in the
  entity, claim or graph routes); soft delete leaves claims as they are.
- **Other kinds.** Only documents have soft delete, restore and purge (`ui/sidebar-crud.md`,
  `delete.trash-browsable`); workflows are mirrored as document nodes, but their `workflows` rows are
  not soft-deleted.
- **The app has no Trash view** (`ui/sidebar-crud.md`, `delete.trash-browsable`).

## Design

- **One Trash per project**, read from that project's engine through `GET /api/documents/trash`, grown
  to list **top-level** deleted items (a deleted folder once, with its count, not each descendant), each
  with: name and kind, when, by whom, where it was (its old folder's path, or "a folder now in the Trash"
  / "a folder now gone"), and why: deleted, or **moved to <project>** (from the transfer's record), or
  sent there by a move with an alias (`transfer.alias.source-aliases`).
- **Put Back** restores the item into its old folder when that folder is live; otherwise into the
  project's Sources folder, and says so. One audited action, undoable.
- **Delete Immediately** (one item) and **Empty Trash** (all) are the only permanent removals. Each asks
  in words with the count ("Delete 37 items for good? This cannot be undone.") and runs `document.purge`
  (snapshot first). Nothing empties the Trash by itself.
- **Knowledge on trashed pages** is hidden, not deleted: claims resting only on trashed pages are left
  out of graph reads, counts and search; an entity whose every mention is in the Trash is hidden with
  them; Put Back shows them again; Empty Trash prunes them through the existing cascade.

## Behaviours

- `trash.per-project` — **[PARTIAL]** (#2077) every project has its own Trash: the deleted items of that
  project's file. Built (engine): soft delete and `GET /api/documents/trash` per library. *Not built:
  the app's per-project Trash.*
- `trash.always-there-project` — **[GAP]** (#2077) the always-there project (My Project) has a Trash too,
  its row at the end of the sidebar's top section.
- `trash.lists-what-was-deleted` — **[PARTIAL]** (#2077, #5657) the Trash lists each top-level deleted
  item once, with when, by whom, from where, and why (deleted, or "moved to <project>" for items a move
  sent there). Built: the listing of every deleted row with `deleted_at`/`deleted_by`. *Not built:
  top-level items only, from where, why.*
- `trash.put-back` — **[PARTIAL]** (#2077) Put Back restores an item and its subtree into its old folder,
  or into Sources when that folder is gone or in the Trash, saying where; audited and undoable. Built:
  `document.restore`. *Not built: the fallback to Sources (today an item can come back under a hidden
  parent), the words.*
- `trash.empty` — **[PARTIAL]** (#2077) Empty Trash and Delete Immediately remove for good after the
  person confirms in words with the count; a snapshot first, refused if it cannot be made; never
  automatic. Built: `document.purge` per item with its snapshot. *Not built: emptying the whole Trash
  in one audited action, the confirmation.*
- `trash.knowledge` — **[GAP]** (#2077) claims resting only on trashed pages, and entities whose every
  mention is in the Trash, are hidden from graph reads, counts and search, not deleted; Put Back shows
  them again; emptying prunes them through `_cascade_delete_kg_rows`.
- `trash.app` — **[GAP]** (#2077) a Trash row at the end of each project's section in the sidebar shows
  the Trash in Items (List mode, columns for where from, when, by whom, why); the context menu and the
  Edit menu offer Put Back, Delete Immediately… and Empty Trash…; dragging an item out of the Trash onto
  a folder puts it back there; the row's icon shows whether the Trash is empty.
- `trash.mcp-cli` — **[PARTIAL]** (#2077) the Trash's listing, Put Back, Delete Immediately and Empty
  Trash are MCP tools and CLI commands generated from the same routes. Built: the list, restore and
  purge routes are generated (`fichero_documents_list_deleted`, `fichero_documents_restore`,
  `fichero_documents_purge`). *Not built: Empty Trash.*

## Test matrix

| Leg | Pins | File |
|---|---|---|
| Backend (pytest), to write | top-level listing with from-where and why; Put Back to Sources when the folder is gone; Empty Trash with snapshot; knowledge hidden then shown then pruned | `fichero-server/tests/unit/api/test_trash.py` |
| App (Swift Testing), to write | Trash row per project and for My Project; menu items; confirmation text carries the count | `fichero/Tests/Unit/general/Views/Sidebar/` |
| MCP / CLI | list, put back, empty through the generated tools | `fichero-mcp/tests/` |

## Open questions (each with a recommendation)

1. **A retention period** (empty items older than 30 days)? *Recommend:* no automatic emptying; the
   Trash says how much space it holds, and emptying stays a person's act. Only the maintainer can rule
   a retention period.
2. **Soft delete for workflows, notes as rows, claims and entities on their own** (#2077's remainder)?
   *Recommend:* workflows and notes join the same Trash as nodes; claims and entities deleted on their
   own keep the knowledge graph's existing undo (`MutationLog`) rather than a second Trash.
