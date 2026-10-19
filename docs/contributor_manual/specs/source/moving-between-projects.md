# Moving and copying between projects and machines — Design Spec (#5657)

> Milestone: Library View
> Manual: TBD — a section of "Organising a project": dragging items to another project (a move) and
> ⌥-dragging them (a copy); what travels with a page and what is left behind and listed; how the
> people and places on a page join the other project's knowledge graph (proposed, never merged by
> themselves); undoing a move; copying to another Mac or a server; dragging items out to the Finder;
> the Trash (`safety/trash.md`).
>
> **Status: DRAFT — 2026-10-10, revised the same day** after an adversarial review (eleven
> findings: tables the id map forgot, the pending move's visibility in the source, Empty Trash and
> undo durability, linked files between machines, synced folders, episodes, vocabulary with one
> key and different fields); the id map's inventory is now code
> (`fichero_server/transfer/id_map_classification.py`). Issues: #2397 (move between projects), #4311 (copy between projects,
> and dragging out to the Finder), tracked by #5657. Written to be implemented next: every claim about
> the code is **VERIFIED** on disk at `52b7b1f65` with a path, or marked **INFERRED**. Related:
> `safety/trash.md` (the per-project Trash a move sends its source to), `ui/sidebar-crud.md` (drag
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
- **Each project has its own Trash, the always-there project included** (`safety/trash.md`).

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
  (`documents.py:1176`, `patch_workspace_items`). A canvas **link** item joins two other items by
  `source_item_id` / `target_item_id`, which may name documents, entities, claims or other canvas
  items (`models/canvas.py:160-186`). The retained 3D spatial rooms: `SpatialNode.source_id` names
  the item a node shows, `SpatialConnection.source_node_id` / `target_node_id` join two nodes, and
  a room id doubles as a folder id (`models/canvas.py:37-100`, #2293).
- **Palaeography and signs** (VERIFIED at `99adaab9a`). `HandAttribution` (`models/hands.py:55`:
  `hand_id`, `segment_id`) says which hand wrote a segment; `LetterformDescription`
  (`models/letterforms.py:55`: `segment_id`, `allograph_id`, `hand_id`, and `character`, which is
  text or a declared sign's id) describes one mark. `Hand` and `Allograph` are project records
  shared across sources. `DeclaredSign` (`models/signs.py:56`) is a sign in the project's sign list
  whose picture is a real segment on a real page (`picture_segment_id`).
- **Correction episodes** (VERIFIED at `99adaab9a`). The episode ledger is append-only JSONL inside
  the package, `<package>/episodes/YYYY-MM.jsonl` (`observability/episodes.py:65`), not a table. A
  record carries `episode_id`, `subject` (`document_id`, `document_ids`, `line_ids`, `artifact_id`,
  `stale_artifact_ids`, `target_id`, by caller), `run` (`thread_id`, `workflow_id`), and for a
  correction `corrects_episode_id`, for an invalidation `caused_by_episode_id`. `CheckVerdict`
  (`models/checking.py`) names an `episode_id`.
- **Synced folders** (VERIFIED at `99adaab9a`). `sync_files` (`sync_folder.py:112`, hand-written
  SQL, per library) ties a file in a synced folder to a `document_id`.
- **Every persisted id field, classified** (built at `af6fb01b6`): see "The id map" below.
- **Between machines.** The transfer core exists, pure and tested, for library sync
  (`workflows/library_sync.py`: content-addressed `SyncObject`, `SyncManifest`, `diff_manifests`,
  `SyncCheckpoint`; `library_sync_io.py` lands an object atomically with its hash re-checked), with two
  read-only routes (`api/routes/library/sync.py`). The write half, the HTTPS carrier to another
  Fichero and the list of paired machines are designed, not built (`compute.transfer.https-write-half`,
  `compute.target.add-fichero-mac`). Device pairing exists (`api/routes/auth/pairing.py`: a code, a
  paired device's own token). A host per library is not built (#2573).
- **Copy and move within one engine are built (build orders 2-4, 2026-10-10).** `POST /api/documents/transfer`
  (`api/routes/document/transfer.py`, action `document.transfer`, inverse `document.untransfer`) plans
  (`dry_run`), copies or moves a selection into another open project: `transfer/plan.py` gathers the set by
  `transfer/membership.py`'s join table and re-points every id by the classification;
  `transfer/copy.py` writes, verifies and records it (`TransferRecord`, `models/transfer.py`);
  `transfer/move.py` takes a move's source step (`document.transfer_out`, build order 4). Not built:
  the background job, the app's drag, out to the Finder. A copy between machines is built (2026-10-11,
  `transfer/remote.py`, `transfer/machines.py`, `api/routes/document/transfer_remote.py`; see the behaviours
  under "Between machines").

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
   as moved (`safety/trash.md`, `safety.trash.lists-what-and-why`). Cut what must be cut in the source
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
- **The pending step is visible in the source too.** Before writing the target, the engine also
  writes a **mirror journal row** in the source's `transfers` (same id, state `sending`, the items
  and the target); it becomes `verified` with the target's and `done` after the source's delete.
  Opening the source while a move is `verified`-not-`done` shows the pending step in the source's
  Activity, in words ("Moving 12 items to Istmina: copied and checked there; removing them here
  is waiting.", with Finish Now and Roll Back), and resumes it when the target is open. While a
  move of an item is pending, a second drag of that item (or of a folder holding it, or into it)
  is refused in words: "These items are already being moved to Istmina." The mirror row is what
  makes the refusal checkable from the source alone.
- **If the target write or verification fails,** every row and file the transfer wrote in the target is
  removed by the id map (they are new rows only this transfer made), the vocabulary entries it made are
  removed if nothing else uses them, and the source is untouched. The result says what failed.
- **If the source's soft delete fails after verification** (the source closed, a lock, a write
  refused), the engine retries once; if it still fails, the target's copy is rolled back as above and
  the move is reported as not done, in words, with the reason. A move never ends as a silent copy.

### The id map

**The source of truth is code, not this paragraph:**
`fichero-server/src/fichero_server/transfer/id_map_classification.py` classifies every persisted id
field — every field ending `_id`/`_ids` of every model in `Database._all_schema_models` and of every
model nested in one (an anchor inside a segment, a support inside a claim), the id-bearing fields
with other names (`Document.curated_items`, `PageLineMap.id`, `CanvasLayout.id`, a letterform's
`character`, …), every id column of every hand-written SQL table, and every id key of the episode
ledger — into one of five buckets, each with a one-line reason:

| Bucket | What the transfer does | Entries at `af6fb01b6` |
|---|---|---|
| `MAPPED` | the row travels with the page; the id is re-pointed through the map; when it names something outside the set, that edge is cut and listed | 162 |
| `CUT` | the row stays in the source (a research workspace, a chat, a synced folder, a prediction queue); when it names a moved item, that entry is cut in the source on a move and listed | 21 |
| `RECOMPUTED` | a derived id, computed again in the target (legacy pass and segment ids, the canvas layout's composite id, a reading pair's shared key, audit pointers re-pointed to the transfer's audit row) | 6 |
| `PROJECT_VOCAB` | names a per-project record (a hand, an allograph, a declared sign, an interpretive framework, a bibliography entry, a sign map's signs): matched by key in the target, made there if missing | 11 |
| `NOT_DOCUMENT_SCOPED` | an engine-wide record, a person, an external identifier, or the source's own history (runs, jobs, the audit chain, the knowledge-graph undo log): never re-pointed; kept as text naming the source project where its row travels | 98 |

`fichero-server/tests/unit/transfer/test_every_id_field_is_classified.py`
(`transfer.inventory.every-id-classified`) fails when a new id field appears unclassified, and
when a classified one no longer exists. The plan step (build order 2) and the "no dangling id"
scan of `test_transfer_cuts.py` read the same table. The paragraph below is its summary.

Every row in the set gets a new id; nothing keeps a source id in the target except
`metadata.transferred_from`. The map re-points, inside the set: `parent_id`, `alias_target_id`,
`document_id`, `pass_id`, `parent_segment_id`, `source_artifact_id`, `rendition_id`, segment ids inside
anchors and reading-order entries (`order_id`, `segment_id`, `parent_entry_id`), match and forwarding
pairs, segment versions' `old_segment_id`, reading choices, typed-link ends, canvas `folder_id` and
`item_id` (and the composite id), workspace item targets, claim `source_document_id`/`source_ids` and
entity ids, annotation and note targets, `metadata.attribute_sources` references to runs and proposals
that travel, hand attributions' and letterform descriptions' `segment_id`, canvas link items'
`source_item_id`/`target_item_id` and spatial nodes' `source_id` and connections' node ids (both
ends in the set), and the episode ledger's ids. Special cases:

- **Derived ids** (`legacy_pass_id`, `legacy_segment_id`) are computed again from the new artifact id,
  never mapped as plain strings.
- **Audit pointers.** A segment forwarding's or version's `audit_id` points into the source's audit
  chain, which does not travel. In the target it is re-pointed to the transfer's own audit row, and the
  original is kept beside it (`metadata.source_audit_id`) so the history reads "carried from <project>
  on <date>, earlier history there".
- **Run ids** (`run_id`, workflow runs, job ids) name runs recorded in the source; they are kept as
  text with the source project named, not re-pointed (a run is history, not a row that travels).
- **An id outside the set** is never written into the target: the edge is cut and listed.
- **Project vocabulary** (hands, allographs, declared signs, reading kinds and levels, document
  types, link types, entity types, interpretive frameworks, bibliography entries) is never mapped
  as a string: each record used by the set is matched in the target by its key (a hand's label, an
  allograph's character and name, a sign's code point or sign-list reference, a kind's key, a
  type's key) and made there if missing. **Same key, different fields:** the target's record is
  kept as it is, and the result lists the difference ("reading level `line` here has label
  'Line'; in <source> 'Renglón'") — the carried rows point at the target's record
  (`transfer.page.vocab-same-key-differs`).

### What travels with a page (always)

| Kind | Rows | Notes |
|---|---|---|
| the node | `Document` (and its subtree) | name, kind, `prototype_key`, `attributes`, `metadata` incl. `attribute_sources`, sort order |
| the file | the original | in-package: copied byte for byte, sha256 checked; linked: the reference (path, bookmark) only |
| pictures | thumbnails, display images | regenerated in the target (caches keyed by id) |
| passes and lines | `SegmentPass`, `Segment`, `SegmentMatch`, `SegmentForwarding`, `SegmentCarry`, `SegmentVersion`, `SegmentPassChoice`, `PageLineMap` | ids mapped; the chosen pass stays chosen |
| readings | `ContentRepresentation` at every level and kind, `ReadingChoice`, `ContentRepresentationRevision`, `EditorialFact`, campaigns (`Campaign`, `CampaignMembership`, `ReadingCampaigns`) | the counted reading stays counted; kinds and levels matched by key, made if missing; same key with different fields keeps the target's and lists the difference |
| hands and letterforms | `HandAttribution`, `LetterformDescription` | travel with their segments, `segment_id` mapped; the `Hand` and `Allograph` they name are project vocabulary, matched by label (a hand) or character and name (an allograph) in the target, made if missing |
| declared signs | `DeclaredSign` whose `picture_segment_id` is a moved segment, or used by a moved reading's `sign_map` or a letterform's `character` | carried like a document type: matched in the target by code point or sign-list reference, made if missing with its picture (the target's `picture_segment_id` is the carried segment's new id); on a move the source's sign keeps a still of its picture and reads "picture moved to <project>" — never a dangling id |
| correction episodes | the lines of `<package>/episodes/*.jsonl` whose `subject` names a moved page, segment or artifact, and the corrections and invalidations that cite them | copied into the target's ledger with new `episode_id`s, every id in them mapped; a `CheckVerdict`'s `episode_id` follows the map; on a move the source's lines stay (the ledger is append-only) and a `transferred` line records the move |
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
resting on the moved pages go to the Trash with their pages: hidden, not deleted (`safety.trash.dependants-go-with-their-source`).
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
- a recipe override or Find the Documents proposal in the source naming a moved folder;
- a **canvas link item** (`CanvasItem`, kind `link`) whose one end moves and whose other end stays:
  cut in the source, not carried; a link whose both ends move travels with both ids mapped;
- a **spatial node** (`SpatialNode`) in a room that stays whose `source_id` names a moved item, and
  every `SpatialConnection` touching it; a connection whose both nodes travel is mapped;
- a moved document's **tie to a synced folder** (its `sync_files` row): severed in the source, the
  file left on disk as it is, and listed ("no longer synced to <folder>"); the target does not
  inherit the folder (it is the source's), so the moved document is not synced there until a
  person ties it again;
- a research workspace's notes, a chat's scope, a graph-inclusion setting, a prediction review or a
  pattern naming a moved item (the `CUT` bucket of the id map).

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
- **Undo is durable** (this spec's decision, flagged for the maintainer to confirm): undo of a
  transfer is not a ⌘Z-session reflex; it survives quitting the app and restarting the engine,
  because it is read from the action history and the `transfers` record in both projects. A move
  stays undoable from either project for as long as its source items are in the source's Trash.
  Emptying them makes the move permanent: Empty Trash says so before it runs
  (`safety.trash.empty-names-moved-items`), the record in both projects then says "made permanent
  on <date>", and undo is refused in words. A copy stays undoable while the copy is live in the
  target. *Why durable:* a move is a large act on two files; the person who finds a mistake
  tomorrow must still be able to take it back, and the Trash already holds everything undo needs.

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
- **Linked files.** An item whose original is linked (kept at its own path outside the package)
  travels as its reference only. Between machines that path is a path on the source machine: the
  result says so per item ("linked file: the original stays at /Users/… on <source machine> and may
  not open here"), and the far side shows the item as linked-elsewhere until a person relinks or
  copies the original in. Nothing pretends the file arrived.
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

- `transfer.action.one-route` — **[PARTIAL]** (#5657, #2397) `POST /api/documents/transfer` runs one audited
  action `document.transfer` (items, source, target, target parent, mode, dry run); the app, MCP and CLI
  call it and nothing else; it runs as one background job beyond a handful of nodes and `GET
  /api/documents/transfer/{id}` returns its state and result. Built (build orders 2-4): the route and the audited action `document.transfer` (`api/routes/document/transfer.py`), copy and move, generated into the CLI and MCP; `test_transfer_a_page_whole.py`, `test_transfer_a_move.py`. *Not built: the background job and `GET /api/documents/transfer/{id}`.*
- `transfer.action.dry-run` — **[OK]** (#5657) `dry_run: true` writes nothing and returns the plan:
  counts by kind, files and bytes, vocabulary to be made, entity matches, every cut, every refusal. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_dry_run_writes_nothing_and_says_what_a_copy_would
- `transfer.action.refusals-in-words` — **[PARTIAL]** (#5657) refused in words, changing nothing: a project
  not open (`DatabaseManager.is_open`), no write permission in the target (or the source, for a move), a
  locked node (`_reject_if_document_read_only`), a target that is not a live folder, the same project
  as source and target (that is `document.move`/`document.duplicate`), an alias between projects. Built (build orders 2-4): not open, same project, unknown or trashed item, alias, locked node, target not a folder, an item a pending move holds; a move checks write permission in the source; `test_transfer_refusals.py`. *Not pinned: no write permission in the target or the source.*
- `transfer.action.verify-then-delete` — **[OK]** (#5657, #2397) a move soft-deletes the source's items
  only after the target's copy is written and verified (counts per kind, sha256 per file, every mapped
  id resolving); a failed verification rolls the target back and leaves the source untouched. Built (build order 4): the source's items go to its Trash only after the target's copy is read back; `test_transfer_a_move.py`::test_a_move_lands_whole_and_sends_the_source_to_its_trash_labelled, `test_transfer_is_never_half_done.py`::test_a_failure_after_half_the_writes_leaves_the_target_with_nothing
- `transfer.action.compensates` — **[OK]** (#5657) if the source's soft delete fails after
  verification, it is retried once, then the target's copy is rolled back and the move reported as not
  done with the reason; a move never ends as a silent copy. Built (build order 4): the source step (`document.transfer_out`, one source transaction) is tried twice, then the target's committed copy is removed by the record's `written` rows and the move reported as not done; `test_transfer_is_never_half_done.py`::test_a_move_whose_source_step_fails_twice_takes_its_copy_back
- `transfer.action.journal-recovers` — **[OK]** (#5657) the transfer's record is written in the target
  as `writing` before any row, `verified` after verification, `done` after the source's delete; on
  opening a project a `writing` transfer is rolled back and a `verified` move resumes its source step. Built (build orders 3-4): `writing` rolled back on open (files removed); a copy left `verified` closed; a move left `verified` finishes its source step when both projects are open, from either side, and waits otherwise; `test_transfer_is_never_half_done.py`
- `transfer.action.record-in-both` — **[OK]** (#5657) each transfer is one record in each project
  (same id): the id map, files and proposals in the target; items, mode and target in the source. Built (build orders 2-3): `TransferRecord` in each project, same id; `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole
- `transfer.action.provenance` — **[OK]** (#5657) every node written by a transfer records
  `metadata.transferred_from` (source project id, node id, transfer id, when, who). Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole
- `transfer.action.undo-copy` — **[PARTIAL]** (#5657, #4311) undoing a copy sends the copy to the target's
  Trash and withdraws its entity proposals; redo copies again. Built (build orders 2-3): undo (`document.untransfer`) sends the copies to the target's Trash and withdraws its proposals; redo replays the copy; `test_transfer_a_page_whole.py`::test_undo_of_a_copy_sends_it_to_the_targets_trash. *Not built: removing vocabulary the copy made when nothing else uses it.*
- `transfer.action.undo-move` — **[PARTIAL]** (#5657, #2397) undoing a move puts the items back in the source
  from its Trash, restores the cut edges from the record and sends the target's copy to the target's
  Trash; offered from either project; refused in words when the source's items were emptied since;
  when the target's copy changed since, says so and offers to put the source back keeping the copy. Built (build order 4): `document.untransfer` from the target's `document.transfer` row or the source's `document.transfer_out` row puts the source's items back from its Trash with every cut edge and sends the copy to the target's Trash; refused in words when the other project is closed, when already undone, and when the source's items were emptied; `test_transfer_a_move.py`. *Not built: saying so when the target's copy changed since, and the offer to keep it (open question 4).*
- `transfer.action.batched-and-gentle` — **[GAP]** (#5657) a large transfer writes in batches of
  top-level items, hashes and copies at background priority and yields to the person's work
  (the auto-throttle rule), with progress per batch.
- `transfer.action.selection-is-one-transfer` — **[GAP]** (#5657) a multi-item selection is one
  transfer, one record, one undo, one result.
- `transfer.action.pending-visible-in-source` — **[PARTIAL]** (#5657) a move writes a mirror journal row in
  the source (same id, `sending` → `verified` → `done`) before it writes the target; opening the
  source while the move is `verified`-not-`done` shows the pending step in the source's Activity in
  words, with Finish Now and Roll Back, and resumes it when the target is open. Built (build order 4): the mirror row `sending` → `verified` → `done` in the source, written before the target; a pending move resumes when both are open (`test_transfer_is_never_half_done.py`). *Not built: the pending step in the source's Activity, in words, with Finish Now and Roll Back.*
- `transfer.action.second-drag-refused` — **[OK]** (#5657) while a move of an item is pending, a
  second transfer of that item, of a folder holding it, or into it, is refused in words ("These
  items are already being moved to <project>."), checked from the source's mirror row alone. Built (build order 4): `test_transfer_refusals.py`::test_a_second_drag_of_an_item_a_pending_move_holds_is_refused, ::test_a_drop_into_a_folder_a_pending_move_holds_is_refused
- `transfer.action.undo-durable` — **[PARTIAL]** (#5657) undo of a transfer survives quitting the app and
  restarting the engine: it is found from the action history and the `transfers` record in either
  project, and a move stays undoable while its source items are in the source's Trash; once they
  are emptied (`safety.trash.empty-names-moved-items`) the record says "made permanent" and undo is
  refused in words. Decided in this spec, flagged for the maintainer (open question 9). *Test:*
  move, restart the engine, undo from the target's window: both sides restored. Built (build order 4): undo is read from the audit row and the `transfers` record in either project, so it does not depend on the session; refused in words once the source's items were emptied (`test_transfer_a_move.py`::test_undo_of_a_move_is_refused_once_the_source_trash_was_emptied). *Not pinned: undo after an engine restart; the record saying "made permanent" when the Trash is emptied.*
- `transfer.inventory.every-id-classified` — **[OK]** (#5657) every persisted id field (model fields
  ending `_id`/`_ids` with nested models, id-bearing fields with other names, hand-written SQL id
  columns, episode-ledger id keys) is in one bucket of
  `fichero_server/transfer/id_map_classification.py` with a reason; a new unclassified one, or a
  stale entry, fails `fichero-server/tests/unit/transfer/test_every_id_field_is_classified.py`.

### What travels with a page

- `transfer.page.whole-subtree` — **[OK]** (#5657, #2397) a node travels with its live descendants;
  trashed descendants stay in the source's Trash and are listed. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole (a trashed page stays and is listed)
- `transfer.page.files` — **[OK]** (#5657, #4311) an in-package original is copied byte for byte under
  the target's `files/` and checked by sha256; a linked original travels as its reference (path and
  bookmark) and the result says it is linked; thumbnails and display images regenerate in the target. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole (in-package copied and sha256-checked; linked travels as its reference); pictures regenerate from the copy
- `transfer.page.passes-and-lines` — **[PARTIAL]** (#5657) every pass and segment travels with its matches,
  forwardings, carries, versions, pass choice and line map, ids mapped; the chosen pass stays chosen. Built (build orders 2-3): built for every row the join table names (`transfer/membership.py`); pinned for passes, segments and parents, `test_transfer_a_page_whole.py`. *Matches, forwardings, carries, versions and the line map are carried by the same code but not pinned by a test.*
- `transfer.page.readings-every-level` — **[OK]** (#5657) every reading (`ContentRepresentation`) at
  every level and kind travels, with its `ReadingChoice`; a reading kind or level missing in the target
  is made there. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole (two levels, a level made in the target, the counted reading)
- `transfer.page.artifacts` — **[PARTIAL]** (#5657) every artifact travels; `legacy_pass_id` and
  `legacy_segment_id` ids are derived again from the new artifact id, never mapped as strings. Built (build orders 2-3): every artifact travels; legacy pass and segment ids are derived again from the new artifact id (`transfer/plan.py`, `_allocate`); `test_transfer_a_page_whole.py` pins the artifact. *The legacy-id derivation is not pinned by a test.*
- `transfer.page.attributes-and-sources` — **[PARTIAL]** (#5657) attributes travel with their
  `attribute_sources` (who set each, a person's mark kept as a person's). Built (build orders 2-3): `attributes` travel as they are and `metadata` (with `attribute_sources`) has every id of the set re-pointed. *Not pinned by a test.*
- `transfer.page.kind-matched-by-key` — **[OK]** (#5657) the node's document type is matched by key in
  the target; a missing type is made with its fields and parent chain; the result lists types made. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole (a missing type made with its parent chain)
- `transfer.page.notes-and-marks` — **[PARTIAL]** (#5657) notes, annotations and anchors on the page travel. Built (build orders 2-3): annotations, notes and anchors by the join table; `test_transfer_a_page_whole.py` pins an annotation and anchors. *Notes on a page are carried but not pinned.*
- `transfer.page.reading-orders` — **[PARTIAL]** (#5657) a reading order wholly in the set travels; entries
  pointing outside the set are cut and listed. Built (build orders 2-3): an order and its entries travel; an entry naming a segment left behind is cut and listed (`membership.JOINS`). *Not pinned by a test.*
- `transfer.page.audit-pointers` — **[PARTIAL]** (#5657) a segment version's or forwarding's `audit_id` is
  re-pointed to the transfer's audit row in the target, the original kept as `metadata.source_audit_id`. Built (build orders 2-3): a carried version's or forwarding's `audit_id` points at the transfer's own audit row. *The original is kept on the target's `TransferRecord.source_audits`, not `metadata.source_audit_id` (neither row has a metadata field); not pinned by a test.*
- `transfer.page.re-embedded` — **[GAP]** (#5657) the target embeds the carried pages in the background;
  search finds them there when it is done.
- `transfer.page.hands-and-letterforms` — **[PARTIAL]** (#5657) every `HandAttribution` and
  `LetterformDescription` on a moved segment travels with its `segment_id` mapped; the hands and
  allographs they name are matched in the target by label (a hand) or character and name (an
  allograph) and made there if missing; rival attributions all travel. Built (build orders 2-3): attributions and descriptions travel with their segments; hands matched by label, allographs by character and name, made if missing; `test_transfer_a_page_whole.py` pins a hand made in the target. *Letterform descriptions are not pinned.*
- `transfer.page.declared-signs` — **[GAP]** (#5657) a declared sign whose picture segment moves, or
  that a moved reading or letterform uses, is carried into the target like a document type:
  matched by code point or sign-list reference, made if missing with its picture pointing at the
  carried segment's new id; on a move the source's sign keeps a still of its picture and says
  "picture moved to <project>". No sign in either project names a segment that is not there.
- `transfer.page.episodes` — **[GAP]** (#5657) the correction-episode ledger lines whose subject is a
  moved page, segment or artifact, and the corrections and invalidations citing them, are copied
  into the target's ledger with new `episode_id`s and every id mapped; a `CheckVerdict`'s
  `episode_id` follows the map; the source's lines stay (append-only) with a `transferred` line.
- `transfer.page.vocab-same-key-differs` — **[OK]** (#5657) a reading kind or level, document type,
  link type, hand or other project vocabulary with the same key in the target but different fields
  keeps the target's record; the carried rows point at it and the result lists the difference. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole (reading level `as_written`)

### Knowledge

- `transfer.entities.claims-travel` — **[OK]** (#5657) every claim resting on a moved page
  (`source_document_id` or `source_ids`) travels with its curation state and maker. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole
- `transfer.entities.match-authority-then-name` — **[PARTIAL]** (#5657) each carried entity is matched in the
  target first by a shared `same_as` authority URI, then by type and name; every match is named with its
  reason. Built (build orders 2-3): authority id (`same_as`), then type and name; `test_transfer_a_page_whole.py` pins the Wikidata match. *The match by name is not pinned.*
- `transfer.entities.match-is-proposed` — **[OK]** (#5657) a match is written as an
  `EntityMatchCandidate` pairing the carried entity (written new) with the target's; never merged by the
  transfer; accepting is the existing audited merge; rejecting is remembered. Built (build orders 2-3): `EntityMatchCandidate`, method `transfer`; `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole
- `transfer.entities.no-match-is-new` — **[PARTIAL]** (#5657) an entity with no match is written new. Built (build orders 2-3): every carried entity is written new; with no match none is proposed (`result.entities_new`). *Not pinned on its own.*
- `transfer.entities.person-marks-kept` — **[PARTIAL]** (#5657) confirmations, corrections, rejections and
  the merge history of carried entities and claims travel as a person set them. Built (build orders 2-3): rows travel as they are; `test_transfer_a_page_whole.py` pins an entity's verified state, a claim's state and maker. *Merge records not pinned.*
- `transfer.entities.source-keeps-while-mentioned` — **[GAP]** (#5657) on a move the source keeps an
  entity while a live page still mentions it; one whose every mention is in the Trash is hidden with them
  and pruned only when the Trash is emptied.

### Cuts

- `transfer.cut.listed-never-silent` — **[PARTIAL]** (#5657) every edge that crosses the set's edge (links,
  note links, citations, research-workspace inclusions, recipe overrides, proposals naming a moved
  folder) is cut and listed in the result by name; nothing in either project points at an id that is
  not there. Built (build orders 3-4): a copy carries no edge out of the set and lists each; a move cuts in the source canvas places, canvas links, workspace slots, aliases and synced-folder ties and lists each; `test_transfer_a_page_whole.py`::test_no_carried_row_names_a_missing_row, `test_transfer_a_move.py`. *Not built: partial groups, research-workspace inclusions, recipe overrides, the CUT bucket's rows.*
- `transfer.cut.canvas-position` — **[OK]** (#5657) the moved items' positions on the source folder's
  canvas are dropped; positions inside a moved folder's own canvas travel; items land in the target by
  its canvas's arrange. Built (build order 4): `test_transfer_a_move.py`::test_a_move_lands_whole_and_sends_the_source_to_its_trash_labelled; positions inside a moved folder travel (`test_transfer_a_page_whole.py`)
- `transfer.cut.workspace-slot` — **[OK]** (#5657) a workspace's slot naming a moved item is removed and
  listed; the workspace stays. Built (build order 4): `test_transfer_a_move.py`::test_a_move_lands_whole_and_sends_the_source_to_its_trash_labelled
- `transfer.cut.partial-group` — **[GAP]** (#5657) moving some pages of a group takes them out of the
  group; the group keeps the rest; listed.
- `transfer.cut.canvas-links` — **[OK]** (#5657) a canvas link item (`CanvasItem.source_item_id` /
  `target_item_id`) travels with both ends mapped when both ends move; when one end stays, the
  link is cut in the source (a move) or not carried (a copy) and listed. Built (build orders 3-4): both ends moved, mapped; one end staying, not carried (copy) and cut in the source (move), listed; `test_transfer_a_page_whole.py`, `test_transfer_a_move.py`
- `transfer.cut.spatial-nodes` — **[GAP]** (#5657) a spatial node whose `source_id` names a moved item
  travels mapped when its room (a moved folder) travels, else is cut and listed; a
  `SpatialConnection` is mapped when both its nodes travel and cut and listed when one stays.
- `transfer.cut.sync-folder-tie` — **[OK]** (#5657) a moved document's tie to a synced folder
  (`sync_files`) is severed in the source, its file left on disk untouched, and listed; the target
  does not inherit the tie. Built (build order 4): `sync_folder.sever`/`retie`; `test_transfer_a_move.py`

### Aliases

- `transfer.alias.within-a-project` — **[PARTIAL]** (#5657) Make Alias and ⌘⌥-drag make an alias within
  a project. Built: `models/node_aliases.py`, the bookmarks route, `sidebarDropOperation`'s ⌘⌥ case and
  the Make Alias menu items. *Not built: the check that the drop's target is in the same project.*
- `transfer.alias.not-between-projects` — **[PARTIAL]** (#5657) a ⌘⌥-drop onto another project or another
  machine is refused in words, "Aliases stay within a project.", with a Copy button; the engine refuses
  an alias in a transfer's items the same way. Built (build orders 2-3): the engine refuses an alias in a transfer's items, "Aliases stay within a project."; `test_transfer_refusals.py`. Built (build order 5): the app refuses a ⌘⌥-drop onto another project in those words, before asking the engine, with Copy Instead; `ProjectTransferStoreTests`::anAliasIsRefused. *Not built: the same between machines.*
- `transfer.alias.inside-set-rewritten` — **[OK]** (#5657) an alias in the set whose target is in the
  set travels with its target id rewritten; one whose target is not in the set does not travel and is
  listed. Built (build orders 2-3): `test_transfer_a_page_whole.py`::test_a_copied_folder_arrives_whole
- `transfer.alias.source-aliases` — **[OK]** (#5657) an alias in the source pointing at a moved item goes
  to the source's Trash labelled "alias to <item>, moved to <project>", is listed, and comes back on undo
  (recommended, open question 2). Built (build order 4): to the source's Trash "moved to", listed, back on undo; `test_transfer_a_move.py`

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

- `transfer.machine.copy-only` — **[PARTIAL]** (#5657, #4311) a transfer to another engine copies; the
  source is never changed by it; no modifier makes it a move. Built (2026-10-11): `POST
  /api/documents/transfer/to-machine` (the library header names the source) has no mode; the source keeps only
  its record (`transfers`, role source, `sending` then `done`, naming the machine) and the send's audit row;
  `fichero-server/tests/unit/transfer/test_transfer_between_machines.py`. *Not built: the app's drop.*
- `transfer.machine.one-code-path` — **[PARTIAL]** (#5657, #5239) the source plans and packages, the target
  lands and verifies with the same code a transfer on one engine uses. Built: the source packages what
  `plan.gather_set` reads (the rows, the project vocabulary, the entities' authority links) as one rows object
  beside each in-package original; the far engine makes those rows a project of their own in its incoming
  folder and lands it with `build_plan` + `copy_into_target` (`transfer/remote.py`); the counts and cuts equal
  a copy's on one engine; `fichero-server/tests/unit/transfer/test_transfer_between_machines.py`. *Not built: the background job.*
- `transfer.machine.carriers-reused` — **[PARTIAL]** (#5657, #5239) the package travels by the HTTPS carrier
  through the one transfer core: only missing objects, verified on arrival, resumable from the checkpoint.
  Built: a push from the sending engine; the far engine opens the copy (`POST
  /api/documents/transfer/incoming`, answering the objects it lacks by `diff_manifests`, its `SyncCheckpoint`
  and `pending_objects`), takes each (`PUT …/incoming/{id}/objects/{sha256}`, re-hashed by `land_object`) and
  lands it (`POST …/incoming/{id}/land`); `fichero-server/tests/unit/transfer/test_transfer_between_machines.py`. *Not built: streaming an object larger than memory.*
- `transfer.devices-are-engine-wide` — **[OK]** a paired device (`devices.user_id`, `devices.paired_by_device_id`, which device minted it) belongs to the engine, not to a project: a move or copy never carries, re-points or cuts one (`NOT_DOCUMENT_SCOPED` in `transfer/id_map_classification.py`). Test: `fichero-server/tests/unit/transfer/` (`test_every_raw_sql_id_column_is_classified`).
- `transfer.machine.paired-only` — **[PARTIAL]** (#5657, #5238) the far engine is a paired device; what lands
  is stamped by the far engine with the paired person; versions must match. Built: `POST /api/machines/pair`
  (a `.ts.net` address and the code the other Mac's Fichero shows) runs the existing device pairing with this
  engine as the device and keeps the machine and its token in the Keychain (`transfer/machines.py`); `GET
  /api/machines` lists them; the far engine's routes take its device token, and its landing is its own audited
  action `document.transfer_in` with its caller as the actor; a different contract sha256 is refused; `fichero-server/tests/unit/transfer/test_transfer_between_machines.py`.
  *Not built: the app's pairing sheet; forgetting a machine.*
- `transfer.machine.egress-gated` — **[PARTIAL]** (#5657, #5239) a copy off this machine passes the one
  egress gate: a project that may not leave this machine is refused; another of the person's Macs is
  the "your own machine" class. Built, conservatively: every send needs the person's yes for the pages
  (`pages_may_leave`, as reading at scale and training do), and nothing is sent while the engine works offline;
  `fichero-server/tests/unit/transfer/test_transfer_between_machines.py`. *Not built: the one gate, the "your own machine" class asked once per project, a project marked
  "may not leave this machine" (no such mark exists yet).*
- `transfer.machine.drop-resumes-or-rolls-back` — **[PARTIAL]** (#5657) a dropped connection resumes from the
  checkpoint; nothing lands until every object is verified; landing is all or nothing on the far side;
  an abandoned transfer removes its partial objects there and says so. Built: a drop leaves the source's
  record `sending` with why and the far side's arrived objects kept; `resume` with its id sends only the rest; a
  landing that fails rolls back there (the one copy's journal) and lands on retry sending nothing; `DELETE
  …/incoming/{id}` abandons, removing what arrived, and says how many; `fichero-server/tests/unit/transfer/test_transfer_between_machines.py`. *Not built: abandoning by itself
  after a set time.*
- `transfer.machine.linked-files-said` — **[PARTIAL]** (#5657) a copy to another machine of an item whose
  original is linked says, per item, that the path is on the source machine and may not open
  there; the far side shows it as linked elsewhere until relinked or copied in. Built: the result's
  `linked_elsewhere` says it per item, and the node carries `metadata.linked_elsewhere` (machine, path); `fichero-server/tests/unit/transfer/test_transfer_between_machines.py`.
  *Not built: the app showing it; relinking.*
- `transfer.machine.incoming-bounded` — **[PARTIAL]** (#5657, security review 2026-10-11) a far peer cannot
  fill this disk: a copy is refused (413) before anything is written when one object is over 512 MB, the whole
  over 20 GB or 100,000 objects, or this disk would keep less than 5 GB free once it and every other copy still
  arriving had arrived; an object's PUT longer than the size the copy declared for it is refused (413), never
  read past that size and never kept; a copy nothing arrived for in a week is abandoned the next time one opens
  (`remote.sweep_stale`); `fichero-server/tests/unit/transfer/test_incoming_copy_security.py`. *Not built: a per-person quota; the limits as a setting.*
- `transfer.machine.incoming-confined` — **[PARTIAL]** (#5657, security review 2026-10-11) what arrives stays
  in its copy's folder: a copy's id is 32 hex characters and an object's hash 64 (refused otherwise, in the
  route and in `remote`), every object is named `records.json` or under `files/` with no `..` (refused at
  open), and a linked original's path, a path on the source machine, never becomes a node's `path` here (only
  `metadata.linked_elsewhere`), so a peer cannot point a node at a file on this machine; the landing is the
  caller's own audited action (`document.transfer_in`, its actor on the record and on every node); only the
  engine's owner may pair this engine out, list its machines or send to one (a paired device and a collaborator
  are refused 403), and the incoming routes need the write role in the project (a viewer is refused 403) and
  answer no anonymous caller from another machine; `fichero-server/tests/unit/transfer/test_incoming_copy_security.py`. *Not built: a row's own `created_by` is kept as the
  source wrote it (human work keeps its author), which `compute.land.server-sets-the-maker` would replace for
  machine results.*
- `transfer.machine.not-to-clusters` — **[PARTIAL]** (#5657) a cluster or Hugging Face is not a transfer
  target (it holds work packages, not projects); refused in words. Built by construction: the only target is a
  paired machine (`GET /api/machines`), and an address that is not a tailnet name is refused when pairing.
  *Not pinned for a cluster by name.*
- `transfer.machine.owners-devices-send` — **[GAP]** (#5661, ruled 2026-10-17) sending to a paired machine is allowed from any device the owner owns (phone and Mac alike, including a phone connected remotely in single-user mode), with the same copy features as the owner's Mac; other roles stay as built (a non-owner cannot pair out or send). Keep-author stands (rows keep their source `created_by`). Not built: its test (an owner's paired-device token sends; an editor's does not) is written with the feature.
- `transfer.machine.forget-machine` — **[PARTIAL]** (#5661, ruled 2026-10-17; engine built: `DELETE /api/machines/{id}`, owner only, pinned by `fichero-server/tests/unit/transfer/test_forget_machine.py`; the app's Forget machine button is not built) a paired machine can be forgotten: "Forget machine" removes its saved token from this Mac's Keychain and drops it from `GET /api/machines`, after which a send to it is refused as unpaired. It does not revoke the device on the far Mac (that is that Mac's Sharing list) and says so in one sentence.

### Rights

- `transfer.rights-travel` — **[GAP]** (#5657) an item's rights record and `not_for_release` travel with
  it and cannot be loosened by a transfer; a copy into a shared project goes through the acting person's
  permission there (#4311).

### The app

- `transfer.app.drag-sidebar` — **[PARTIAL]** (#5657, #2397) dragging items onto a folder or the header of
  another project's section in the sidebar moves them; ⌥ copies; ⌘⌥ is refused
  (`transfer.alias.not-between-projects`); the cursor badge shows which before the drop. Built (build order 5): a
  folder row and a project's row start the transfer (`ProjectTransferStore.beginIfAcrossProjects`, called first by
  `handleDropIntoFolder` and `handleLibraryHeaderItemDrop`; a project's row lands in its Sources folder);
  `ProjectTransferStoreTests`, `ProjectTransferDropGrammarTests`. *Not built: the cursor badge across projects (the
  hover cannot read which project the drag came from, so ⌘⌥ still shows the alias badge until the drop refuses it).*
- `transfer.app.drag-items-and-canvas` — **[PARTIAL]** (#5657) dragging from Items (every mode, the canvas
  included) onto another project's row behaves the same, through the one drop grammar
  (`sidebarDropOperation`) extended with the project check. Built (build order 5): Items' rows drag onto another
  project's sidebar row as above, and Items' folder cells and pane take a drop of another project's items the same
  way (`applyCellDrop`, `applyPaneDrop`). *Not built: the canvas's own drops.*
- `transfer.app.drop-checks-project` — **[OK]** (#5657, #2397) the drop path compares the dragged item's
  project with the target's: same project, today's move/copy/alias; another project, the transfer. Built (build
  order 5): `ProjectTransferStore.sourceProject` finds the open project whose loaded documents hold every dragged
  id (ids are UUIDs; the drag payload is unchanged); `ProjectTransferStoreTests`::ownItemsAreNotATransfer
- `transfer.app.progress-in-activity` — **[GAP]** (#5657, #4311) a transfer is one row in Activity with
  its phase in words (checking, copying N of M, verifying, sending the source to its Trash) and Stop
  (which rolls back).
- `transfer.app.result-sheet` — **[PARTIAL]** (#5657) when a transfer cut anything or proposed a merge, a
  result sheet lists it (cuts by kind, proposals with Review…, types made); otherwise a quiet line
  ("Moved 12 items to Istmina. Undo"). Built (build order 5): every drop opens a small sheet
  (`ProjectTransferSheet`) with the dry run's plan (what goes, what is cut and listed, the merges proposed), then
  Move or Copy and the result in words; a refusal shows the engine's sentence; `OnboardingScreenshotsTests` writes
  `13-move-between-projects.png`. *Not built: Review… on a proposal, and the types made.*
- `transfer.app.undo-both-windows` — **[PARTIAL]** (#5657) ⌘Z right after a transfer undoes it from the
  source's or the target's window. Built (build order 5): the window the drop was made in registers the step
  (`ActionUndo`, the target's audit row the result names, undone through the target);
  `ProjectTransferStoreTests`::undoTakesItBack. *Not built: ⌘Z from the other project's window.*
- `transfer.app.drag-to-finder` — **[GAP]** (#4311) dragging items to the Desktop or a Finder window
  writes their originals through file promises streamed from the engine (folders as folders, notes as
  Markdown); nothing in the project changes.
- `transfer.app.drag-to-another-mac` — **[GAP]** (#5657, #2573) a project on another engine shown in
  the sidebar accepts drops as copies (no move badge); needs a host per project (#2573).

### MCP and CLI

- `transfer.mcp-cli.generated` — **[PARTIAL]** (#5657) the transfer route, its dry run and its result are
  generated into the MCP (a `fichero_documents_transfer` tool) and the CLI (`fichero documents
  transfer`), printing the result report; no hand-written client. Built (build orders 2-3): the route, its dry run and its result are generated into the MCP and the CLI (`fichero-mcp`/`fichero-cli` generated surfaces). *Not pinned by an MCP/CLI test.*
- `transfer.mcp-cli.result-readable` — **[GAP]** (#5657) an agent can read a transfer's state and result
  by id and review its entity proposals with the existing knowledge-graph tools.

## Test matrix

| Leg | Pins | File |
|---|---|---|
| Backend (pytest), **built** | every persisted id field classified in one bucket with a reason; unclassified or stale entries fail (`transfer.inventory.every-id-classified`) | `fichero-server/tests/unit/transfer/test_every_id_field_is_classified.py` |
| Backend, to write | hand attributions, letterform descriptions, a declared sign's picture, episodes and campaigns travel with their segments; vocabulary matched by key, same key with different fields listed | `fichero-server/tests/unit/transfer/test_transfer_a_page_whole.py` |
| Backend, to write | the source's mirror journal row; the pending step in the source's Activity; a second drag refused; undo after an engine restart; undo refused after the source's Trash is emptied | `fichero-server/tests/unit/transfer/test_transfer_is_never_half_done.py` |
| Backend, to write | canvas link items, spatial nodes and connections, a synced-folder tie: mapped with both ends, cut and listed with one | `fichero-server/tests/unit/transfer/test_transfer_cuts.py` |
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
6. **Correction episodes (training data) for moved pages.** *Resolved in this spec (2026-10-10):*
   they travel with the pages, ids mapped (`transfer.page.episodes`), so the target can train on
   them. The ledger is append-only JSONL (`<package>/episodes/YYYY-MM.jsonl`), so the source's
   lines are not deleted: a `transferred` line names the move, and the source's training export
   leaves out lines whose subject is only in its Trash.
7. **Copying the same item twice into one project.** *Recommend:* a second, separate copy (the
   Finder's rule); `metadata.transferred_from` lets the result say "already copied here on <date>".
8. **Pulling from another machine** (dragging from a remote project into this one). *Recommend:* the
   same copy, the far engine packaging; waits on a host per project (#2573).
9. **Undo durability.** *Decided in this spec, for the maintainer to confirm:* durable across
   restarts from the action history in both projects, while the source items are in its Trash
   (`transfer.action.undo-durable`); emptying the source's Trash makes the move permanent and says
   so first.

## Build order

Engine first, each slice pinned by its tests before the next:

1. **The Trash in the app** (`safety/trash.md`): the engine routes exist; the app's Trash row, view and
   Put Back come early, because a move's safety is that its source lands somewhere a person can see.
   The engine's `safety.trash.dependants-go-with-their-source` (claims on trashed pages hidden) lands with it.
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
