---
hide:
  - toc
---

# API Reference

!!! warning "Work in progress, unstable"
    The Fichero API is still in progress. Endpoints and response shapes will
    change before 1.0, and this is not yet a stable contract. Do not build
    against it expecting backward compatibility.

The Fichero engine is a FastAPI application that exposes an OpenAPI 3 schema.
The interactive reference below is rendered from the committed schema
(`openapi.json`, copied from `fichero-engine/tests/contracts/openapi.json`).

That committed schema is the real backend surface used to generate the Swift
client and document the engine routes. In the current contract it includes route
families for documents, search, workflows, workflow execution, annotations,
providers, knowledge-graph endpoints, mind-palace endpoints, and more.

## Fold endpoints documented here

The node-model fold shipped backend storage changes this session, but the API
surface is still route-based. The paths below are the committed public
contract in `fichero-engine/tests/contracts/openapi.json`.

### `/api/bookmarks`

`POST /api/bookmarks`

- Purpose: create a bookmark node that points at another document.
- Request body: `BookmarkCreate`
  - `target_id` (required string): the target document id.
  - `parent_id` (optional string or null): parent bookmark container.
  - `name` (optional string or null): override display name for the alias node.
- Response: `201` with a `Document` object.
  - The route code creates the bookmark through alias machinery and then sets
    `prototype_key="bookmark"`, so the returned document is the alias-backed
    bookmark node rather than the resolved target.

`GET /api/bookmarks`

- Purpose: list bookmark nodes.
- Query params:
  - `parent_id` (optional string): filter by parent bookmark container.
- Response: `200` with `DocumentListResponse`.
  - `items`: array of `Document` rows.
  - `count`: total rows returned.

### `/api/bookmarks/{bookmark_id}/resolve`

`GET /api/bookmarks/{bookmark_id}/resolve`

- Purpose: resolve a bookmark node to its current target document.
- Path params:
  - `bookmark_id` (required string): bookmark document id.
- Response: `200` with a `Document` object for the live target.
- Failure behavior from the route code: a dangling or missing bookmark target is
  returned as `404`, not a partial alias object.

### `/api/search/saved`

These saved-search endpoints still expose `SavedSearch*` request and response
models even though saved searches are folded into node-backed storage in the
backend.

`GET /api/search/saved`

- Purpose: list all saved searches.
- Response: `200` with `SavedSearchListResponse`.
  - `items`: array of `SavedSearchResponse`.
  - `count`: total rows returned.

`POST /api/search/saved`

- Purpose: save a search for later.
- Request body: `SavedSearchCreate`
  - `query` (required string).
  - `is_smart_search` (optional boolean, default `true`).
  - `filters` (optional object or null).
  - `search_type` (optional string, default `"hybrid"`).
  - `sort_by` (optional string, default `"relevance"`).
  - `sort_direction` (optional string, default `"desc"`).
  - `folder_path` (optional string, default `"/"`).
  - `sort_order` (optional integer, default `0`).
- Response: `200` with `SavedSearchResponse`.
  - Fields include `id`, `query`, `is_smart_search`, `filters`,
    `search_type`, `sort_by`, `sort_direction`, `folder_path`, `sort_order`,
    and `created_at`.

### `/api/search/saved/{search_id}`

`PUT /api/search/saved/{search_id}`

- Purpose: update a saved search.
- Path params:
  - `search_id` (required string).
- Request body: `SavedSearchUpdate`.
  - Partial update fields are `query`, `is_smart_search`, `filters`,
    `search_type`, `sort_by`, `sort_direction`, and `folder_path`.
- Response: `200` with `SavedSearchResponse`.

`DELETE /api/search/saved/{search_id}`

- Purpose: delete a saved search.
- Path params:
  - `search_id` (required string).
- Response: `200` with the route's `DeletedResponse` object.

### `/api/search/saved/{search_id}/duplicate`

`POST /api/search/saved/{search_id}/duplicate`

- Purpose: duplicate a saved search under a new id.
- Path params:
  - `search_id` (required string).
- Response: `200` with `SavedSearchResponse`.

### `/api/search/saved/reorder`

`POST /api/search/saved/reorder`

- Purpose: reorder saved searches within a folder.
- Query params:
  - `folder_path` (optional string, default `"/"`).
- Request body: JSON array of saved-search ids in the desired order.
- Response: `200` with the route's reorder response object.

!!! note
    This is a static render of the committed contract schema. For live,
    interactive docs against a running engine, start it locally with
    `bash fichero-engine/scripts/start_backend.sh` and open
    `https://127.0.0.1:8765/docs` (Swagger UI) or `/redoc`.

<redoc spec-url="openapi.json" hide-download-button></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
