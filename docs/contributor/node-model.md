# Node Model

This page documents the parts of the node model that are already shipped in the
merged code. It does not restate the larger staging plan except where a planned
piece matters for understanding what is not built yet.

## Three different axes on a node

The backend `Document` model now carries three different classification axes:

- `doc_type`: the structural shape of the node. In current code this is still
  the main hierarchy axis: file, folder, page, chunk, group, and so on.
- `node_kind`: the behavioral role of the node. The default is `"document"`,
  but shipped special cases now include `"saved_search"` and `"alias"`.
- `prototype_key`: an optional class/prototype tag. It names a prototype
  definition or a conventional subtype such as `"saved_search"` or
  `"bookmark"`.

Those axes are intentionally separate. A shipped saved search is a good example:
it is stored as a `Document` with `doc_type=folder`, `node_kind="saved_search"`,
and `prototype_key="saved_search"`. A shipped bookmark is different again: it is
an alias node with `node_kind="alias"` and `prototype_key="bookmark"`.

## Prototype definitions and inheritance

Prototype resolution is implemented in
`fichero-engine/src/fichero/node_prototypes.py`. The current shipped behavior is
attribute inheritance, not a full behavior system.

- A prototype definition is a `ClassificationValue` row with
  `dimension=document_prototype`.
- Prototypes can point to a parent through `parent_key`.
- `resolve_prototype_attributes` walks that parent chain, merges attributes
  root to leaf, and lets the child override inherited values.
- Unknown keys, missing parents, and cycles raise
  `PrototypeResolutionError` instead of silently returning partial data.

The unit tests in `test_node_prototypes.py` verify the current contract:
inheritance works across multiple levels, child attributes override parent
attributes, and invalid chains fail loudly.

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

Research plans, tasks, and steps are not folded into `Document` rows in the
current merged code.

What the shipped code actually does today:

- `api/routes/research_crud.py` creates and updates `ResearchPlan`,
  `ResearchTask`, and `ResearchStep` by calling `db.save(...)` on those models
  directly.
- `Database.save(...)` has mirror hooks only for `SavedSearch` and
  `ResearchProject`; there is no corresponding fold helper for
  `ResearchPlan`, `ResearchTask`, or `ResearchStep`.
- `Database.get(...)`, `Database.all(...)`, and `Database.query(...)` have
  folded-document read paths only for `SavedSearch` and `ResearchProject`.
- The current research hierarchy is therefore model-native:
  `ResearchTask.plan_id` points to its plan, and `ResearchStep.task_id` points
  to its task.

Planned, not yet built:

- A `research_plan` prototype fold in the document tree.
- Child task and step nodes represented through `parent_id`.
- Prototype-key-backed plan/task/step document hydration analogous to the
  shipped saved-search and research-workspace folds.

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

The larger fold plan in `docs/architecture/node_model_fold_staging.md` is still
mostly a staging document, not a completion record.

What is shipped now:

- prototype attribute resolution
- alias nodes
- saved-search document folding
- research-workspace document folding
- bookmark routes built on alias nodes

What should still be described as planned unless more code lands:

- broader prototype-driven behavior beyond attribute inheritance
- research plan/task/step document folding
- SwiftUI bookmark UI wiring
- the remaining staged subsystem folds described in the architecture note
