(AI generated. Not reviewed.)

# Node Model

This page documents the parts of the node model that are already shipped in the
merged code. It does not restate the larger staging plan except where a planned
piece matters for understanding what is not built yet.

## Three different axes on a node

The backend `Document` model now carries three different classification axes:

- `doc_type`: the structural shape of the node. In current code this is still
  the main hierarchy axis: file, folder, page, chunk, group, and so on.
- `node_kind`: the behavioral role of the node. The default is `"document"`,
  but shipped special cases now include `"saved_search"`, `"alias"`,
  `"workspace"`, `"plan"`, `"task"`, `"step"`, and `"room"`.
- `prototype_key`: an optional class/prototype tag. It names a prototype
  definition or a conventional subtype such as `"saved_search"` or
  `"bookmark"`.

Those axes are intentionally separate. A shipped saved search is a good example:
it is stored as a `Document` with `doc_type=folder`, `node_kind="saved_search"`,
and `prototype_key="saved_search"`. A shipped bookmark is different again: it is
an alias node with `node_kind="alias"` and `prototype_key="bookmark"`.

## Prototype definitions and inheritance

Prototype resolution is implemented in
`fichero-engine/src/fichero/node_prototypes.py`, and the built-in prototype
definitions are seeded from `_BUILTIN_DOCUMENT_PROTOTYPE_SEEDS` in
`fichero-engine/src/fichero/db.py`. The current shipped behavior is attribute
inheritance, not a full behavior system.

- A prototype definition is a `ClassificationValue` row with
  `dimension=document_prototype`.
- Prototypes can point to a parent through `parent_key`.
- `resolve_prototype_attributes` walks that parent chain, merges attributes
  root to leaf, and lets the child override inherited values.
- The shipped built-ins include plain types such as `book` and `letter`, plus
  container/workspace types such as `folder`, `research_workspace`, and `room`.
- `folder` is the current built-in container base. Its seeded attributes are
  `container_kind="folder"` and `supports_children=True`.
- `research_workspace` and `room` both inherit from `folder` through
  `parent_key="folder"`. The seeded room-specific attributes are
  `spatial_layout=True` and `workspace_kind="room"`.
- Unknown keys, missing parents, and cycles raise
  `PrototypeResolutionError` instead of silently returning partial data.

The unit tests in `test_node_prototypes.py` verify the current contract:
inheritance works across multiple levels, child attributes override parent
attributes, and invalid chains fail loudly.

Prototype assignment is also shipped as part of the documents API:

- `PUT /api/documents/{doc_id}/prototype` in
  `fichero-engine/src/fichero/api/routes/documents.py` validates the requested
  key against seeded/user-defined `ClassificationValue` rows.
- The same route can apply a prototype to descendants, and can restrict that
  assignment to descendant page nodes within a page range.

## Aliases

Alias nodes are implemented in
`fichero-engine/src/fichero/node_aliases.py`.

- An alias is a `Document` with `node_kind == "alias"` and a non-empty
  `alias_target_id`.
- `make_alias` copies the target's structural `doc_type`, keeps a normal
  `parent_id`, and does not duplicate the target's content.
- `resolve_alias` returns the live target node.
- Missing targets raise `DanglingAliasError` rather than degrading silently.

This is the shared foundation the bookmark fold now reuses.

## Saved searches as document nodes

Saved searches are now folded into document nodes in the database layer.

The relevant implementation is in `fichero-engine/src/fichero/db.py`:

- `_save_saved_search_document` mirrors a `SavedSearch` into a same-id
  `Document`.
- The mirrored node is written with `node_kind="saved_search"`,
  `doc_type=DocType.folder`, and `prototype_key="saved_search"`.
- The search payload is stored in `attributes`, including `query`, `filters`,
  `search_type`, `sort_by`, `sort_direction`, and `folder_path`.
- A small `curated_items` record also stores the query payload, and
  `_saved_search_from_document` uses it as a fallback if the `attributes["query"]`
  value is missing.
- `metadata` is still populated with saved-search-specific fields such as
  `node_class="smart_folder"` and `saved_search_query`.

The public saved-search API still lives under `api/routes/search.py` as
`/api/search/saved` CRUD and reorder routes. The fold did not replace that API
surface; it changed the storage representation under it.

## Mind-palace rooms as node-backed folders

Mind-palace rooms now have a node-backed representation in the database layer.

The relevant implementation is split between `fichero-engine/src/fichero/db.py`
and `fichero-engine/src/fichero/api/routes/mind_palace.py`:

- `Database.save(...)` special-cases `SpatialRoom` and mirrors it through
  `_save_spatial_room_document`.
- The mirrored node is written with `node_kind="room"`,
  `doc_type=DocType.folder`, and `prototype_key="room"`.
- The room payload lives in `attributes`, including `description`,
  `room_type`, `owner_id`, and room `metadata`.
- Reads are symmetric: `Database.get(SpatialRoom, ...)`,
  `Database.all(SpatialRoom)`, and `Database.query(SpatialRoom, ...)` hydrate
  from document nodes whose `prototype_key` is `"room"`.
- Room nodes resolve effective prototype attributes through the same
  `resolve_prototype_attributes(...)` path as other prototype-backed nodes, so
  a room inherits the current folder/container attributes from the built-in
  `room -> folder` chain.
- On reopen, `_backfill_spatial_room_documents` mirrors legacy `SpatialRoom`
  rows into room documents if the old table still exists.

F5 slice 1 did not replace the mind-palace room API surface. The existing room
routes still operate on `SpatialRoom` view models:

- `POST /api/mind-palace/rooms`
- `GET /api/mind-palace/rooms`
- `GET /api/mind-palace/rooms/{room_id}`
- `PATCH /api/mind-palace/rooms/{room_id}`
- `DELETE /api/mind-palace/rooms/{room_id}`

Those routes now read and write through the node-backed room bridge rather than
through a room-only storage path.

## Research workspaces as workspace nodes

Research workspaces are also folded into `Document` rows in the database layer.

The relevant implementation is in `fichero-engine/src/fichero/db.py`:

- `Database.save(...)` special-cases `ResearchProject` and mirrors it through
  `_save_research_workspace_document`.
- The mirrored node is written with `node_kind="workspace"`,
  `doc_type=DocType.folder`, and `prototype_key="research_workspace"`.
- The fold also sets `is_workspace=True`, so the node presents as a workspace
  folder rather than as a plain library folder.
- Workspace-specific payload lives in `attributes`, including `description`,
  `status`, `created_by`, `library_destination_folder_id`, and the project's
  `metadata`.
- `metadata` is also marked with `node_class="research_workspace"` plus the
  original `research_project_id`.
- Reads are symmetric: `Database.get(ResearchProject, ...)`,
  `Database.all(ResearchProject)`, and `Database.query(ResearchProject, ...)`
  hydrate from document nodes whose `prototype_key` is
  `"research_workspace"`.
- On reopen, `_backfill_research_workspace_documents` mirrors legacy
  `ResearchProject` rows into workspace documents if the old table still exists.

The unit tests in `test_db.py` and `test_routes_research_agents.py` verify the
current contract: saving a `ResearchProject` produces a same-id workspace node,
reading can hydrate a project back from that node, and reopen backfills the
mirror when needed.

## Research plans, tasks, and steps

Research plans, tasks, and steps are now folded into `Document` rows in the
current merged code.

What the shipped code does today:

- `Database.save(...)` mirrors `ResearchPlan`, `ResearchTask`, and
  `ResearchStep` through `_save_research_plan_document`,
  `_save_research_task_document`, and `_save_research_step_document`.
- Plans are mirrored as `node_kind="plan"` plus
  `prototype_key="research_plan"`.
- Tasks are mirrored as `node_kind="task"` plus
  `prototype_key="research_task"`.
- Steps are mirrored as `node_kind="step"` plus
  `prototype_key="research_step"`.
- Containment is represented through `parent_id`: a plan's parent is its
  project/workspace, a task's parent is its plan, and a step's parent is its
  task.
- `Database.get(...)`, `Database.all(...)`, and `Database.query(...)` now have
  folded-document read paths for all three model types.
- On reopen, `_backfill_research_plan_task_step_documents` mirrors legacy rows
  into document nodes if the legacy tables still exist.

Important boundary:

- `BackgroundTask` in `fichero-engine/src/fichero/workflows/task_types.py` and
  `fichero-engine/src/fichero/workflows/tasks.py` is workflow/task-run
  infrastructure. It is not part of the research node-model fold and should not
  be described as a plan/task/step node.

## Bookmarks as alias-backed nodes

Bookmark nodes ship as backend routes in
`fichero-engine/src/fichero/api/routes/bookmarks.py`.

- `POST /api/bookmarks` creates a bookmark by calling `make_alias(...)` and then
  setting `prototype_key="bookmark"`.
- `GET /api/bookmarks` lists only nodes that are both
  `node_kind="alias"` and `prototype_key="bookmark"`.
- `GET /api/bookmarks/{bookmark_id}/resolve` resolves the bookmark through the
  shared alias resolver and returns `404` on a dangling target.

Tests in `test_routes_bookmarks.py` verify those semantics directly.

Planned, not yet built:

- The backend and OpenAPI surface are shipped.
- SwiftUI wiring is still explicitly deferred; the endpoint allowlist records
  `/api/bookmarks` and `/api/bookmarks/{bookmark_id}/resolve` as backend-only
  for now.

## What is still planned

The larger fold plan in `docs/contributor/architecture/node_model_fold_staging.md` is still
mostly a staging document, not a completion record.

What is shipped now:

- prototype attribute resolution
- built-in document-prototype seeding, including `folder`, `room`, and
  `research_workspace`
- alias nodes
- saved-search document folding
- mind-palace room document folding with the existing `/api/mind-palace/rooms`
  routes still intact
- research-workspace document folding
- research plan/task/step document folding
- bookmark routes built on alias nodes

What should still be described as planned unless more code lands:

- broader prototype-driven behavior beyond attribute inheritance
- SwiftUI bookmark UI wiring
- the remaining staged subsystem folds described in the architecture note

## Fold status

This is the current closeout status for EPIC #2591, based on merged backend
code rather than the original staging plan.

Folded into the node model now:

- F1 saved searches: `Database.save(SavedSearch)` mirrors each saved search into
  a `Document` with `node_kind="saved_search"` and
  `prototype_key="saved_search"`, and the database read paths route both the
  legacy model and the folded node through that bridge.
- F2 research workspaces: `Database.save(ResearchProject)` mirrors each
  workspace into a `Document` with `node_kind="workspace"` and
  `prototype_key="research_workspace"`, and the built-in
  `research_workspace` prototype inherits from `folder`.
- F3 research plans, tasks, and steps: `Database.save(...)` folds
  `ResearchPlan`, `ResearchTask`, and `ResearchStep` into document nodes with
  `parent_id` containment linking workspace -> plan -> task -> step.
- F4 bookmarks: `POST /api/bookmarks` creates alias nodes through
  `make_alias(...)`, and bookmark listing / resolution is implemented by
  filtering alias nodes with `prototype_key="bookmark"`.
- P3 notes and milestones: `Database.save(Note)` and `Database.save(Milestone)`
  mirror both models into `Document` rows with `prototype_key="note"` and
  `prototype_key="milestone"`, and those nodes appear in document-child reads.
- P4 entities filable in folders: a `KnowledgeEntity` only gets a mirrored
  `Document` row when it has a `parent_id`; moving or clearing that `parent_id`
  updates or removes the folded node, so filing is represented through normal
  document containment.
- P5 folder and room prototypes: built-in prototype seeds now include `folder`
  and `room`, and `node_prototypes.py` resolves inherited attributes through
  the parent chain rather than hard-coding per-type behavior.
- F5 slice 1 room-node bridge: `Database.save(SpatialRoom)` mirrors each room
  into a `Document` with `node_kind="room"` and `prototype_key="room"`, while
  the existing `/api/mind-palace/rooms*` routes keep reading and writing the
  legacy `SpatialRoom` model through that bridge.

Intentionally not folded:

- `BackgroundTask` in
  `fichero-engine/src/fichero/workflows/task_types.py` and
  `fichero-engine/src/fichero/workflows/tasks.py` is task-queue
  infrastructure, not a node-model task type.
- The workflow runner in `fichero-engine/src/fichero/execution/runner.py` and
  the workflow execution routes remain execution infrastructure, not document
  nodes.
- The action registry in `fichero-engine/src/fichero/actions/registry.py`
  remains the audited write path for mutations; it is not a node fold.
- Provider configuration in `fichero-engine/src/fichero/providers.py` remains
  backend/provider infrastructure, not document content.
- Authorization and ACL enforcement in `fichero-engine/src/fichero/authz.py`
  remain access-control infrastructure, not part of the node hierarchy.

Still in progress or pending:

- P6 chat scopes are not fully folded yet. The shipped code only seeds a
  `chat_scope="container"` prototype attribute on `research_workspace`; broader
  chat-scope folding should still be described as in progress until more code
  lands.
- F5 retirement of the `/api/mind-palace/rooms*` endpoints is still pending.
  Those routes are live in `fichero-engine/src/fichero/api/routes/mind_palace.py`
  and currently depend on the room <-> room-node bridge for behavior parity.
