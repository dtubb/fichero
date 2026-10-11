# Trash: I removed a thing and may want it back. Design Spec (#5243, #2077)

> Milestone: undo-trash-rollback
> Manual: TBD. "The Trash": what goes there and what does not; opening it; Put Back; what
> happens to a document's statements and search results while it is in the Trash; Empty Trash
> and what it really removes; who may empty it in a shared library; items a move to another
> project sent there.
>
> Slice 2 of the safety set. Read `undo-trash-rollback.md` first. **Status: DRAFT,
> 2026-09-20; revised 2026-10-10** with the maintainer's rulings of that day and the Trash
> findings of the adversarial review of `source/moving-between-projects.md` (#5657). This is the
> **one** Trash spec: a second draft written on 2026-10-10 (`source/trash.md`) was folded in here
> and removed. Issues: #5243 (this slice), #2077 (the Trash UI and soft delete for the other
> kinds), #5657 (moves between projects, which send their source here). Claims about the code
> are VERIFIED (line given), TRACED or INFERRED. Nothing was run. Engine paths are relative to
> the engine's source folder; app paths are given in full.

## Intent

Each project has its own Trash, the always-there project included, as a row at the end of that
project's section of the sidebar. Deleting a thing a person can name sends it there. It can be
opened, looked through, and things can be put back where they came from, today or next year.
While a thing is in the Trash it is out of the way everywhere: lists, search, the knowledge
graph, exports. Nothing is destroyed until someone chooses Empty Trash or Delete Permanently, is
told exactly what will go, and says yes.

This is the Trash the app already promises in its delete dialog and does not have.

## Ruled 2026-10-10 (the maintainer)

- **Each project has its own Trash, and so does the always-there project.** A project is one
  package and one database, so its Trash is the deleted rows of that file. The Trash is a row
  named Trash at the end of each project's section in the sidebar; the always-there project's is
  at the end of the top section.
- **A move between projects sends the source's items to the source's Trash**, after the
  target's copy is verified (`source/moving-between-projects.md`), labelled as moved.
- **Nothing empties the Trash by itself** (already `safety.trash.never-empties-itself`).

## Prior art

- **Finder and Mail.** Delete is instant and unconfirmed because it is reversible; the Trash is
  a place you can open; Put Back returns a thing to where it was; only emptying asks. We adopt
  all four.
- **Shared drives** (Google Drive, Dropbox). In a shared space, people see deleted things they
  had access to; only an owner or manager empties for everyone. We adopt that.
- **Archival practice.** Deaccession is deliberate, recorded, and names who and why. Emptying
  the Trash is our deaccession: a recorded, confirmed step that leaves a note behind.
- **What we do differently.** A deleted source's derived knowledge (statements, entities,
  search entries) goes out of view WITH it and comes back WITH it, worked out when reading, so
  nothing is rewritten on the way in or the way out.

## What exists

| What | State | Evidence |
| --- | --- | --- |
| Documents and folders are soft-deleted with who and when, whole subtree | built | VERIFIED `api/routes/document/documents.py:2501-2524` |
| Engine routes to list the Trash, restore, and purge | built | VERIFIED by survey (`document.list_trash`, `document.restore`, `document.purge`) |
| Locked nodes (the default workflows container) refuse deletion loudly | built | VERIFIED same file `:2506-2509` |
| The delete dialog promises "you can put it back later" | built | VERIFIED `fichero/fichero/Views/Sidebar/Sections/SidebarDeleteConfirmation.swift:8-55` |
| Any Trash screen, Put Back or Empty in the app | **not built** | VERIFIED: no app code calls the Trash list or purge; the one restore call is an unreachable undo closure at `fichero/fichero/Views/Sidebar/Components/SidebarActions.swift:216` |
| The Library pane deletes through the same action with no way back at all | built, and wrong | VERIFIED by survey `fichero/fichero/Views/Library/LibraryView+DeleteActions.swift:90-120` |
| A trashed document's statements, entities and search vectors stay live | wrong | VERIFIED by survey: the cascade and the vector removal run only at purge (`documents.py:2565`, `:2570`) |
| Trashed documents are left out of exports | built for the documents an export writes (6cf0b0dc3): `_collect_documents` keeps live, non-workflow documents only; pinned by `fichero-server/tests/unit/core/test_export_service.py` | the lookup maps at `export_service.py:132`, `:253` still read every row; the other whole-library reads are listed in #5406 |
| Stored original files are ever deleted | never, not even at purge | VERIFIED by survey: storage has no delete call |
| Purge computes snapshots for a reversal, then discards them | wrong | VERIFIED by survey `documents.py:2528-2560`, `:3429-3456` |
| A deleted run is marked and nothing reads the mark; the route is outside the record | #4960. True on this branch. **The engine half is fixed on the integration branch (0bcb71c8e, after this branch was cut):** deleting a run is one recorded action (single, bulk, clear failed); the run row is soft-deleted; its events are KEPT and hidden when read; a test proves that flipping the mark back restores both. The tracker's "workflow deleted" event now has no caller | this branch: VERIFIED by survey `workflows/activity_store.py:1297`, `:1311-1354`; the fix: commit confirmed to exist, its content as reported by the manager, not read here |
| Every other kind (notes, annotations, entities, statements, workflows, conversations, saved searches, canvas items, references) | hard-deleted; comes back only by reversing the recorded step | VERIFIED by survey |
| Deleting a folder of workflows, searches or conversations with its contents | hard delete, no record, no way back | VERIFIED by survey `api/routes/document/folders.py:388-422` |
| Confirmation before delete | inconsistent: the same kind confirms on one surface and not another; deleting a run never confirms | VERIFIED by survey |
| Who may delete, restore, purge | one "may write" bit; who deleted is stored and never consulted | VERIFIED by survey `security/authz.py:255-260` |
| The Trash listing | every deleted row, a deleted folder's descendants beside the folder, readable rows only, paged; no reason ("moved to <project>") and no "from where" | VERIFIED at `52b7b1f65` `GET /api/documents/trash` (`list_deleted_documents`, `documents.py:822`); descendants-beside-folder INFERRED from `_list_documents(only_deleted=True)` |
| Put Back into a folder that is itself gone or in the Trash | the item comes back under a parent that is not shown | VERIFIED at `52b7b1f65`: `restore_documents_impl` (`documents.py:2973`) sets no parent; `restore_document_subtree_impl` (`:1806`) clears the stamps only |
| Empty the whole Trash in one step | no route; purge is per item (`DELETE /{doc_id}/purge`, `:1854`), snapshot first (#5070) | VERIFIED at `52b7b1f65` |
| Per project | the Trash listing is per library (one database per project), the always-there project included | VERIFIED at `52b7b1f65`: the routes run on the library the request names |
| MCP and CLI | list, restore and purge are generated tools (`fichero_documents_list_deleted`, `fichero_documents_restore`, `fichero_documents_purge`); no Empty Trash | VERIFIED: the generated MCP tool list |

## Behaviours

### A. What goes to the Trash

- `safety.trash.the-rule` — **[GAP]** (#5243) a thing goes to the Trash when it is deleted if **a person can name
  it and would go looking for it**. Everything else is undo only. The kinds:

  | Goes to the Trash | Undo only |
  | --- | --- |
  | document, page, folder (of any kind) | a segment or line, a box, a reading |
  | note, reference | an annotation or highlight |
  | workflow, workflow run, batch | a workflow's node or wire |
  | saved search, conversation | a tag, a link, a rating |
  | canvas board | a note's place on a board |
  | entity | a statement; a link between statement and entity |
  | **a pass: for the maintainer** (see below) | |

  **A deleted pass.** Agreed with the source-model set: a deleted segment is undo only. It is
  soft-deleted, still resolves through its forwarding note, and comes back by undo or from its
  own history. But a **pass** (one whole segmentation or reading of a page, by a person or a
  model) is a body of work someone might go looking for. By this slice's own rule it belongs
  in the Trash. It is put to the maintainer, with that proposal.

  A statement or an annotation removed by mistake last week is still recoverable: from the
  history list (slice 1) or the thing's own history (slice 3). It simply does not clutter the
  Trash. *Data:* a field on each delete action's registration says "trash" or "undo only";
  this is the same field as `safety.undo.every-action-says-how-it-comes-back`. *Test:* a
  guardrail: every delete action declares one of the two.
- `safety.trash.one-shape-for-every-kind` — **[GAP]** (#5243) every Trash kind is soft-deleted the same way:
  when, by whom, and **with which step** (the id of the recorded step that trashed it, so a
  group deleted together is put back together). *Data:* three columns on each Trash kind's
  table; documents already have the first two. *Existing data:* rows without the columns are
  live; rows already soft-deleted (documents) keep their who and when and get no step id, so
  each is put back on its own. Nothing is rewritten. *Test:* delete one of each kind; each is
  in the Trash list with who and when.
- `safety.trash.deleted-runs-join-it` — **[GAP]** (#5243) a deleted workflow run goes to the Trash with its
  events intact; the delete is a recorded action (→ #4960; the engine half has landed on the
  integration branch as a soft delete with events kept, which is exactly what the Trash
  needs). What is left for this slice: the run appears in the Trash list; Put Back is a
  recorded action that flips the mark back; and the tracker's unused "workflow deleted" event
  is either the event the Trash listens to, or is deleted. One or the other, not left lying.
  *Existing data:* runs already marked deleted appear in the Trash on first open. *Test:*
  delete a run; the activity window no longer lists it; the Trash does; Put Back returns it
  with every event.
- `safety.trash.no-hard-delete-by-folder` — **[GAP]** (#5243) deleting a folder of workflows, searches or
  conversations is the same recorded Trash action as any folder. The unrecorded hard delete is
  removed. *Test:* delete such a folder with contents; all of it is in the Trash under one
  step; Put Back returns all of it.
- `safety.trash.one-delete-path` — **[GAP]** (#5243) the sidebar, the Library pane, the menu, the keyboard
  (Command-Delete), Shortcuts, the command line and agents all call the same action for a kind.
  *Test:* the availability leg finds one call site per kind.

### B. Out of the way while it is there

- `safety.trash.every-read-leaves-it-out` — **[GAP]** (#5406, #5243) a thing in the Trash appears in no list, count,
  search, graph, dataset, chat context or export. Reads go through one seam that leaves trashed
  rows out unless the caller asks for the Trash by name. *Why a seam:* the defect found twice
  already (→ #4960, and documents in exports) is a mark that is written and not read. *Data:*
  none new. *Test:* for each Trash kind, a behaviour test per read surface; and a guardrail
  that refuses a query on a Trash kind's table that names neither the seam nor the Trash.
- `safety.trash.dependants-go-with-their-source` — **[PARTIAL]** (#5243, #2077, #5657) hidden, not deleted: while a document is in the Trash (deleted, or sent there by a move to another project):
  its **statements** that rest only on it are out of view; a statement that rests on other
  sources too stays, and shows that one of its sources is in the Trash; its **search entries**
  are left out of results; its **segments, artifacts, annotations and notes** are out of view
  with it; an **entity** stays if a person made or curated it, or if any live source mentions
  it, and is out of view otherwise. *Data:* **nothing is stored.** "Out of view because its
  source is in the Trash" is worked out when reading, from the source's mark. So trashing is
  instant, Put Back is instant and exact, and nothing is rewritten. *Existing data:* documents
  already in a library's Trash simply take their dependants out of view from the first open of
  the new version; the release notes say so, and the app says once: "N items are in the Trash."
  *Test:* trash a document: its only-here statements vanish from the table and the graph, a
  two-source statement stays with a mark, search no longer finds its text; Put Back: all of it
  returns, row for row identical. Emptying prunes what rests only on the removed rows through the
  existing cascade (`_cascade_delete_kg_rows`, `documents.py:1729`, each a reversible
  `MutationLog`). *Built (engine, 2026-10-10):* one seam, `knowledge/trash_visibility.py`, worked
  out when reading; statements and entities are left out of the claims list, the entities list,
  the graph's neighbourhood and the knowledge search, back on Put Back, pruned on Empty Trash
  (`fichero-server/tests/unit/api/test_trash.py`, `TestKnowledgeGoesWithItsSource`); document search already leaves trashed pages
  out. *Not built:* segments, artifacts, annotations and notes; the mark on a two-source
  statement; the other graph reads (`knowledge/graph.py`); the cascade still removes a
  two-source statement on purge.
- `safety.trash.curated-work-is-never-hidden-silently` — **[GAP]** (#5243) when a delete will take
  person-curated statements or notes out of view, the short notice after the delete says how
  many. *Test:* the notice for a document with curated statements names the count.

### C. The Trash screen

- `safety.trash.one-per-project` — **[PARTIAL]** (#2077, #5243) every project has its own Trash: the
  deleted items of that project's file. The always-there project has one too. Built (engine):
  soft delete and `GET /api/documents/trash` per library, pinned by `fichero-server/tests/unit/api/test_trash.py`
  (`test_each_project_lists_only_its_own_trash`). *Not built:* the app's per-project Trash. *Test:* delete in two projects and in the always-there project; each Trash lists only
  its own.
- `safety.trash.a-place-in-the-sidebar` — **[GAP]** (#5243, #2077) the Trash is a row named Trash at the
  end of each project's section of the sidebar; the always-there project's is at the end of the
  top section; its icon shows whether that Trash is empty. It opens in the Library like any
  folder: every view mode, search within it, sorting by when deleted and by whom, List mode with
  columns for where from, when, by whom and why. Things in it can be looked at (Quick Look, the
  Source view, the Reader) and cannot be edited. The context menu and the Edit menu offer Put
  Back, Delete Permanently… and Empty Trash…; dragging an item out of the Trash onto a folder of
  the same project puts it back there. *Test:* availability; click-around.
- `safety.trash.lists-what-and-why` — **[PARTIAL]** (#2077, #5657, #5243) the Trash lists each top-level
  deleted item once (a deleted folder once, with its count, not each descendant), with when, by
  whom, where it was (its old folder's path, or "a folder now in the Trash" / "a folder now
  gone"), and why: deleted, or **moved to <project> on <date>** (from the transfer's record in
  this project), or "alias to <item>, moved to <project>" for an alias a move sent there
  (`transfer.alias.source-aliases`). Built (engine, 2026-10-10): `GET /api/documents/trash` lists each top-level item once with
  `item_count`, when, by whom, `from_where`, and `reason`/`why`; a move's soft delete passes
  `moved_to: {project, transfer_id}` to `document.delete` and the item reads "Moved to <project>
  on <date>" (`fichero-server/tests/unit/api/test_trash.py`, `TestTheListing`). A delete no longer re-stamps a descendant already
  in the Trash. *Not built:* the alias label, the app's columns.
  *Test:* a folder trashed with 40 pages lists once with "40 items"; a moved page says "moved to
  Istmina on 10 Oct 2026".
- `safety.trash.put-back` — **[PARTIAL]** (#5243, #2077) Put Back returns a thing to where it came from,
  with everything that was deleted with it, as one recorded step that can be undone. When its
  old folder is live, it goes there. When that folder is itself in the Trash, or gone for good,
  the thing goes into the project's **Sources** folder and the notice says so ("Put back in
  Sources: its folder is in the Trash."), offering to put the folder back too when it is in the
  Trash. Built (engine, 2026-10-10): `POST /api/documents/{id}/restore` restores what was deleted with
  the item (not what was trashed on its own earlier), falls back to Sources when the folder is in
  the Trash or gone, answers where in words with `folder_in_trash_id` for the offer, and is an
  undoable recorded step (`fichero-server/tests/unit/api/test_trash.py`, `TestPutBack`). *Not built:* the app's notice and offer. *Test:* each of the three cases.
- `safety.trash.put-back-a-moved-item` — **[GAP]** (#5657, #2077) Put Back on an item a move sent to
  this Trash asks which is meant: **Undo the Move** (`transfer.action.undo-move`: the item comes
  back here and the target's copy goes to the target's Trash) or **Put Back and Keep the Copy**
  (the item comes back here; the target keeps its copy; the move becomes a copy, recorded so in
  both projects). Never silently one or the other. *Test:* both choices, read back in both
  projects.
- `safety.trash.delete-is-not-confirmed` — **[GAP]** (#5243) sending a thing to the Trash does not ask first. It
  is reversible, and a short notice offers Undo. The only questions asked are before Empty
  Trash and Delete Permanently. The present dialogs for reversible deletes are removed; the
  one exception is a delete that reaches a linked original on disk, which keeps its sentence
  that the original file stays. *Test:* click-around: delete shows no dialog; the notice
  appears; Undo returns it.
- `safety.trash.it-is-the-librarys-trash` — **[GAP]** (#5243) this is not the Mac's Trash. It lives in the
  library, on whatever machine the engine runs, and looks the same from every device. No local
  file path is involved. *Test:* delete from the Mac; the iPad shows it in the Trash.

### D. Emptying

- `safety.trash.empty-says-what-will-go` — **[GAP]** (#5243) Empty Trash and Delete Permanently first show what
  will be destroyed, in numbers: documents, pages, statements and notes that rest only on them,
  and stored files with their total size, in words with the count ("Delete 37 items for good?
  This cannot be undone."). The button says "Delete Permanently". *Test:* the sheet's numbers
  equal what is then removed.
- `safety.trash.empty-names-moved-items` — **[PARTIAL]** (#5657, #2077) when the Trash holds items a move
  sent there, Empty Trash and Delete Permanently name them: "N of these were moved to <project>
  on <date>; emptying makes those moves permanent." (one line per target project). After that,
  the move can no longer be undone from either project (`transfer.action.undo-move` is refused in
  words), and the transfer's record in both projects says the move was made permanent, when and
  by whom. *Test:* move 3 pages, empty the source's Trash: the sheet names the 3 and the target;
  undo of the move is then refused in words in both windows. *Built (engine):* the preview
  `GET /api/documents/trash/empty` and the result name each target project with its count and
  sentence (`fichero-server/tests/unit/api/test_trash.py`, `TestEmptyTrash`). *Not built:* the transfer's record saying "made
  permanent" and the refusal of its undo (the transfer, #5657); the app's sheet.
- `safety.trash.empty-is-one-step` — **[OK]** (#2077, #5243) Empty Trash is one recorded action over
  everything in the Trash (today purge is one call per item), snapshot first, refused if the
  snapshot cannot be made. *Test:* empty a Trash of 50 items: one record row, one snapshot.
  Built: `POST /api/documents/trash/empty` (`document.empty_trash`), pinned by `fichero-server/tests/unit/api/test_trash.py`
  (`test_empty_is_one_recorded_step_after_one_snapshot`, `test_no_snapshot_no_empty`).
- `safety.trash.empty-removes-everything-and-only-that` — **[GAP]** (#5243) emptying removes the rows, the
  dependants that rest only on them, the search entries, the derived images, **and the stored
  original files** (today nothing ever removes those). A stored file shared by a live document
  is kept. A statement that rests on other sources too is kept, and says its evidence from the
  removed source is gone. *Data:* storage gains a delete that goes through the storage layer,
  never a file path. *Test:* empty; rows, vectors and bytes are gone; a shared file remains;
  a two-source statement remains with a stated absence.
- `safety.trash.empty-cannot-be-undone-and-says-so` — **[GAP]** (#5243) emptying is a recorded step that cannot
  be reversed. A snapshot is taken first (`safety-net.md`); if it cannot be taken, emptying is
  refused. The record keeps a note for each thing removed: its name, kind, who, when. No
  content. This is the same shape as the source-model set's purge of a segment, and should be
  one action family with it. *Test:* empty with no room for a snapshot: refused, nothing
  removed.
- `safety.trash.never-empties-itself` — **[GAP]** (#5243) nothing is removed from the Trash by age. There is no
  setting for it. The Trash shows its size so a person can decide. *Test:* none needed beyond
  the absence of a sweeper; a guardrail refuses one.

### E. Shared libraries

- `safety.trash.you-see-what-you-could-see` — **[GAP]** (#5243) a person sees in the Trash exactly the things
  they could see before deletion. The → #4917 access rules apply to the Trash list, to looking at
  a trashed thing, and to Put Back: a restriction on a document reaches it in the Trash too. A
  viewer can look and cannot put back. *Test:* deny a viewer on a folder; trash a document in
  it; the viewer's Trash does not list it.
- `safety.trash.who-may-put-back` — **[GAP]** (#5243) anyone who may edit the place a thing came from may put it
  back, whoever deleted it. *Test:* A deletes, B puts back; the record names both.
- `safety.trash.who-may-empty` — **[GAP]** (#5243) a person may permanently delete what **they** sent to the
  Trash. Only the library's owner may empty everything. An AI agent's account may send things
  to the Trash and may never empty or delete permanently. *Data:* who deleted is already
  stored and is now consulted. *Test:* editor B cannot permanently delete A's trashed
  document; the owner can; an agent's attempt is refused.
- `safety.trash.an-agent-deletes-softly` — **[GAP]** (#5243) for an agent's account and for a workflow run, every
  delete of any kind is soft, even of "undo only" kinds, so a batch can be reviewed and put
  back (`run-take-back.md`). *Test:* an agent deletes a statement; it is recoverable from the
  run's take-back.

### F. From everywhere

- `safety.trash.command-line-and-agents` — **[PARTIAL]** (#5243, #2077) list the Trash, put back, and
  (for a person's account only) delete permanently and empty, from the command line and the
  agent tools, through the same actions, generated from the routes. Built: list, restore and
  purge are generated (`fichero_documents_list_deleted`, `fichero_documents_restore`,
  `fichero_documents_purge`). *Not built:* Empty Trash, the reason and from-where in the
  listing, the person-only rule for permanent deletes. *Test:* CLI and MCP legs.
- `safety.trash.shortcuts-ask-first` — **[GAP]** (#5243) the Shortcuts delete action sends to the Trash and
  needs no confirmation; no Shortcuts action empties the Trash. This answers the open half of
  → #3304. *Test:* the intent calls the Trash action.

## Not in this slice

Deleting a person's account, removing a library from the list, and deleting downloaded model
files are not Trash matters. Each is destructive and outside the record today; each needs its
own confirmation and its own line in `safety.undo.every-action-says-how-it-comes-back`.

## Things to try by hand

1. Delete a document. No dialog. A notice offers Undo. The Trash row shows it.
2. Search for a phrase from that document. It is not found. Open the statements table. Its
   statements are gone. Put it back. Both return.
3. Delete a folder of workflows. Open the Trash. Put Back. Everything returns.
4. Delete a run in the activity window. It is in the Trash with its events.
5. Choose Empty Trash. The sheet says how many documents, statements and megabytes. Cancel.
   Nothing changed.
6. As a second, editor account: try to delete permanently something the first person trashed.
   Refused, in a sentence.

## Test matrix

| Leg | This slice? | Pins | File |
| --- | --- | --- | --- |
| Pure rule (Swift) | y | which kinds go to the Trash | beside the delete actions |
| Availability (Swift) | y | Trash row, Put Back, Empty reachable | the availability suite |
| Backend (pytest) | y | A, B, D, E with a real database, real vectors, real stored files, two accounts | extends `fichero-server/tests/unit/api/test_document_actions.py` and siblings |
| Backend (pytest), to write | top-level listing with from-where and why ("moved to <project>"); Put Back into Sources when the folder is gone or trashed; Empty Trash as one step with a snapshot, naming moved items; knowledge hidden, shown again, pruned | `fichero-server/tests/unit/api/test_trash.py` |
| Guardrail | y | every delete declares trash or undo-only; reads use the seam; no sweeper | new checks |
| MCP / CLI | y | F | the MCP and CLI suites |
| Click-around (Mac) | y | C and the six things above | the UI suite |
| iPhone / iPad | y | Trash in the sidebar; Put Back | the iOS plans |
| Load | y | Trash list with 100,000 items; reads with a large Trash stay within the ratchet | the perf suite |

## Open questions

**Answered** (source/source-model.md Rulings 2026-09-20 item 6 (passes only)): A deleted pass goes to the Trash; a single segment is undo only. Rest of the rule still open. See the questions file. From this slice: the rule for what goes to the Trash; no confirmation
for a reversible delete; what happens to a trashed document's statements; never emptying by
age; who may empty.

**Answered 2026-10-10** (the maintainer): a Trash per project and one for the always-there
project; a move between projects sends its source here; no automatic emptying (no retention
period). Still open from the folded draft: whether workflows and notes as rows join this Trash
as nodes (*recommend:* yes, as `safety.trash.the-rule` already says), and whether claims and
entities deleted on their own keep the knowledge graph's `MutationLog` undo rather than a second
Trash (*recommend:* yes; `safety.trash.the-rule` already makes a statement undo only).
