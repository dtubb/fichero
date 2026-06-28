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
- bookmark routes built on alias nodes

What should still be described as planned unless more code lands:

- broader prototype-driven behavior beyond attribute inheritance
- SwiftUI bookmark UI wiring
- the remaining staged subsystem folds described in the architecture note
