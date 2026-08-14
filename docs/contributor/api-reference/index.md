---
hide:
  - toc
---

(AI generated. Not reviewed.)

# API Reference

!!! warning "Work in progress, unstable"
    The Fichero API is still in progress. Endpoints and response shapes will
    change before 1.0, and this is not yet a stable contract. Do not build
    against it expecting backward compatibility.

The Fichero engine is a FastAPI application that exposes an OpenAPI 3 schema.
The interactive reference below is rendered from the committed schema
(`openapi.json`, copied from `fichero-server/tests/contracts/openapi.json`).

That committed schema is the real backend surface used to generate the Swift
client and document the engine routes. In the current contract it includes route
families for documents, search, workflows, workflow execution, annotations,
providers, knowledge-graph endpoints, canvas endpoints (the former
mind-palace routes, renamed to `/api/canvas`), and more.

## W3C annotation export

`GET /api/documents/{doc_id}/annotations.jsonld`

- Purpose: export a document's annotations as a W3C Web Annotation
  `AnnotationPage`, including the JSON-LD context and annotation targets.
- Path param: `doc_id` (required string), the source document id.
- Response: `200` with the JSON-LD AnnotationPage object; missing documents
  return `404`.

## Prototype attributes and the dataset query (datasets Stages 1–2)

`GET /api/documents/{doc_id}/effective-attributes`

- Purpose: a node's structured data, resolved — attribute declarations from
  its prototype chain (typed, with renderer roles) plus effective values
  (chain defaults overlaid with the node's own `attributes`). Unresolvable
  prototypes return `422`, never partial data.

`GET /api/classifications/resolved/{key}`

- Purpose: one prototype's chain-merged declarations and defaults — the
  editor's inheritance preview. Unknown key or cycle returns `422`.

`POST /api/documents/dataset/query`

- Purpose: the one renderer query over a folder's attribute-bearing rows —
  server-side sort (typed, nulls last), typed filters, paging, date binning
  (year/month/day, for timeline and calendar), and facet counts, all via
  DuckDB `json_extract` per the Stage 2 measurement. The response carries
  each involved prototype's chain-merged defaults so clients overlay a page
  cheaply; a prototype that no longer resolves reports its error string
  under `_unresolved`.

## Fold endpoints documented here

The node-model fold shipped backend storage changes this session, but the API
surface is still route-based. The paths below are the committed public
contract in `fichero-server/tests/contracts/openapi.json`.

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

## Recently added engine endpoints

These routes are in the committed OpenAPI contract. They are documented here
until their corresponding Swift service wrappers land; the engine CLI already
exposes them.

### Device enrollment

`POST /api/pair/enroll`

- Purpose: exchange an owner's synced enrollment secret for a new, distinct
  per-device token.
- Request body: `EnrollmentRequest` with the required `enrollment_secret`.
- Response: `200` with `PairResponse`. The enrollment secret is not itself a
  device credential, so the returned token remains independently revocable.

### Agent workspace membership

`PATCH /api/chat/workspaces/{workspace_id}/members`

- Purpose: add or remove curated source, entity, claim, or note references on
  an explicit saved agent workspace.
- Path param: `workspace_id` (required string).
- Request body: `AgentWorkspaceMembershipPatch`, with `add` items and/or
  `remove_ids`.
- Response: `200` with the updated `AgentWorkspace`; mutations are audited and
  undoable through the workspace action layer.

### Content representations and revisions

`GET /api/content-representations/document/{document_id}` lists a document's
typed `ContentRepresentation` records. `document_id` is required; response is
`200` with an array of representations.

`GET /api/content-representations/{representation_id}/revisions` lists the
immutable `ContentRepresentationRevision` history for one representation.
Returns `200` with an array or `404` when the representation does not exist.

`POST /api/content-representations/{representation_id}/revisions` records a
reviewer revision without changing the source representation. The body is
`RepresentationRevisionParams` (`content` required, `decision` optional); the
response is `200` with the new `ContentRepresentationRevision`.

### PyKEEN prediction review lifecycle

`POST /api/kg/pykeen/reviews` persists a `KnowledgePredictionReview` for a
user-confirmed review workflow; response `200` returns that review.

`GET /api/kg/pykeen/reviews` lists review records as `PykeenListResponse`.
Optional query `state` filters by the typed `PredictionReviewState`.

`PATCH /api/kg/pykeen/reviews/{review_id}` records an accept/reject/review
decision. The body is `PredictionReviewDecision` (`state` required, `note` and
`resulting_claim_id` optional); returns the updated review or `404`.

### Entity biography export

`GET /api/entities/{entity_id}/export` downloads one entity's existing
structured biography as an attachment. `entity_id` is required. The optional
`format` query parameter accepts `markdown` (default), `text`, or `json`; the
response is the corresponding attachment with a filesystem-safe filename.
Unknown entity ids return `404`.

### Record-bundle exports

`POST /api/export/jsonl` writes a JSON Lines record bundle for an optional
`target_id`, or for the whole library when it is omitted, to the requested
`output_path`. `POST /api/export/parquet` writes the same target's typed
Parquet bundle, or the whole library when `target_id` is omitted, to its
requested `output_path`. Both routes return a conflict rather than replacing
an existing destination unless the request sets `overwrite` (default `false`),
and return `404` when a supplied target does not exist. Their requested destinations are engine-local filesystem paths, so
these are CLI/backend-only surfaces: no SwiftUI save/export workflow may call
them.

### Live library handles

`GET /api/registry/open`

- Purpose: report the backend's currently open library connections, distinct
  from persisted `GET /api/registry` known-library rows.
- Response: `200` `OpenLibraryHandlesResponse`, whose items expose `id`,
  `path`, and `is_open` from a lock-safe manager snapshot.

### Reversible image regions and batches

All routes below preserve the source document. Crop and split create derived
children; uncrop, unsplit, and batch undo remove those derived children.

`POST /api/images/{document_id}/crop` accepts `CropOperationRequest` (`left`,
`top`, `width`, `height`, optional `page`/`auto_orient`) and returns
`ImageCropResponse` for one derived child. `POST /api/images/{document_id}/uncrop`
accepts no body and returns the reversible crop response.

`POST /api/images/{document_id}/split` accepts `ImageSplitRequest` with region
`bboxes` and returns `ImageSplitResponse`; `POST /api/images/{document_id}/unsplit`
accepts no body and returns `ImageUnsplitResponse` after removing those children.

`POST /api/images/crops/batch` applies one `ImageBatchCropRequest` region to
its required `document_ids`, returning `ImageBatchCropResponse` with children.

`POST /api/images/batch-apply` applies one crop or split spec to all images in
a required folder (`BatchImageApplyRequest`) and returns `BatchResponse` with
per-item state. `POST /api/images/batch-apply/{batch_id}/undo` reverses its
completed derived children and returns `BatchImageUndoResponse`; unknown or
non-image batch ids return `404`.

!!! note
    This is a static render of the committed contract schema. For live,
    interactive docs against a running engine, start it locally with
    `bash fichero-server/scripts/start_backend.sh` and open
    `https://127.0.0.1:8765/docs` (Swagger UI) or `/redoc`.

## Sandbox (Mac App Store)

### `POST /api/sandbox/security-scoped-access`

Grants the **running engine process** access to a security-scoped library folder.

Under the Mac App Store's App Sandbox, a child process inherits only the parent's
**static** entitlements. The user's folder grant (from `NSOpenPanel`) is a **dynamic**
Powerbox extension, and dynamic rights are **not inherited** — so the sandboxed engine
cannot open the user's library on its own. The app therefore hands the engine an
app-scoped **security-scoped bookmark**, which this endpoint resolves on the live engine
process and calls `startAccessingSecurityScopedResource()` against.

Returns whether the grant was already held (so the bookmark was not resolved twice).

**On failure it returns 400 and the engine refuses the library** — a malformed bookmark,
or a refusal from `startAccessingSecurityScopedResource()`, means the engine genuinely
cannot read that library, and the app must say so rather than open it and fail later.

See `docs/superpowers/specs/2026-07-13-mac-app-store-sandbox-research.md` (#3747).

<redoc spec-url="openapi.json" hide-download-button></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>

### Artifact span → page region

`GET /api/artifacts/{artifact_id}/region` resolves a line or character span of
a transcription artifact to its normalized page region — the single addressing
scheme (#4418) behind sentence-level highlight provenance. Optional query
parameters `char_start`/`char_end` (offsets into the artifact's content) or
`line` (zero-based) choose the span. The response is `ArtifactRegionResponse`:
a `geometry_status` (so "this engine cannot point at the page" is
distinguishable from "this page is blank"), an optional `geometry_reason`, and
the resolved `region` when geometry exists. Unknown artifact ids return `404`.

### Workflow run comparison

`GET /api/workflow-execution/comparisons` diffs what two runs produced from
the same input. Required query parameters `left` and `right` are the two
thread ids. Artifacts pair on (document, artifact type); the
`RunComparisonResponse` reports line-level differences for transcriptions and,
for extraction runs, which entities or claims each side found that the other
missed.

### Workflow run episodes

`GET /api/workflow-execution/threads/{thread_id}/episodes` returns the
episode-ledger records recorded under one run — per-node model-call
provenance: each record carries the node, the full exchange (prompt, raw
output, thinking), model identity and use case, the subject
(document/page/file), and timing. Optional `limit` (default 500). The
response is `{thread_id, count, episodes}` with records in ledger order.
This is the per-node inspection surface and the resolver behind episode
citation keys; corrections and invalidations referencing the run's
episodes appear by id.

### Interpretation search leg

`POST /api/search` accepts `"interpretations"` in `include` (opt-in, like
`"artifacts"`). A matching interpretation — its text, key insights, or
predicate — folds its SOURCE document into `results` with
`metadata.matched_via = "interpretation"`, the interpretation text as the
preview, and `interpretation_id`/`framework_id` in metadata so the client
can open the interpretive context alongside the document.

### Training export

`POST /api/export/training` writes chat-format training samples from the
episode ledger to a `.jsonl` destination. One sample per recorded model
call: system+user messages from the recorded exchange; the assistant turn
is the human correction when one exists (`gold: true`, with the model's
original output in `rejected` for DPO pairing), otherwise the model
output. Optional `use_case` filters to one workflow step's calls;
`gold_only` keeps only corrected pairs. Engine-local destination path — a
CLI/backend surface like the record-bundle exports, with the same
conflict rule (`409` unless `overwrite`).
