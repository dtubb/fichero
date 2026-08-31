# 2. The Node Model


The library is a tree of nodes. The backend `Document` model carries three separate classification axes:

- `doc_type` — the structural shape: file, folder, page, chunk, group, and so on. Still the main hierarchy axis.
- `node_kind` — the behavioral role. Default `"document"`; shipped special cases include `"saved_search"`, `"alias"`, `"workspace"`, `"plan"`, `"task"`, `"step"`, and `"room"`.
- `prototype_key` — an optional class/prototype tag naming a prototype definition or conventional subtype such as `"saved_search"` or `"bookmark"`.

A saved search illustrates the separation: it is stored as a `Document` with `doc_type=folder`, `node_kind="saved_search"`, `prototype_key="saved_search"`. A bookmark is an alias node with `node_kind="alias"` and `prototype_key="bookmark"`.

### Prototypes

Prototype resolution lives in `models/node_prototypes.py`; built-in definitions are seeded from `_BUILTIN_DOCUMENT_PROTOTYPE_SEEDS` in the `db/` package. Shipped behavior is **attribute inheritance**, not a full behavior system:

- A prototype definition is a `ClassificationValue` row with `dimension=document_prototype`; prototypes can point to a parent through `parent_key`.
- `resolve_prototype_attributes` walks the parent chain, merges attributes root to leaf, and lets the child override inherited values.
- `folder` is the built-in container base (`container_kind="folder"`, `supports_children=True`); `research_workspace` and `room` inherit from it.
- Unknown keys, missing parents, and cycles raise `PrototypeResolutionError` rather than returning partial data.

Prototype assignment ships in the documents API: `PUT /api/documents/{doc_id}/prototype` in `api/routes/document/documents.py` validates the key and can apply a prototype to descendants, optionally restricted to page nodes in a range.

### Aliases and bookmarks

Alias nodes (`models/node_aliases.py`): an alias is a `Document` with `node_kind == "alias"` and a non-empty `alias_target_id`. `make_alias` copies the target’s structural `doc_type` and does not duplicate content; `resolve_alias` returns the live target; missing targets raise `DanglingAliasError`. Bookmarks build on this: `api/routes/system/bookmarks.py` creates bookmarks via `make_alias(...)` with `prototype_key="bookmark"`, lists only alias-kind bookmark nodes, and resolves through the shared resolver (404 on a dangling target). The backend and OpenAPI surface are shipped; SwiftUI bookmark wiring is still deferred.

### Folded subsystems

The larger fold program (EPIC \#2591) has landed these as document nodes, each with symmetric read paths (`Database.get/all/query` hydrate from folded nodes) and reopen-time backfills from any surviving legacy tables:

- **Saved searches** — mirrored via `_save_saved_search_document`; the query payload lives in `attributes`. The public `/api/search/saved` CRUD surface is unchanged; the fold changed the storage representation under it.
- **Research workspaces** — `ResearchProject` mirrors to `node_kind="workspace"`, `prototype_key="research_workspace"`, `is_workspace=True`.
- **Research plans, tasks, steps** — `node_kind` `"plan"`/`"task"`/`"step"` with containment through `parent_id`: workspace → plan → task → step.
- **Notes and milestones** — mirrored with `prototype_key="note"` / `"milestone"`; they appear in document-child reads.
- **Entities filed in folders** — a `KnowledgeEntity` gets a mirrored `Document` row only when it has a `parent_id`; filing is represented through normal document containment.
- **Mind-palace rooms** — `SpatialRoom` mirrors to `node_kind="room"`, `prototype_key="room"`. **The** `/api/mind-palace/rooms*` **route surface is REMOVED** — `tests/unit/api/test_mind_palace_route_guard.py` asserts it stays removed. Rooms survive as workspace nodes via the bridge, not as a separate storage path or API namespace.

Deliberately **not** folded: `BackgroundTask` (workflow task-queue infrastructure, not a node), the workflow runner and execution routes, the action registry, provider configuration, and authz enforcement. Still in progress: chat-scope folding (only a `chat_scope="container"` attribute on `research_workspace` is seeded so far), broader prototype-driven behavior beyond attribute inheritance, and the SwiftUI bookmark UI.
