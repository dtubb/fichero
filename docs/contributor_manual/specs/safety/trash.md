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
- `safety.trash.no-hard-delete-by-folder` — **[PARTIAL]** (#5243) (built: `DELETE /api/folders/{kind}/folders?delete_contents=true` deletes each workflow, search and chat through its kind's audited action, so every item has a record and an undo, pinned by `fichero-server/tests/unit/api/test_folder_delete_is_a_recorded_step_5243.py`; not built: the items going to the Trash as one step that Put Back returns whole, since those kinds are not soft-deleted yet) deleting a folder of workflows, searches or
  conversations is the same recorded Trash action as any folder. The unrecorded hard delete is
  removed. *Test:* delete such a folder with contents; all of it is in the Trash under one
  step; Put Back returns all of it.
- `safety.trash.is-a-folder-in-the-sidebar` — **[PARTIAL]** (#5243, #2077; owner design 2026-11-05: the Trash is a plain folder in the tree, Finder-like, not a separate screen) the Trash row opens onto what is in it: a chevron at the row's leading edge, where every folder has it (owner ruling 2026-11-11, #6536; it was drawn at the trailing edge, by a button inside the row, and the items were indented by hand. Built 2026-11-11: `SidebarTrashNode` is a real `DisclosureGroup` while the Trash holds something, tagged on the group; `SidebarTrashNodeTests.theTrashOpensOnlyWhileItHoldsSomething`; seen in its preview, not yet in the running app), shows the top-level things in the Trash as rows beneath (the first 50; the rest are one "N more in the Trash" row), each with Put Back on its menu; a click on the row, a child or the "more" row opens the Trash pane. The chevron is drawn only while the Trash holds something. Built: `SidebarTrashNode`, `SidebarTrashChildRow`. Swift written, not run here. Not built: the chevron in the leading strip where a folder's is (it sits at the trailing edge so the name keeps its place; the owner's eyes are needed to say which), child rows that open their own contents, and dragging a child out to put it back somewhere. *Test:* `SidebarTrashNodeTests.fewEntriesAreAllDrawnAndNothingIsHidden`, `.manyEntriesAreCappedInOrderAndTheRestAreCounted`, `.anEmptyTrashDrawsNothing`.
- `safety.trash.drop-to-trash` — **[PARTIAL]** (#5243; owner design 2026-11-04: the Trash is a plain place in the sidebar, Finder-like) dropping library items on a project's Trash row sends them there as one undoable step, the same `document.delete` a Delete key sends; a row inside a dropped folder is left to the folder; an item from another project, a non-document and a file from Finder are refused and logged. Built: `SidebarTrashRow` takes the drop through `LibraryItemDropDelegate`, `SidebarActions.moveDroppedToTrash` sends it. Swift written, not run here. *Test:* `SidebarDeleteTests.aDropOnTheTrashTakesDocumentsOnlyAndLeavesAFolderChildToTheFolder`, `.aDropOnTheTrashSurvivesAParentCycleWithoutHanging`.
- `safety.trash.one-delete-path` — **[PARTIAL]** (#5243) (built for the app's document deletes: the sidebar, the Library pane and Shortcuts send one `DocumentDeleteActionParams` to `document.delete`, and the document store's two unrecorded deletes are removed, pinned by `fichero-server/tests/unit/test_one_delete_path_to_the_trash_5243.py`; not built: the other kinds' deletes, the command line and agents) the sidebar, the Library pane, the menu, the keyboard
  (Command-Delete), Shortcuts, the command line and agents all call the same action for a kind.
  *Test:* the availability leg finds one call site per kind.

### B. Out of the way while it is there

- `safety.trash.every-read-leaves-it-out` — **[PARTIAL]** (#5406, #5243) (built: the claims, entities, notes, annotations, segments, artifacts and the full graphs leave a trashed document's rows out through `knowledge/trash_visibility.py`; the guardrail `scripts/check_trash_seam_reads.py` refuses a new API GET handler that reads one of those kinds without the seam, pinned by `fichero-server/tests/unit/scripts/test_check_trash_seam_reads_5406.py`; not built: the 30 handlers seeded in `scripts/check_trash_seam_reads_known_gaps.json` still leak, each to close and delete from the file, and the kinds beyond GET handlers, exports and datasets) a thing in the Trash appears in no list, count,
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
  out; the full-library graphs (`build_full_graph`, `build_full_cooccurrence`, about eighteen endpoints) leave a trashed page's knowledge out too, their cache keyed on the Trash (`fichero-server/tests/unit/api/test_trash_full_graph_leaves_it_out_5406.py`). segments (the scoped list), annotations and notes are out of view with their document too, a note that also links a live document staying (`fichero-server/tests/unit/api/test_trash_hides_segments_annotations_notes_5406.py`). the library-wide artifact list leaves a trashed document's artifacts out in the same WHERE as its count and page (`fichero-server/tests/unit/api/test_trash_hides_artifacts_5406.py`). *Not built:* the per-document artifact reads of a trashed document; the app's drawing of the mark on a two-source
  statement (the list already names the source in the Trash, `GET /api/claims` `sources_in_trash`, read when listing and never stored, `fichero-server/tests/unit/api/test_trash_marks_a_two_source_statement_5243.py`); the graph reads beyond the full-library graphs; the cascade still removes a
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
  - Note 2026-11-07 (spec-writer, from the landings): the app half is built since 2026-10-10, `SidebarTrashRow` ends every project's section and the top section (`safety.trash.a-place-in-the-sidebar`); what is left of this line is the click-around test on two projects and the always-there one, in Step 3.1.
- `safety.trash.a-place-in-the-sidebar` — **[PARTIAL]** (#5243, #2077) the Trash is a row named Trash at the
  end of each project's section of the sidebar; the always-there project's is at the end of the
  top section; its icon shows whether that Trash is empty. It opens in the Library like any
  folder: every view mode, search within it, sorting by when deleted and by whom, List mode with
  columns for where from, when, by whom and why. Things in it can be looked at (Quick Look, the
  Source view, the Reader) and cannot be edited. The context menu and the Edit menu offer Put
  Back, Delete Permanently… and Empty Trash…; dragging an item out of the Trash onto a folder of
  the same project puts it back there. *Test:* availability; click-around. *Built (app,
  2026-10-10):* `SidebarTrashRow` ends every project's section and the top section, its icon full
  or empty; selecting it lists that project's Trash in the Library pane (`TrashPane`, from
  `TrashStore`, merged one entry at a time) with what, when, who, where from and why; Put Back and
  Empty Trash… are one component each in the context menu and the Edit menu; Empty Trash… asks
  with the engine's question and moved-items sentences (`fichero/Tests/Unit/general/Models/TrashStoreTests.swift`).
  *Not built:* view modes, search and sorting in the Trash, looking at a trashed thing, Delete
  Permanently…, dragging out to put back, the offer to put back a trashed folder.
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
- `safety.trash.shows-in-the-preview-like-a-folder` — **[GAP]** (#6175; owner 2026-11-08: "we used to have trash in the Preview as well". Code today: selecting a project's Trash routes it to the Library pane (`SidebarView` selection routing `.trash`, `Views/Library/TrashPane.swift`), and the Preview has no Trash case, so a window whose Library pane is hidden or whose Preview is linked to the sidebar shows nothing for it) selecting the Trash shows its contents in the Preview exactly as a selected folder does (`FolderContentsPreview` and the per-pane folder view of `ui/library-view-modes.md` Step 1.1: Canvas, List or Table), scoped to the Trash and read from the existing trash listing (`TrashStore`, the engine's trash route; no new route), its rows carrying where from, when, by whom and why as the Library pane's do; the items are read-only there (no rename, no drag within, no edit; Quick Look and the Source view read-only as Step 3.1 says), and a double-click opens the trashed item read-only. Acceptance: with the Trash selected in the sidebar the Preview's Table lists the trashed items with the four columns; emptying it leaves the Preview's header greyed as the Library pane's is, no sentence. *Test:* `TrashPreviewTests.swift` (not yet written; the Preview's route for the Trash beside a folder and a group, through the real document model; the read-only predicates), the existing `TrashStoreTests.swift`.
- `safety.trash.put-back-and-empty-in-the-preview` — **[GAP]** (#6175) Put Back and Empty Trash… are offered in the Preview's Trash view (its head, as `TrashPane` offers them: `PutBackButton` over `TrashActionsTarget`, `EmptyTrashButton`) and in the context menu of every trashed row there, the same items the Edit menu and the Library pane render (`menus.context-matches-bar`), acting on the Preview's selection through the same store and the same audited actions, one undo each; Empty asks first with the numbers as Step 2.4 rules. Acceptance: right-clicking a trashed page in the Preview offers Put Back and Delete Permanently…; Put Back returns it and shows the notice with the folder offer; Empty Trash… in the Preview's head asks and then empties, and the Library pane's view agrees. *Test:* `TrashPreviewTests.swift` (not yet written; the context menu's items and the target from the Preview's selection), the existing `TrashStoreTests.swift`.
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

- `safety.trash.empty-says-what-will-go` — **[PARTIAL]** (#5243) (built: the preview `GET /api/documents/trash/empty` carries `notes`, `stored_files`, `stored_bytes` and a `detail` sentence, "It also removes 2 stored files (4.2 MB) and 1 note.", and the app's confirm shows it above the moved-items sentences, `TrashStoreTests.theEmptyQuestionNamesWhatElseGoes`; the numbers are what then goes, `fichero-server/tests/unit/api/test_empty_trash_removes_only_its_own_files_5243.py`; not built: pages and annotations counted apart from documents) Empty Trash and Delete Permanently first show what
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
- `safety.trash.empty-removes-everything-and-only-that` — **[PARTIAL]** (#5243; manager ruling 2026-11-05, inside the owner's "deleted for good") (built: Empty Trash also removes the trashed documents' own stored files, the copied-in originals under the library's `files/` and the derived images under `storage/thumbnails/`, and the notes whose every linked document is trashed; read before the purge and carried out after it, so the confirm's numbers are what goes; never a linked original outside the library, a path that escapes it by `..` or a symlink, nor a file a live document also uses; `fichero-server/tests/unit/api/test_empty_trash_removes_only_its_own_files_5243.py`; not built: the audit row keeping a note per file removed, and a two-source statement kept with a stated absence) emptying removes the rows, the
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
  - Note 2026-11-07 (spec-writer): the refusal half is built and pinned, `test_no_snapshot_no_empty` under `safety.trash.empty-is-one-step`; what is left is the per-thing note in the record (name, kind, who, when) and the one action family with the segment purge, in Step 2.4.
- `safety.trash.never-empties-itself` — **[GAP]** (#5243) nothing is removed from the Trash by age. There is no
  setting for it. The Trash shows its size so a person can decide. *Test:* none needed beyond
  the absence of a sweeper; a guardrail refuses one.

### E. Shared libraries

- `safety.trash.you-see-what-you-could-see` — **[GAP]** (#5243) a person sees in the Trash exactly the things
  they could see before deletion. The → #4917 access rules apply to the Trash list, to looking at
  a trashed thing, and to Put Back: a restriction on a document reaches it in the Trash too. A
  viewer can look and cannot put back. *Test:* deny a viewer on a folder; trash a document in
  it; the viewer's Trash does not list it.
- `safety.trash.who-may-put-back` — **[PARTIAL]** (#5243; manager ruling 2026-11-05: whoever could delete the item may put it back) (built: Put Back needs the same write access as the delete, so an editor puts back what they or another deleted, `fichero-server/tests/unit/security/test_only_the_owner_empties_the_trash_5243.py`; not built: a test that the record names both people) anyone who may edit the place a thing came from may put it
  back, whoever deleted it. *Test:* A deletes, B puts back; the record names both.
- `safety.trash.who-may-empty` — **[PARTIAL]** (#5243; manager ruling 2026-11-05: Empty Trash is the library owner's alone when accounts are on; in a personal library the caller is the owner) (built: `document.empty_trash` refuses anyone but the library's owner with accounts on, the owner's own key and a personal library passing, `fichero-server/tests/unit/security/test_only_the_owner_empties_the_trash_5243.py`; not built: an editor permanently deleting what they alone sent to the Trash, and an AI agent's account refused) a person may permanently delete what **they** sent to the
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

## Build order

What landed (read from origin/integration on 2026-11-07, `git log -- '*trash*'`): the engine's soft delete, `GET /api/documents/trash` per project with what, when, who, where from and why, Put Back into the old folder or Sources with the offer, Empty Trash as one recorded step after a snapshot naming moved items, the stored files and notes it removes, the owner-only empty and the editor's put back; the one `document.delete` path for the app's document deletes; the Trash seam over claims, entities, notes, annotations, segments, artifacts, the full graphs and the curation queues, with a guard refusing a new GET handler without it (30 known gaps seeded); the app's Trash row per project with its chevron and child rows, Put Back and Empty Trash… in the context and Edit menus, the Trash pane, the drop on the row (Swift written, not all run), the Trash folder's preview; #6175's floor on integration (fff858ac0, 580a09a43): a sidebar delete never takes the parent, one undoable batch, the selection never a delete target, the engine's snapshot in the audit row (`ui/sidebar-crud.md` `delete.never-deletes-the-parent`, `delete.snapshot-so-undo-restores`). What is left is each bullet's *Not built*, in the order below: the owner's ruling of 2026-11-04 stands over all of it (the Trash is a plain folder in the sidebar tree, Finder-like, never a mode or a window: things are moved in, put back, or deleted for good), and #6175 comes first.

### Stage 1 — the floor: a delete never takes the parent, and every delete is the one path (#6175)

#### Step 1.1 — #6175 closed on the owner's Mac; every document delete and the drop on the Trash row are the one recorded path (#6175, #5243)
- Behaviours: `safety.trash.one-delete-path`, `safety.trash.drop-to-trash`
- Tests: fichero-server/tests/unit/api/test_sidebar_delete_and_undo_end_to_end_6175.py, fichero/Tests/Unit/general/Views/Sidebar/SidebarDeleteTests.swift, fichero-server/tests/unit/test_one_delete_path_to_the_trash_5243.py
- Size: S

Landed: the engine never deletes upward, the app's selection is never a delete target, the batch is one undoable set (`ui/sidebar-crud.md`, #6175). Left: the owner's device check of #6175 (the issue stays open for it); the Swift tests run, not only compiled; a mixed selection (documents with workflows or searches) deleted as one batch, not one by one; batch-undo end to end; the audit row kept until purge and undo after a restart (`delete.snapshot-so-undo-restores`'s unverified half). Nothing of the Trash's own goes before this.

### Stage 2 — the engine and the routes: every kind, out of view everywhere, Put Back and Empty whole, who may, from everywhere

#### Step 2.1 — the rule and one shape: every delete action declares Trash or undo-only; every Trash kind is soft-deleted the same way; deleted runs and folders of other kinds join (#5243, #4960)
- Behaviours: `safety.trash.the-rule`, `safety.trash.one-shape-for-every-kind`, `safety.trash.deleted-runs-join-it`, `safety.trash.no-hard-delete-by-folder`
- Tests: fichero-server/tests/unit/api/test_trash.py, fichero-server/tests/unit/api/test_folder_delete_is_a_recorded_step_5243.py, test_trash_every_kind.py (not yet written)
- Depends on: 1.1
- Size: M

Engine only. Order: the registration field (trash or undo-only) and its guardrail; the three columns (when, by whom, step id) on notes, references, workflows, runs, batches, saved searches, conversations, canvas boards and entities, existing rows read as live; the deleted run listed in the Trash and its Put Back; a folder of workflows, searches or chats trashed as one step. Ruled 2026-11-07 (manager default, owner may veto): a deleted pass goes to the Trash (it costs tokens to redo) and Put Back restores it, as the table says.

- test (to write): `test_trash_every_kind.py` in fichero-server/tests/unit/api/ (one of each kind deleted lists in the Trash with who, when and step; a group deleted together is put back together; a run returns with every event; the guardrail names an action that declares neither)

#### Step 2.2 — out of view everywhere: the 30 known gaps closed, exports and datasets, the rest of the dependants, the curated-work count (#5406, #5243)
- Behaviours: `safety.trash.every-read-leaves-it-out`, `safety.trash.dependants-go-with-their-source`, `safety.trash.curated-work-is-never-hidden-silently`
- Tests: fichero-server/tests/unit/scripts/test_check_trash_seam_reads_5406.py, fichero-server/tests/unit/api/test_trash_hides_segments_annotations_notes_5406.py, test_trash_reads_leave_it_out_everywhere.py (not yet written)
- Depends on: 2.1
- Size: M

Engine only. Order: each handler in `scripts/check_trash_seam_reads_known_gaps.json` closed and removed from the file until it is empty; exports and datasets through the seam; the per-document artifact reads of a trashed document; the graph reads beyond the full-library graphs; the cascade keeping a two-source statement with its stated absence; the delete's result carrying the count of person-curated statements and notes taken out of view, for the app's notice (Step 3.1).

- test (to write): `test_trash_reads_leave_it_out_everywhere.py` in fichero-server/tests/unit/api/ (the known-gaps file is empty; an export and a dataset of a folder leave a trashed page out; a two-source statement survives a purge with its absence stated; the delete result counts curated work)

#### Step 2.3 — Put Back and Empty, whole: a moved item's two answers, the transfer made permanent, pages and annotations counted, a note per removed file (#5243, #5657, #2077)
- Behaviours: `safety.trash.put-back`, `safety.trash.put-back-a-moved-item`, `safety.trash.empty-names-moved-items`, `safety.trash.empty-says-what-will-go`, `safety.trash.empty-removes-everything-and-only-that`
- Tests: fichero-server/tests/unit/api/test_trash.py, fichero-server/tests/unit/api/test_empty_trash_removes_only_its_own_files_5243.py, test_trash_put_back_moved_and_empty.py (not yet written)
- Depends on: 2.2
- Size: M

Engine only; the app's notice, offer and sheet are Step 3.1. Order: `POST /api/documents/{id}/restore` takes `moved: "undo" | "keep-copy"` for an item a move sent here (the transfer's `undo-move`, or the move recorded as a copy in both projects), refused in words without it; Empty marks the transfer permanent in both projects and its undo is refused in words; the preview counts pages and annotations apart from documents; the audit row keeps one note per removed file.

- test (to write): `test_trash_put_back_moved_and_empty.py` in fichero-server/tests/unit/api/ (both answers for a moved item, read back in both projects; the transfer's record after Empty and the refused undo; the preview's page and annotation counts equal what goes; the audit row's note per file)

#### Step 2.4 — what Empty cannot do, and who may: the record's notes, no sweeper, see what you could see, an editor's own permanent delete, an agent refused (#5243, #4917)
- Behaviours: `safety.trash.empty-cannot-be-undone-and-says-so`, `safety.trash.never-empties-itself`, `safety.trash.you-see-what-you-could-see`, `safety.trash.who-may-put-back`, `safety.trash.who-may-empty`
- Tests: fichero-server/tests/unit/security/test_only_the_owner_empties_the_trash_5243.py, fichero-server/tests/unit/api/test_trash.py, test_trash_access.py (not yet written)
- Depends on: 2.3
- Size: M

Engine only. Order: the record's per-thing note and the one action family with the segment purge; a guardrail that refuses any retention or sweeper over the Trash; the #4917 access rules over the Trash list, a trashed thing and Put Back; `document.purge` of one item allowed to the person who trashed it, and an agent's account refused for purge and empty; the record naming both the deleter and the restorer.

- test (to write): `test_trash_access.py` in fichero-server/tests/unit/security/ (a viewer denied on a folder sees no trashed document of it and cannot put back; editor B cannot purge A's item, A can, the owner can; an agent is refused; the put-back record names both people; the sweeper guardrail)

#### Step 2.5 — from everywhere: the command line, the agent tools, Shortcuts and a run delete softly; it is the library's Trash on every device (#5243, #2077, #3304)
- Behaviours: `safety.trash.command-line-and-agents`, `safety.trash.shortcuts-ask-first`, `safety.trash.an-agent-deletes-softly`, `safety.trash.it-is-the-librarys-trash`
- Tests: fichero-mcp/tests/test_mcp_generated.py, test_trash_cli_mcp.py (not yet written), TrashOnEveryDeviceIOSTests.swift (not yet written)
- Depends on: 2.4
- Size: M

Engine and the generated clients first (Empty Trash, the reason and from-where in the listing, the person-only rule for permanent deletes, every delete soft for an agent's account and a run); then the Shortcuts intent sending to the Trash with no confirmation and no empty intent; then the iPhone and iPad showing the same Trash (a row in the sidebar, Put Back) from the same routes.

- test (to write): `test_trash_cli_mcp.py` in fichero-cli/tests/ (list with reason and from-where, put back, empty, the person-only purge, an agent's soft delete of an undo-only kind)
- test (to write): `TrashOnEveryDeviceIOSTests.swift` in fichero/Tests/UI/ios/ (delete on the Mac fixture engine, the iPhone lists it, Put Back)

### Stage 3 — the app: a plain folder in the tree, Finder-like (owner 2026-11-04)

#### Step 3.1 — the Trash is a folder: opens like one in every view mode, lists what and why, Put Back's notice and offer, Delete Permanently…, drag out to put back, no dialog on a delete (#2077, #5243)
- Behaviours: `safety.trash.is-a-folder-in-the-sidebar`, `safety.trash.a-place-in-the-sidebar`, `safety.trash.one-per-project`, `safety.trash.lists-what-and-why`, `safety.trash.delete-is-not-confirmed`
- Tests: fichero/Tests/Unit/general/Views/Sidebar/SidebarTrashNodeTests.swift, fichero/Tests/Unit/general/Models/TrashStoreTests.swift, TrashFolderUITests.swift (not yet written)
- Depends on: 2.3
- Size: M

App only, on the routes above. Order: the Trash row as a folder of the tree (its chevron where a folder's is, the owner's eyes on it; child rows that open their contents) listing in every Library view mode with the columns where from, when, by whom and why, search and sorting within it, Quick Look and the Source view on a trashed thing read-only; Put Back's notice with the offer to put the folder back too; Delete Permanently… with the engine's numbers; dragging an item out onto a folder of its project puts it back there; the reversible delete shows no dialog, a notice offers Undo and names curated work taken out of view (Step 2.2's count); the mark on a two-source statement; the Empty Trash sheet's moved-items lines. Nothing here is a window or a mode.

- test (to write): `TrashFolderUITests.swift` in fichero/Tests/UI/mac/ (XCUITest: delete shows no dialog and a notice with Undo; the Trash row opens as a folder in list and icon mode with the four columns; Put Back returns the item and offers the folder; drag out puts back; Delete Permanently… shows the numbers; two projects and the always-there project each list only their own)

#### Step 3.2 — the Trash in the Preview: its contents like any folder, read-only, with Put Back and Empty Trash… in the head and the context menu (#6175)
- Behaviours: `safety.trash.shows-in-the-preview-like-a-folder`, `safety.trash.put-back-and-empty-in-the-preview`
- Tests: fichero/Tests/Unit/general/Models/TrashStoreTests.swift, fichero/Tests/Unit/general/Views/Sidebar/SidebarTrashNodeTests.swift, TrashPreviewTests.swift (not yet written)
- Depends on: 3.1
- Size: S

App only, no new route: the Preview's folder branch takes the Trash where it takes a folder (the same classifier Step 3.1 teaches the tree and the Library pane), scoped to the trash listing the Library pane already reads; the head renders the two existing buttons; the row's context menu renders the same two items over the Preview's selection. Order: the route classifier and the read-only predicates with their test red then green; the head and the context menu; a click-around by hand with Step 3.1's.

- test (to write): `TrashPreviewTests.swift` in fichero/Tests/Unit/general/Views/Preview/ (the Trash routes to the folder view in every per-pane mode; items read-only; the head's two buttons; the context menu's two items and their target from the selection)

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
