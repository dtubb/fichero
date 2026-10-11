# Moving and copying between projects and machines — Design Spec (#5657)

> Milestone: Library View
> Manual: TBD — a section of "Organising a project": dragging items to another project (a move) and
> ⌥-dragging them (a copy); what travels with a page and what is left behind and listed; how the
> people and places on a page join the other project's knowledge graph (proposed, never merged by
> themselves); undoing a move; copying to another Mac or a server; dragging items out to the Finder;
> the Trash (`source/trash.md`).
>
> **Status: DRAFT — 2026-10-10.** Issues: #2397 (move between projects), #4311 (copy between projects,
> and dragging out to the Finder), tracked by #5657. Written to be implemented next: every claim about
> the code is **VERIFIED** on disk at `52b7b1f65` with a path, or marked **INFERRED**. Related:
> `source/trash.md` (the per-project Trash a move sends its source to), `ui/sidebar-crud.md` (drag
> grammar inside one project, `delete.*`, the always-there project), `compute/transfer-and-results.md`
> and `compute/targets-and-connection.md` (the carriers and the paired machines a copy between
> machines reuses), `source/models-chains-and-projects.md` (a project is what the code calls a
> library; recipes and models), `compute/training-and-evaluation.md` (a model's card),
> `transport/library-sharing.md` (people and permissions).

## Intent

A researcher keeps several projects: a box being transcribed, a dissertation's sources, the
always-there My Project where things land first. Material moves between them the way files move
between folders in the Finder: drag a page, a document or a folder from one project to another and it
is there, whole — its pictures, its passes and lines, every reading, the names and statements found on
it, its notes, its kind and its fields. Hold ⌥ and it is copied instead. Nothing is half-moved: the
source gives up its items only after the target's copy has been checked, a move goes to the source's
Trash rather than vanishing, and one Undo puts everything back.

The people and places on a page are the hard part. The other project already has its own Juan de la
Cruz. Fichero never decides that two people are one: the carried entity is matched against the target's
graph (by an authority id first, then by name) and a match is offered to a person as a proposed merge.
Every mark a person made (a confirmation, a correction, a merge) is kept.

Whatever cannot travel — a link to a page left behind, a place on a canvas, a slot in a workspace, half
of a group — is cut on purpose and listed in the transfer's result. Nothing dangles silently.

Between machines (another Mac running Fichero, a server), the rule is the Finder's rule across disks:
a transfer **copies**. The far side can vanish mid-way, so nothing is ever deleted at the source by a
transfer between machines; a person who wants the source gone deletes it themselves.

## Ruled 2026-10-10 (the maintainer)

- **Within one engine, a drag moves; ⌥-drag copies** (the Finder's convention). A move is undoable; the
  source's items go to its Trash (soft delete) only after the target's copy is verified.
- **Entities and statements resting on moved pages are carried.** Each mention and statement travels;
  each entity is matched into the target's knowledge graph by authority id (Wikidata, VIAF, …), then by
  name; a match becomes a **proposed** merge a person confirms, never an automatic one; no match makes a
  new entity; every "set by a person" mark (confirmations, corrections, merges) is kept. On a move, the
  source keeps an entity only while other pages still mention it.
- **Always with a page:** segments, passes, readings at every level, artifacts, attributes, notes, and
  the node's kind (its document type, matched by key, made in the target if missing).
- **What does not move is cut and listed:** a relation to a page left behind, a canvas position, a
  workspace slot, a group only partly moved — cut in the source, listed in the transfer's result.
- **Between machines a transfer copies.** There is no ⌘-move across machines; a person who wants the
  source gone deletes it there themselves. (This supersedes #4311's "cross-library drag defaults to
  copy" for projects on one engine, which now move.)
- **Aliases stay within a project.** Make Alias and ⌘⌥-drag make an alias inside one project; a drop
  that would make an alias in another project, or on another machine, is refused in words ("Aliases
  stay within a project.") and offers a copy instead.
- **Each project has its own Trash, the always-there project included** (`source/trash.md`).

## What exists today (VERIFIED at `52b7b1f65` unless marked)

### How a document subtree is stored

All paths below are under `fichero-server/src/fichero_server/`.

- **One project = one `.fichero` package = one DuckDB file.** A project is what the code calls a
  library (`source/models-chains-and-projects.md`, "the words"). Every row below lives in that one
  database; nothing is shared between two projects' databases. (Not to be confused with the `Project`
  model in `models/knowledge.py:1350`, the research workspaces of #918, which group items *inside* one
  library; this spec calls those **research workspaces**.)
- **Documents.** `Document` (`models/__init__.py:247`): the tree is `parent_id`; `node_kind`
  (`document`, `alias`, `artifact`, …), `doc_type` (folder, file, …), `prototype_key` (the document
  type, `:308`), `attributes`, `metadata` (including `metadata.attribute_sources`, who set each
  attribute and the kind, `workflows/attribute_sources.py`), `page_content`, `path`, a security-scoped
  `bookmark` in metadata (`:719-735`), `deleted_at`/`deleted_by` (soft delete).
- **Files.** `db/storage.py:471` `resolve_source` finds a document's file in order: the macOS bookmark,
  `doc.path`, `metadata.source_path` / `full_path` / `local_path`, then a package-relative `files/…`
  path re-rooted under the current package. An imported (copied-in) file lives inside the package under
  `files/`; a **linked** import keeps its original absolute path outside the package. Thumbnails and
  display images are caches keyed by document id (`_thumb_path`, `_display_path`, `:226`, `:262`) and
  regenerate. The original is served by `GET /api/storage/source/{doc_id}`
  (`api/routes/system/storage.py:295`).
- **Passes, segments, readings.** `SegmentPass` and `Segment` (`models/segments.py:590`, `:654`), keyed
  by `document_id`; a segment points at its `pass_id`, `parent_segment_id`, and (from conversion)
  `source_artifact_id`, `rendition_id`, `run_id`. `SegmentMatch` (`:982`, `original_id`/`copy_id`),
  `SegmentForwarding` (`:1004`, from/to segment ids, and an `audit_id` into the library's audit chain,
  `:1028`), `SegmentCarry` (`:1064`), `SegmentVersion` (`:1086`, `old_segment_id`), `SegmentPassChoice`
  (`:1807`), `PageLineMap` (`:1837`). A **reading** is a `ContentRepresentation`
  (`models/__init__.py:900`), with `ReadingChoice` (`models/readings.py:352`) for which reading counts;
  the reading **kinds** and **levels** are per-library vocabularies (`LibraryReadingKind`,
  `LibraryReadingLevel`, `models/readings.py:240`, `:185`). Reading orders: `ReadingOrder` and
  `ReadingOrderEntry` (`models/reading_orders.py:58`, `:85`; `order_id`, `segment_id`,
  `parent_entry_id`). Anchors (`models/anchors.py`) carry segment ids inside their shapes.
- **Derived ids.** `legacy_pass_id(artifact_id)` and `legacy_segment_id(artifact_id, box_index)`
  (`models/segments.py:100`, `:104`) make ids *from* an artifact's id: a plain old→new id map breaks
  them; they must be derived again from the new artifact id.
- **Artifacts.** `Artifact` (`models/__init__.py:778`), keyed by `document_id`; proposals such as Find
  the Documents' `grouping` are artifacts too (`source/finding-documents.md`).
- **Other rows keyed by document id** (the manager's inventory, spot-checked): `models/segments.py`,
  `readings.py`, `anchors.py`, `reading_orders.py`, `knowledge.py`, `checking.py`, `hermeneutics.py`,
  `research.py`, `campaigns.py`, `conversion.py`; `TypedLink` (`models/typed_links.py:169`, from/to
  kind and id, soft-deletable) relates segments, notes, documents, claims, canvas items, entities and
  outside URIs.
- **Knowledge graph.** `KnowledgeEntity` (`models/knowledge.py:849`: `canonical_name`, `entity_type`,
  `names`, `curation_state` (unreviewed / verified / rejected / merged), `merged_into_id`,
  `source_document_ids`, `attribution_chain`). An entity's **authority id** is a `same_as` `TypedLink`
  from the entity to the authority's canonical URI (`knowledge/authorities.py:1-30`, `:180-200`); the
  authorities table names Wikidata and the rest. `KnowledgeClaim` (`:1741`): `source_document_id`,
  `source_ids`, `subject_entity_id`, `entity_ids`, `curation_state`, `created_by`. A **mention** is a
  claim's document→entity edge (`knowledge/graph.py:84-106`, the `mentions` predicate) or a segment's
  `names` link to an entity. `EntityMatchCandidate` (`:1653`) is the existing **proposed merge** a
  person accepts or rejects; `EntityMergeAudit` (`:977`) the reversible merge record. Per-library
  vocabularies: `LibraryEntityType` (`:1086`).
- **Document types.** A node's `prototype_key` names a `ClassificationValue` row with dimension
  `document_prototype` (`models/node_prototypes.py:1-20`, `models/knowledge.py:1035`), per library,
  with a `parent_key` chain and inheritable fields.

### What the engine does with them today

- **Several projects open at once.** `DatabaseManager.get_database` (`db/manager.py:91`) keeps one
  `Database` per package, keyed by its real path (`_cache_key`, `:334`); `is_open` (`:87`) answers
  whether a project is open; `open_library_paths` (`:566`) lists them. So "the target project is not
  open" is checkable before anything is written.
- **One action, one database.** `ActionRegistry.invoke` (`actions/registry.py:236`) validates, runs,
  audits and emits change events on **one** database per call, in one transaction, with that library's
  audit chain, page-text cache, re-embed and synced-folder hooks. Undo
  (`api/routes/system/actions_registry.py:285`) finds the audit row in one library. Two DuckDB files have
  no shared transaction.
- **Same-project copy.** `duplicate_document_impl` (`api/routes/document/documents.py:2689`, action
  `document.duplicate`): new ids, walks the tree, copies the **document rows only** (page content,
  metadata, attributes); passes, segments, readings, artifacts and files are **not** copied ("derived
  artifact rows are NOT copied (they regenerate on demand)"). Since passes, segments and readings are
  first-class records a person made, that is no longer enough even within one project, and it is not
  the base for a transfer.
- **Soft delete and restore.** `delete_document_impl` (`documents.py:2879`, `document.delete`) stamps
  `deleted_at`/`deleted_by` on the subtree and keeps snapshots; `document.restore`
  (`restore_document_subtree_impl`, `:1806`) puts it back. `GET /api/documents/trash` (`:822`) lists
  soft-deleted documents; `DELETE /{doc_id}/purge` (`:1854`, `document.purge`) removes for good, after a
  snapshot (#5070), cascading the knowledge graph through `_cascade_delete_kg_rows` (`:1729`: claims
  whose `source_document_id` or `source_ids` name a purged document, then entities left with none,
  each logged as a reversible `MutationLog`).
- **Guards.** `_reject_if_document_read_only` (`:2615`, locked nodes such as Default Workflows and its
  preset mirrors), `_move_would_create_cycle`, the folder check on a drop target.
- **Aliases.** An alias is a `Document` with `node_kind == "alias"` and `alias_target_id`
  (`models/node_aliases.py`); resolving a missing target raises `DanglingAliasError`. The app's Make
  Alias (sidebar and Items context menus, `SidebarItemContextMenu.swift:55`,
  `LibraryView+ContextMenu.swift:156-230`) and ⌘⌥-drop make one through the bookmarks route
  (`/api/bookmarks`); aliasing an alias targets the original.
- **The app's drop grammar.** `sidebarDropOperation` (`fichero/fichero/Views/Sidebar/ItemRow/
  SidebarDropOperation.swift`): plain = move, ⌥ = copy, ⌘⌥ = alias, for document payloads, sampled once
  per drop; sidebar rows, insertion lines and Items cells share it. `processFolderDropItem`
  (`SidebarItemRow+DropHandlers.swift`) checks section, self-drop and nesting but **not which project**
  the dragged item and the target belong to (VERIFIED: no library comparison in the drop path); a drop
  onto another project's folder sends the source's id to the target project's routes, which do not know
  it (INFERRED: refused as not found, which is #2397's "nothing happens").
- **Trained models** live inside their project: `<package>/models/<model>/` with `fichero-card.json`
  and weights (`training/project_models.py:1-30`); the engine's **global store** is shared by every
  project on the engine; `make_global` (`:118`) copies a project's model there, card unchanged
  (`not_for_release` included). The Models node lists a project's models by `belongs_to`
  (`training/model_nodes.py`).
- **Workflows** are rows of the library's `workflows` table, mirrored as document nodes for the sidebar
  (`db/__init__.py:4044`); system presets sit under the locked Default Workflows folder, `read_only`.
- **Saved searches** are `SavedSearch` rows (`models/__init__.py:1790`) in the library.
- **Recipe and setup** are files in the package: `recipe/recipe.yaml` and `recipe/setup.yaml`
  (`recipes/project.py:1-20`), the kept bake-offs under `recipe/bakeoffs/`.
- **Canvases.** `CanvasLayout` (`models/canvas.py:118`): one position per (folder, item), id
  `"{folder_id}::{item_id}"`; `CanvasItem` (`:160`): standalone content on a folder's canvas.
  A workspace is a document whose curated items point at entities or documents by id
  (`documents.py:1176`, `patch_workspace_items`).
- **Between machines.** The transfer core exists, pure and tested, for library sync
  (`workflows/library_sync.py`: content-addressed `SyncObject`, `SyncManifest`, `diff_manifests`,
  `SyncCheckpoint`; `library_sync_io.py` lands an object atomically with its hash re-checked), with two
  read-only routes (`api/routes/library/sync.py`). The write half, the HTTPS carrier to another
  Fichero and the list of paired machines are designed, not built (`compute.transfer.https-write-half`,
  `compute.target.add-fichero-mac`). Device pairing exists (`api/routes/auth/pairing.py`: a code, a
  paired device's own token). A host per library is not built (#2573).
- **Nothing transfers today.** No route, action, job or app surface moves or copies anything between
  two projects or two machines; nothing drags out to the Finder (no file promise in the app).

## Design

### One engine action, `document.transfer`

Every surface — the sidebar, Items, a canvas, the CLI, MCP — calls one route, `POST
/api/documents/transfer`, which runs one audited action, `document.transfer`:

| Parameter | Meaning |
|---|---|
| `items` | the ids of the nodes to transfer, in the source project (a selection; each carries its subtree) |
| `source` / `target` | the two projects, by package path (the library header names the target; the source is named in the body) |
| `target_parent_id` | the folder in the target the items land in (absent: the target's Sources folder) |
| `mode` | `move` or `copy` |
| `dry_run` | true: plan only, write nothing, return the plan (counts, what will be cut, entity matches, refusals) |

The engine owns the whole transfer; the app only sends the drop. A transfer of more than a handful of
nodes runs as one background job (a row in Activity, `transfer.app.progress-in-activity`); the route
returns the transfer's id and the job's id, and `GET /api/documents/transfer/{id}` returns its state and
its result.

### The phases (verify, then delete)

1. **Check.** Both projects open (`DatabaseManager.is_open`); the person may write the target and, for
   a move, the source; no item is locked (`_reject_if_document_read_only`); the target parent is a live
   folder; no item is an alias that would land in another project (`transfer.alias.not-between-projects`);
   the rights record lets the items go where they are going (`transfer.rights-travel`). A refusal names
   the item and the reason and changes nothing.
2. **Plan.** Walk each item's subtree (live rows only; trashed descendants stay behind) and gather every
   row that belongs to it (the table below), the files, the vocabularies it uses, the knowledge it
   carries, and every edge that crosses the edge of the set (to be cut). Allocate a new id for every row.
   This is the dry run's answer.
3. **Write the target.** In the target's database, in one transaction per batch of top-level items,
   write every row under its new id, with every id inside it re-pointed through the map; copy in-package
   files under the target's `files/`; make missing vocabulary entries; match entities
   (`transfer.entities.*`). Each written node records where it came from
   (`metadata.transferred_from`: source project id, source node id, transfer id, when, who).
4. **Verify.** Read back from the target: for each kind of row, the count written equals the count
   planned; every copied file's sha256 equals the source's; every id the map produced resolves. A
   mismatch stops the transfer and rolls the target back (below).
5. **Source (a move only).** Soft-delete the moved items in the source through `document.delete`, with
   the reason "moved to <target>" and the transfer's id, so they appear in the source's Trash labelled
   as moved (`source/trash.md`, `trash.lists-what-was-deleted`). Cut what must be cut in the source
   (`transfer.cut.*`).
6. **Result.** Store and return the result report (below), and emit change events in both projects.

### No cross-file transaction: where the record lives, and the compensation

Two DuckDB files cannot share one transaction, so the order above is the safety: the target is fully
written and verified **before** the source changes, and the source only ever changes by soft delete.

- **The record of a transfer** is one row in each project (`transfers`, the same id): in the target the
  full id map, the files written, the entity proposals and the result; in the source the items sent,
  the mode, the target and the result. The target's audit row is the transfer's audit (`document.transfer`,
  its inverse `document.untransfer`); the source's soft delete is its own `document.delete` audit row
  naming the transfer. Undo from either project finds the transfer by its id and acts on both.
- **A journal for crashes.** Before writing the target the engine writes the transfer's record in the
  target as `writing`; after verification `verified`; after the source's delete `done`. On opening a
  project, a transfer left `writing` is rolled back (its new rows and files removed by the id map); one
  left `verified` for a move resumes step 5 if the source is open, else waits and says so in Activity.
- **If the target write or verification fails,** every row and file the transfer wrote in the target is
  removed by the id map (they are new rows only this transfer made), the vocabulary entries it made are
  removed if nothing else uses them, and the source is untouched. The result says what failed.
- **If the source's soft delete fails after verification** (the source closed, a lock, a write
  refused), the engine retries once; if it still fails, the target's copy is rolled back as above and
  the move is reported as not done, in words, with the reason. A move never ends as a silent copy.

### The id map

Every row in the set gets a new id; nothing keeps a source id in the target except
`metadata.transferred_from`. The map re-points, inside the set: `parent_id`, `alias_target_id`,
`document_id`, `pass_id`, `parent_segment_id`, `source_artifact_id`, `rendition_id`, segment ids inside
anchors and reading-order entries (`order_id`, `segment_id`, `parent_entry_id`), match and forwarding
pairs, segment versions' `old_segment_id`, reading choices, typed-link ends, canvas `folder_id` and
`item_id` (and the composite id), workspace item targets, claim `source_document_id`/`source_ids` and
entity ids, annotation and note targets, `metadata.attribute_sources` references to runs and proposals
that travel. Special cases:

- **Derived ids** (`legacy_pass_id`, `legacy_segment_id`) are computed again from the new artifact id,
  never mapped as plain strings.
- **Audit pointers.** A segment forwarding's or version's `audit_id` points into the source's audit
  chain, which does not travel. In the target it is re-pointed to the transfer's own audit row, and the
  original is kept beside it (`metadata.source_audit_id`) so the history reads "carried from <project>
  on <date>, earlier history there".
- **Run ids** (`run_id`, workflow runs, job ids) name runs recorded in the source; they are kept as
  text with the source project named, not re-pointed (a run is history, not a row that travels).
- **An id outside the set** is never written into the target: the edge is cut and listed.

### What travels with a page (always)

| Kind | Rows | Notes |
|---|---|---|
| the node | `Document` (and its subtree) | name, kind, `prototype_key`, `attributes`, `metadata` incl. `attribute_sources`, sort order |
| the file | the original | in-package: copied byte for byte, sha256 checked; linked: the reference (path, bookmark) only |
| pictures | thumbnails, display images | regenerated in the target (caches keyed by id) |
| passes and lines | `SegmentPass`, `Segment`, `SegmentMatch`, `SegmentForwarding`, `SegmentCarry`, `SegmentVersion`, `SegmentPassChoice`, `PageLineMap` | ids mapped; the chosen pass stays chosen |
| readings | `ContentRepresentation` at every level and kind, `ReadingChoice` | the counted reading stays counted; kinds and levels matched by key, made if missing |
| reading orders | `ReadingOrder`, `ReadingOrderEntry` | an order on a page travels; an order spanning pages left behind is cut and listed |
| artifacts | `Artifact` | every one, proposals included; derived ids recomputed |
| anchors, marks | `SourceAnchor` in rows, `Annotation` | travel with the page they mark |
| notes | `Note` nodes and notes on the page | a note linking to something left behind keeps its text; the link is cut and listed |
| the kind | `prototype_key` → `ClassificationValue` | matched by key in the target; made there (with its fields and parent chain) if missing |
| knowledge | claims, mentions, entities | `transfer.entities.*` |
| other records keyed by the page | rows in `checking.py`, `hermeneutics.py`, `research.py`, `campaigns.py`, `conversion.py`, `rights.py` | carried when every id they name is in the set; otherwise cut and listed |
| search | embeddings | the target re-embeds in the background; the source's embedding stays with the trashed page |

### Knowledge: carried, matched, proposed

For the moved pages, every claim whose source is one of them (`source_document_id` or `source_ids`)
travels, and with it every entity those claims and the pages' `names` links mention. For each such
entity:

1. **By authority id.** If the entity has a `same_as` link to an authority URI and an entity in the
   target has a `same_as` to the same canonical URI, that is a match.
2. **Else by name.** The same `entity_type` and the same canonical name or one of its names (Unicode
   normalised as the library compares names), is a match. More than one match: all are offered.
3. **A match is proposed, never merged.** The carried entity is written in the target as a new entity
   (so the person's work on it survives untouched), and one `EntityMatchCandidate` pairs it with each
   match, naming the reason ("same Wikidata Q-id", "same name and type"). A person accepts (the existing
   merge, audited and undoable) or rejects (remembered, not offered again).
4. **No match:** the entity is written as a new entity.

Every mark a person made travels as it is: an entity's `curation_state` (verified, rejected), a claim's
curation state and `created_by`, a merge's `EntityMergeAudit` for entities that travel, corrections,
the `attribution_chain`. A claim between a carried entity and an entity that does not travel (its other
end is on a page left behind) travels when it rests on a moved page — it is that page's statement — and
its far entity travels with it as a referenced entity, matched the same way.

**On a move, the source** keeps an entity while any live page in the source still mentions it. Claims
resting on the moved pages go to the Trash with their pages: hidden, not deleted (`trash.knowledge`).
An entity whose every mention is now in the Trash is hidden with them, and comes back if the pages are
put back; emptying the Trash prunes it through the existing cascade (`_cascade_delete_kg_rows`).

### What is cut, and listed

Cut in the source (a move) or simply not carried (a copy), and listed in the result, by name:

- a link (typed link, note link, claim link, citation) whose other end is not in the set;
- the moved items' positions on the source folder's canvas (`CanvasLayout` rows keyed by the source
  folder) — positions *inside* a moved folder's own canvas travel with it;
- a workspace's curated slot pointing at a moved item (the workspace stays; the slot is removed);
- a group (#5303) only partly moved: the moved pages leave the group; the group stays with what is left;
- an entry in a research workspace's inclusions (`ProjectInclusion`) naming a moved item;
- an alias in the source pointing at a moved item (`transfer.alias.source-aliases`);
- a recipe override or Find the Documents proposal in the source naming a moved folder.

### Aliases

Within a project, Make Alias and ⌘⌥-drag make aliases as today. Between projects and between machines
there are no aliases: the drop is refused in words ("Aliases stay within a project.") with a Copy
button that performs the copy. On a transfer:

- an alias **inside** the set whose target is also in the set travels, its `alias_target_id` rewritten
  to the target's new id;
- an alias inside the set whose target is **not** in the set does not travel (it would dangle); it goes
  to the source's Trash with the rest on a move, and is listed;
- an alias **in the source** pointing at a moved item cannot follow. Recommended (open question 2):
  it goes to the source's Trash with the move, labelled "alias to <item>, moved to <project>", and is
  listed; undoing the move puts it back.

### Undo

- **Undo a copy:** the copy goes to the target's Trash (soft), entity proposals it made are withdrawn,
  vocabulary it made is removed if unused. Redo copies again.
- **Undo a move:** the items are put back in the source from its Trash (`document.restore`, which also
  brings back their claims and hidden entities), the cut edges are restored from the transfer's record,
  and the target's copy goes to the target's Trash. If the target's copy was changed after the move (a
  reading added, a merge accepted), undo says so and offers to put the source back while keeping the
  target's copy (open question 4); if the source's items were emptied from its Trash, undo of the move
  is refused in words.
- Undo is offered in both projects' windows (⌘Z right after, and the action history), because the
  transfer's record lives in both.

### The result report

One report per transfer, stored on its record, returned by the route and shown by the app:
mode, source, target, when, who; counts by kind (nodes, files and bytes, passes, lines, readings,
artifacts, notes, claims, entities); the document types, reading kinds and levels made in the target;
entities matched (with the proposals to review, one click away) and entities made new; every cut, by
kind, with the item's name and what it pointed to; anything left behind and why (a trashed descendant,
a locked node); for a move, "sent to <source>'s Trash". The report is also what the MCP tool and CLI
print.

### Other kinds of items

| Item | Where it lives | Shared or per project | Drag between projects on one engine |
|---|---|---|---|
| **Trained model** (a node under Models) | `<package>/models/<id>/`: weights + `fichero-card.json` | per project; the engine's global store is shared by all projects | same grammar (move / ⌥ copy); card and weights copied, sha256 checked; the card's `project_of` rewritten, `not_for_release` and evaluations kept (labelled "scored in <source>"); a move of a model the source's recipe or an override uses is refused in words, offering a copy (open question 3) |
| **Model in the global store** (Settings) | the engine's store | shared | not dragged between projects (already in every project); Make Global copies a project's model there (`make_global`) |
| **Workflow** | `workflows` table + its sidebar mirror | per project | same grammar; new id; the sub-workflows it calls by id travel with it; a name already used in the target is kept with " 2" |
| **Preset** (Default Workflows) | seeded in every project, `read_only` | in every project | refused in words: already in the target |
| **Document type** (Edit Document Types) | `ClassificationValue`, dimension `document_prototype` | per project | always a **copy** (a type is vocabulary nodes may use); matched by key: missing → made with its fields and parent chain; same key → the target's kept, differences in fields listed |
| **Saved search** | `SavedSearch` rows | per project | same grammar; a scope naming folders not in the target is cut to the whole project and listed |
| **Recipe and setup** | `recipe/recipe.yaml`, `setup.yaml`, `bakeoffs/` | per project | not dragged; "Use This Project's Setup In…" copies the recipe into the target as a fork (or a follow, `models-chains-and-projects.md`); folder overrides are not carried (they name folders); never a move |
| **Workspace** | a document with curated items | per project | travels as a node; slots pointing into the set are rewritten, others cut and listed |
| **Canvas** | `CanvasLayout`, `CanvasItem` on a folder | per folder | travels with its folder; standalone canvas items travel; positions of items left behind are cut |
| **Note** | `Note` (a node) | per project | same grammar, as a node |
| **Entity or claim alone** | knowledge rows | per project | not transferred alone (they travel with pages); drag an entity to a workspace in the same project only (today's behaviour) |

### Between machines (copy only)

A machine here is another Fichero engine: another Mac of the person's running Fichero, reached over
Tailscale, or a Linux server running the engine (`compute/targets-and-connection.md`). A Slurm cluster
or Hugging Face holds work packages, not projects, and is not a transfer target.

- **The same action, split in two halves.** `document.transfer` on one engine is *plan → package →
  land* run in one process. Between machines, the source engine plans and makes a **transfer package**
  (a `SyncManifest` of the files by sha256, as `compute.package.is-a-sync-manifest`, plus the rows as
  records with their ids and the id map left to the landing side); the target engine **lands** it with
  the same code that writes the target on one engine (step 3) and verifies (step 4). One code path.
- **Transport.** The HTTPS carrier to a running Fichero (`compute.transfer.https-write-half`: put an
  object, commit a manifest), through the one transfer core (`compute.transfer.one-core`): only missing
  objects are sent (`compute.transfer.only-what-is-missing`), each verified on arrival
  (`compute.transfer.verified-on-arrival`), resumable (`compute.transfer.resumes`). Nothing new is
  invented here.
- **Auth.** The far engine is a paired device (`compute.target.add-fichero-mac`): its token, its
  person, and that person's role in the far project. The far engine stamps the actor on what lands
  (`compute.land.server-sets-the-maker`). Versions must match (`compute.connect.version-must-match`).
- **Egress.** Pages sent to another of the person's Macs are the egress class "your own machine"
  (`compute.target.mac-pages-stay-yours`); a project marked "may not leave this machine" cannot be
  copied off it (`compute.leave.stays-local-is-absolute`); restricted material is refused by the one
  gate.
- **A copy, always.** The source is never changed. If the connection drops, objects already sent are
  kept and the send resumes from the checkpoint when the far side is back; nothing lands until every
  object has arrived and been verified; landing is all or nothing on the far side (it has everything
  locally by then; a failure there removes what it wrote). A transfer abandoned (cancelled, or the far
  side gone longer than a set time) removes its partial objects from the far side and says so.

### Out to the Finder

Dragging items out of the sidebar or Items to the Desktop or a Finder window writes files through file
promises: each item's original as it is (`GET /api/storage/source/{doc_id}`, streamed, so it works with a
remote engine and never passes a path), a folder as a folder of its items, an item with no original
(a note, a text node) as Markdown from the one export stream. The app never reads the package from disk.
Nothing in the project changes.

## Behaviours

### The action (engine)

- `transfer.action.one-route` — **[GAP]** (#5657, #2397) `POST /api/documents/transfer` runs one audited
  action `document.transfer` (items, source, target, target parent, mode, dry run); the app, MCP and CLI
  call it and nothing else; it runs as one background job beyond a handful of nodes and `GET
  /api/documents/transfer/{id}` returns its state and result.
- `transfer.action.dry-run` — **[GAP]** (#5657) `dry_run: true` writes nothing and returns the plan:
  counts by kind, files and bytes, vocabulary to be made, entity matches, every cut, every refusal.
- `transfer.action.refusals-in-words` — **[GAP]** (#5657) refused in words, changing nothing: a project
  not open (`DatabaseManager.is_open`), no write permission in the target (or the source, for a move), a
  locked node (`_reject_if_document_read_only`), a target that is not a live folder, the same project
  as source and target (that is `document.move`/`document.duplicate`), an alias between projects.
- `transfer.action.verify-then-delete` — **[GAP]** (#5657, #2397) a move soft-deletes the source's items
  only after the target's copy is written and verified (counts per kind, sha256 per file, every mapped
  id resolving); a failed verification rolls the target back and leaves the source untouched.
- `transfer.action.compensates` — **[GAP]** (#5657) if the source's soft delete fails after
  verification, it is retried once, then the target's copy is rolled back and the move reported as not
  done with the reason; a move never ends as a silent copy.
- `transfer.action.journal-recovers` — **[GAP]** (#5657) the transfer's record is written in the target
  as `writing` before any row, `verified` after verification, `done` after the source's delete; on
  opening a project a `writing` transfer is rolled back and a `verified` move resumes its source step.
- `transfer.action.record-in-both` — **[GAP]** (#5657) each transfer is one record in each project
  (same id): the id map, files and proposals in the target; items, mode and target in the source.
- `transfer.action.provenance` — **[GAP]** (#5657) every node written by a transfer records
  `metadata.transferred_from` (source project id, node id, transfer id, when, who).
- `transfer.action.undo-copy` — **[GAP]** (#5657, #4311) undoing a copy sends the copy to the target's
  Trash and withdraws its entity proposals; redo copies again.
- `transfer.action.undo-move` — **[GAP]** (#5657, #2397) undoing a move puts the items back in the source
  from its Trash, restores the cut edges from the record and sends the target's copy to the target's
  Trash; offered from either project; refused in words when the source's items were emptied since;
  when the target's copy changed since, says so and offers to put the source back keeping the copy.
- `transfer.action.batched-and-gentle` — **[GAP]** (#5657) a large transfer writes in batches of
  top-level items, hashes and copies at background priority and yields to the person's work
  (the auto-throttle rule), with progress per batch.
- `transfer.action.selection-is-one-transfer` — **[GAP]** (#5657) a multi-item selection is one
  transfer, one record, one undo, one result.

### What travels with a page

- `transfer.page.whole-subtree` — **[GAP]** (#5657, #2397) a node travels with its live descendants;
  trashed descendants stay in the source's Trash and are listed.
- `transfer.page.files` — **[GAP]** (#5657, #4311) an in-package original is copied byte for byte under
  the target's `files/` and checked by sha256; a linked original travels as its reference (path and
  bookmark) and the result says it is linked; thumbnails and display images regenerate in the target.
- `transfer.page.passes-and-lines` — **[GAP]** (#5657) every pass and segment travels with its matches,
  forwardings, carries, versions, pass choice and line map, ids mapped; the chosen pass stays chosen.
- `transfer.page.readings-every-level` — **[GAP]** (#5657) every reading (`ContentRepresentation`) at
  every level and kind travels, with its `ReadingChoice`; a reading kind or level missing in the target
  is made there.
- `transfer.page.artifacts` — **[GAP]** (#5657) every artifact travels; `legacy_pass_id` and
  `legacy_segment_id` ids are derived again from the new artifact id, never mapped as strings.
- `transfer.page.attributes-and-sources` — **[GAP]** (#5657) attributes travel with their
  `attribute_sources` (who set each, a person's mark kept as a person's).
- `transfer.page.kind-matched-by-key` — **[GAP]** (#5657) the node's document type is matched by key in
  the target; a missing type is made with its fields and parent chain; the result lists types made.
- `transfer.page.notes-and-marks` — **[GAP]** (#5657) notes, annotations and anchors on the page travel.
- `transfer.page.reading-orders` — **[GAP]** (#5657) a reading order wholly in the set travels; entries
  pointing outside the set are cut and listed.
- `transfer.page.audit-pointers` — **[GAP]** (#5657) a segment version's or forwarding's `audit_id` is
  re-pointed to the transfer's audit row in the target, the original kept as `metadata.source_audit_id`.
- `transfer.page.re-embedded` — **[GAP]** (#5657) the target embeds the carried pages in the background;
  search finds them there when it is done.

### Knowledge

- `transfer.entities.claims-travel` — **[GAP]** (#5657) every claim resting on a moved page
  (`source_document_id` or `source_ids`) travels with its curation state and maker.
- `transfer.entities.match-authority-then-name` — **[GAP]** (#5657) each carried entity is matched in the
  target first by a shared `same_as` authority URI, then by type and name; every match is named with its
  reason.
- `transfer.entities.match-is-proposed` — **[GAP]** (#5657) a match is written as an
  `EntityMatchCandidate` pairing the carried entity (written new) with the target's; never merged by the
  transfer; accepting is the existing audited merge; rejecting is remembered.
- `transfer.entities.no-match-is-new` — **[GAP]** (#5657) an entity with no match is written new.
- `transfer.entities.person-marks-kept` — **[GAP]** (#5657) confirmations, corrections, rejections and
  the merge history of carried entities and claims travel as a person set them.
- `transfer.entities.source-keeps-while-mentioned` — **[GAP]** (#5657) on a move the source keeps an
  entity while a live page still mentions it; one whose every mention is in the Trash is hidden with them
  and pruned only when the Trash is emptied.

### Cuts

- `transfer.cut.listed-never-silent` — **[GAP]** (#5657) every edge that crosses the set's edge (links,
  note links, citations, research-workspace inclusions, recipe overrides, proposals naming a moved
  folder) is cut and listed in the result by name; nothing in either project points at an id that is
  not there.
- `transfer.cut.canvas-position` — **[GAP]** (#5657) the moved items' positions on the source folder's
  canvas are dropped; positions inside a moved folder's own canvas travel; items land in the target by
  its canvas's arrange.
- `transfer.cut.workspace-slot` — **[GAP]** (#5657) a workspace's slot naming a moved item is removed and
  listed; the workspace stays.
- `transfer.cut.partial-group` — **[GAP]** (#5657) moving some pages of a group takes them out of the
  group; the group keeps the rest; listed.

### Aliases

- `transfer.alias.within-a-project` — **[PARTIAL]** (#5657) Make Alias and ⌘⌥-drag make an alias within
  a project. Built: `models/node_aliases.py`, the bookmarks route, `sidebarDropOperation`'s ⌘⌥ case and
  the Make Alias menu items. *Not built: the check that the drop's target is in the same project.*
- `transfer.alias.not-between-projects` — **[GAP]** (#5657) a ⌘⌥-drop onto another project or another
  machine is refused in words, "Aliases stay within a project.", with a Copy button; the engine refuses
  an alias in a transfer's items the same way.
- `transfer.alias.inside-set-rewritten` — **[GAP]** (#5657) an alias in the set whose target is in the
  set travels with its target id rewritten; one whose target is not in the set does not travel and is
  listed.
- `transfer.alias.source-aliases` — **[GAP]** (#5657) an alias in the source pointing at a moved item goes
  to the source's Trash labelled "alias to <item>, moved to <project>", is listed, and comes back on undo
  (recommended, open question 2).

### Other kinds of items

- `transfer.model.project-model` — **[GAP]** (#5657, #5539) a trained model dragged to another project's
  Models moves (⌥ copies) with its card and weights, sha256 checked; the card's project is rewritten,
  `not_for_release` and its evaluations kept, labelled with the project they were scored in.
- `transfer.model.in-use-refused` — **[GAP]** (#5657) moving a model the source's recipe or an override
  uses is refused in words, naming the step, and offers a copy.
- `transfer.model.global-shared` — **[PARTIAL]** (#5539) a model in the engine's global store is in every
  project and is not transferred; Make Global copies a project's model there (built:
  `training/project_models.make_global`). *Not built: the Models node's drag surface.*
- `transfer.workflow.with-its-parts` — **[GAP]** (#5657) a workflow moves or copies with the
  sub-workflows it calls; presets are refused as already present; a name in use gets " 2".
- `transfer.doctype.always-copy` — **[GAP]** (#5657) a document type dragged between projects' Edit
  Document Types is copied, matched by key, never removed from the source; same key keeps the target's
  and lists the field differences.
- `transfer.search.scope-cut` — **[GAP]** (#5657) a saved search moves or copies; a scope naming folders
  not in the target becomes the whole project, listed.
- `transfer.recipe.use-setup-in` — **[GAP]** (#5657) Use This Project's Setup In… copies the recipe and
  setup into another project as a fork or a follow; folder overrides are not carried; never a move.
- `transfer.canvas.with-its-folder` — **[GAP]** (#5657) a folder's canvas and its standalone items travel
  with the folder.

### Between machines

- `transfer.machine.copy-only` — **[GAP]** (#5657, #4311) a transfer to another engine copies; the
  source is never changed by it; no modifier makes it a move.
- `transfer.machine.one-code-path` — **[GAP]** (#5657, #5239) the source plans and packages, the target
  lands and verifies with the same code a transfer on one engine uses.
- `transfer.machine.carriers-reused` — **[GAP]** (#5657, #5239) the package travels by the HTTPS carrier
  through the one transfer core: only missing objects, verified on arrival, resumable from the checkpoint.
- `transfer.machine.paired-only` — **[GAP]** (#5657, #5238) the far engine is a paired device; what lands
  is stamped by the far engine with the paired person; versions must match.
- `transfer.machine.egress-gated` — **[GAP]** (#5657, #5239) a copy off this machine passes the one
  egress gate: a project that may not leave this machine is refused; another of the person's Macs is
  the "your own machine" class.
- `transfer.machine.drop-resumes-or-rolls-back` — **[GAP]** (#5657) a dropped connection resumes from the
  checkpoint; nothing lands until every object is verified; landing is all or nothing on the far side;
  an abandoned transfer removes its partial objects there and says so.
- `transfer.machine.not-to-clusters` — **[GAP]** (#5657) a cluster or Hugging Face is not a transfer
  target (it holds work packages, not projects); refused in words.

### Rights

- `transfer.rights-travel` — **[GAP]** (#5657) an item's rights record and `not_for_release` travel with
  it and cannot be loosened by a transfer; a copy into a shared project goes through the acting person's
  permission there (#4311).

### The app

- `transfer.app.drag-sidebar` — **[GAP]** (#5657, #2397) dragging items onto a folder or the header of
  another project's section in the sidebar moves them; ⌥ copies; ⌘⌥ is refused
  (`transfer.alias.not-between-projects`); the cursor badge shows which before the drop.
- `transfer.app.drag-items-and-canvas` — **[GAP]** (#5657) dragging from Items (every mode, the canvas
  included) onto another project's row behaves the same, through the one drop grammar
  (`sidebarDropOperation`) extended with the project check.
- `transfer.app.drop-checks-project` — **[GAP]** (#5657, #2397) the drop path compares the dragged item's
  project with the target's: same project, today's move/copy/alias; another project, the transfer.
- `transfer.app.progress-in-activity` — **[GAP]** (#5657, #4311) a transfer is one row in Activity with
  its phase in words (checking, copying N of M, verifying, sending the source to its Trash) and Stop
  (which rolls back).
- `transfer.app.result-sheet` — **[GAP]** (#5657) when a transfer cut anything or proposed a merge, a
  result sheet lists it (cuts by kind, proposals with Review…, types made); otherwise a quiet line
  ("Moved 12 items to Istmina. Undo").
- `transfer.app.undo-both-windows` — **[GAP]** (#5657) ⌘Z right after a transfer undoes it from the
  source's or the target's window.
- `transfer.app.drag-to-finder` — **[GAP]** (#4311) dragging items to the Desktop or a Finder window
  writes their originals through file promises streamed from the engine (folders as folders, notes as
  Markdown); nothing in the project changes.
- `transfer.app.drag-to-another-mac` — **[GAP]** (#5657, #2573) a project on another engine shown in
  the sidebar accepts drops as copies (no move badge); needs a host per project (#2573).

### MCP and CLI

- `transfer.mcp-cli.generated` — **[GAP]** (#5657) the transfer route, its dry run and its result are
  generated into the MCP (a `fichero_documents_transfer` tool) and the CLI (`fichero documents
  transfer`), printing the result report; no hand-written client.
- `transfer.mcp-cli.result-readable` — **[GAP]** (#5657) an agent can read a transfer's state and result
  by id and review its entity proposals with the existing knowledge-graph tools.

## Test matrix

| Leg | Pins | File |
|---|---|---|
| Backend (pytest), to write | a page with two passes, readings at three levels, a chosen reading, artifacts with legacy ids, a reading order, notes, a kind, claims and entities moves whole; counts and sha256 match; source in Trash labelled moved; undo restores both sides | `fichero-server/tests/unit/transfer/test_transfer_a_page_whole.py` |
| Backend, to write | verification failure rolls the target back; source delete failure compensates; a `writing` journal rolls back on open; a `verified` move resumes | `fichero-server/tests/unit/transfer/test_transfer_is_never_half_done.py` |
| Backend, to write | entity matched by Wikidata URI, by name, by none; proposals not merges; person marks kept; source keeps a still-mentioned entity, hides an unmentioned one | `fichero-server/tests/unit/transfer/test_transfer_knowledge.py` |
| Backend, to write | every cut listed (link, canvas position, workspace slot, partial group, inclusion, alias); no dangling id in either project after a move (a scan of every id column) | `fichero-server/tests/unit/transfer/test_transfer_cuts.py` |
| Backend, to write | refusals: not open, read-only, locked node, alias, same project, no permission | `fichero-server/tests/unit/transfer/test_transfer_refusals.py` |
| Backend, to write | models (in use refused, card rewritten), workflows with sub-workflows, document types by key, saved-search scope | `fichero-server/tests/unit/transfer/test_transfer_other_items.py` |
| Backend, to write | between machines: a package landed by a second engine on loopback; dropped connection resumes; landing all or nothing; source unchanged | `fichero-server/tests/unit/transfer/test_transfer_between_engines.py` |
| App (Swift Testing), to write | drop grammar across projects (move, ⌥ copy, ⌘⌥ refused), the project check, Activity row, result sheet from a stored result | `fichero/Tests/Unit/general/Views/Sidebar/` beside the drop-operation tests |
| App, real host | a drag between two open projects in the running app moves a page and the Items pane of each updates in place | the maintainer's run; an XCUITest in a GUI session |
| MCP / CLI | transfer, dry run and result through the generated tools | `fichero-mcp/tests/` |

## Open questions (each with a recommendation)

1. **Where does undo live?** *Recommend:* the transfer's record in both projects, the target's audit
   row as the transfer's audit, undo from either (as designed above).
2. **Aliases in the source pointing at moved items.** Trash them, or leave them broken and say so?
   *Recommend:* to the source's Trash, labelled and listed, back on undo — a dangling alias in the tree
   is a row that lies; the Trash keeps it recoverable.
3. **A model the source's recipe uses.** Refuse the move, or move and drop the step's choice?
   *Recommend:* refuse in words and offer a copy; changing what a recipe step uses is its own audited
   choice (`training.ab.use-this-audited`).
4. **Undo of a move after the target's copy changed.** *Recommend:* say so; offer "Put back in <source>
   and keep the copy in <target>"; never discard work done in the target.
5. **Name already used in the target folder.** *Recommend:* keep the name (folders already allow two
   items of one name, as `document.duplicate` into a folder does); workflows alone get " 2" because
   their names are looked up.
6. **Correction episodes (training data) for moved pages.** *Recommend:* they travel with the pages
   (ids mapped) so the target can train on them; the source's go to the Trash with their pages.
7. **Copying the same item twice into one project.** *Recommend:* a second, separate copy (the
   Finder's rule); `metadata.transferred_from` lets the result say "already copied here on <date>".
8. **Pulling from another machine** (dragging from a remote project into this one). *Recommend:* the
   same copy, the far engine packaging; waits on a host per project (#2573).

## Build order

Engine first, each slice pinned by its tests before the next:

1. **The Trash in the app** (`source/trash.md`): the engine routes exist; the app's Trash row, view and
   Put Back come early, because a move's safety is that its source lands somewhere a person can see.
   The engine's `trash.knowledge` (claims on trashed pages hidden) lands with it.
2. **The plan and the id map** (`transfer.action.dry-run`): walk a subtree, gather every row by kind,
   allocate ids, list cuts; no writes. Pins the inventory against every model keyed by document id.
3. **Copy within one engine** (`mode: copy`): write the target, files, vocabulary, verify, the record,
   the journal and roll-back; undo of a copy. Knowledge: claims travel, entities matched and proposed.
4. **Move within one engine**: the source's soft delete with "moved to", compensation, cuts in the
   source, undo of a move from either project.
5. **The app's drag between projects** (sidebar, Items, canvas): the project check, the badges, the
   ⌘⌥ refusal, the Activity row, the result sheet, ⌘Z.
6. **Other items**: models, workflows, document types, saved searches, Use This Project's Setup In….
7. **Drag out to the Finder** (file promises).
8. **Between machines**: the HTTPS carrier's write half and the package/land split (with
   `compute/transfer-and-results.md`'s slices), then the sidebar's remote projects (#2573).
