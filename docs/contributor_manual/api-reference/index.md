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

## Connected clients

`GET /api/clients`

- Purpose: which surfaces are currently talking to this engine — the app,
  the `fichero` CLI, an MCP client — each with its transport (`uds`, `tcp`),
  request count, and first/last seen times. Sharing settings renders this so
  a user can see that the command-line tool and MCP server really are
  connected, rather than inferring it from a successful command.
- Presence, not authorization: entries come from the `X-Fichero-Client`
  header recorded during auth enforcement, so an unnamed caller is attributed
  by transport rather than rejected.

## W3C annotation export

`GET /api/documents/{doc_id}/annotations.jsonld`

- Purpose: export a document's annotations as a W3C Web Annotation
  `AnnotationPage`, including the JSON-LD context and annotation targets.
- Path param: `doc_id` (required string), the source document id.
- Response: `200` with the JSON-LD AnnotationPage object; missing documents
  return `404`.

## Document outline view (Mandate 1, 2026-08-24)

`GET /api/documents/{doc_id}/view`

- Purpose: one answer for "where am I, what's in here, what does it have" —
  ancestors root-first, the anchor document, level-aware children, and an
  attachment summary (renditions, artifacts, annotation/entity counts). The
  ONE outline endpoint every tree consumer (sidebar, grid, breadcrumbs,
  entry ladder, dataset router) migrates onto, replacing five client-side
  tree builders that each cached and disagreed.
- Query params: `level` (`stored` default — the sidebar's structural tier;
  `content` looks through containers, the grid's tier), `children` and
  `attachments` (booleans; a cheap caller skips halves).
- Response: `200` `DocumentViewResponse`; unknown ids return a declared
  `404`.

## Renditions (bbox program, 2026-08-20)

`GET /api/documents/{document_id}/renditions`

- Purpose: list a document's renditions — the same page in different pixel
  frames (archival original, enhanced, background-removed). The engine
  returns them in canonical order (primary first, then role preference), so
  every client agrees what "next" means. Missing documents return a declared
  `404`.

`GET /api/documents/{document_id}/renditions/{rendition_id}/content`

- Purpose: the bytes of one named rendition, for the preview's up/down
  rendition flip. Unknown document or rendition id returns a declared `404`.
  Not yet called from Swift — tracked in the ui-wiring baseline until the
  flip control is wired.

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
    `bash fichero-server/scripts/start_fichero_server.sh` and open
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

See `agent-work/superpowers/specs/2026-07-13-mac-app-store-sandbox-research.md` (#3747).

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

### Artifact region curation

`PUT /api/artifacts/{artifact_id}/regions` curates an artifact's
`ocr_geometry.boxes`. The body is `ArtifactRegionsEditRequest` with an `op`:
`move` (one index plus a normalized `bbox`), `delete` (one or more indices),
`add` (a `bbox`, optional `text`/`level` — bootstraps an empty user geometry
when the artifact has none yet, which is the rubber-band draw on a bare page),
or `combine` (two or more indices replaced by their union box, texts joined in
reading order). Every edit runs as one audited, undoable action with a full
before-snapshot, and appends a `curation_log` entry inside the geometry so the
history travels with the artifact. The response is `ArtifactResponse` with
geometry included, so the caller re-renders its overlay from the reply rather
than re-fetching.

### Segments (source model)

`GET /api/segments/document/{doc_id}` returns a source page's segments —
region, line and word boxes — resolved from whichever of its artifacts carry
`ocr_geometry` (the old blob) AND from real `Segment`/`SegmentPass` rows
where they exist (slice 3): the caller cannot tell which store a segment
came from. Reading a page's segments this way writes nothing: calling it
twice creates no row. The response is `SegmentListResponse` (`document_id`,
`passes`, `segments`); a document with neither yet returns an empty list,
not an error, and an unknown `doc_id` returns `404`. Optional query
parameters `artifact_id` (restrict to one artifact's boxes, or one real
pass's source artifact), `pass_id` (restrict to one pass — a `legacy:` one
or a real pass id), `kind` (restrict to one segment kind — region, line,
word), and `area` (a rectangle, `x,y,w,h` in image fractions — every real
segment whose box intersects it) narrow the result.

A segment read from today's blob is **provisional**:
`legacy:<artifact_id>:<box_index>` and its pass `legacy:<artifact_id>`, both
marked `provisional: true`. A provisional id is refused on write — the
regions-edit route (`PUT /api/artifacts/{artifact_id}/regions` above) and
every segment-write route below return `422` if handed one.

Each segment's `anchor` is a `SourceAnchor` (rect always; a polygon only when
the source box's metadata carries one — a Kraken line's polygon and baseline
are normalized from pixels to the anchor's fractional top-left convention).
Raw pixel values, and why a box's geometry could not be held, ride in the
segment's own `metadata` (`raw_polygon_px`, `raw_baseline_px`,
`raw_pixel_frame`, `geometry_problem`) — never on the anchor, which slices 3
and 6 store.

`POST /api/segments/passes` creates a `SegmentPass` (body:
`SegmentPassCreateParams` — `document_id`, `name`, optional `run_id` and
`source_artifact_id`), one typed audited action
(`segment.pass_create`/`.pass_delete`/`.pass_restore`). `DELETE
/api/segments/passes/{pass_id}` soft-deletes it (the row is never removed;
its segments stop appearing in the seam).

`POST /api/segments` creates one `Segment` in an existing pass (body:
`SegmentCreateParams` — `document_id`, `pass_id`, `kind`, `anchor`, optional
`baseline`, `parent_segment_id`, `kind_raw`); `POST /api/segments/bulk`
creates several in one `save_many` transaction (`SegmentCreateManyParams`).
Both refuse (`409`) a `pass_id` from another document or a
`parent_segment_id` in another pass/document, and (`422`) a client-supplied
`id`, `bbox_*`, `tile`, `version` or `provenance_kind` — the params models
declare none of them, so `extra="forbid"` rejects the request outright; the
four box columns are always engine-derived from `anchor`. Update and delete
of a segment as a user-facing feature, with version compare-and-set, arrive
in a later slice.

**Matches, forwarding notes, a citable reference (slice 4).** An id never
moves: "this new segment is that old one" is a `SegmentMatch` record, and a
merge/split/delete leaves an append-only `SegmentForwarding` note so an old
id can always be followed (`resolve_segment`, used by the citable reference
below).

`POST /api/segments/matches` proposes a match (body: `from_segment_id`,
`to_segment_id`, optional `certainty`, `note`), one typed audited action
(`segment.match_propose`/`.match_withdraw`). `POST
/api/segments/matches/{match_id}/accept` and `POST
/api/segments/matches/{match_id}/reject` change its state; only a person
may accept — a machine caller gets `422` (`MatchNeedsAPerson`).

`POST /api/segments/merge` absorbs two or more segments (one pass) into
`keep_id` (body: `segment_ids`, `keep_id`); the absorbed rows are
soft-deleted and each gets a `merged` forwarding note. Merging into a
segment that already forwards to the one being absorbed is refused (`409`,
`SegmentForwardingWouldLoop`) — this is what stops a merge cycle. `POST
/api/segments/split` splits one segment into two or more `parts` (each an
`anchor` and optional `baseline`); the original id stays on the first
part, and a `split` forwarding note names every resulting id.

`POST /api/segments/carry` copies readings/annotations/claim-evidence
across an **accepted** match (body: `match_id`, `kinds` — any of
`reading`, `annotation`, `claim_evidence`); the original is never moved.
A `reading` is carried only across a **one-to-one** match (accepted
matches only) — a many-to-many match carries no reading and reports why in
`not_carried`. Its inverse, `segment.uncarry`, removes exactly the copies.

`GET /api/segments/{segment_id}/reference` returns a citable string,
`fichero:segment/<library_uuid>/<document_id>/<segment_id>`, worked out on
request (never stored). It resolves through the EXISTING `POST
/api/locations/resolve` — never a second resolver — which gains an
optional `segmentId` (a bare id or the citable string form, checked against
the current library and refused with `422` if it names another one): the
route follows any forwarding first (`resolve_segment`), so a merged, split
or deleted id still resolves to where its content lives today. The
response's `liveSegmentIds` names EVERY live part (a split line has two —
this never quietly picks one), `resolvedSegmentId` names the primary
(the part that kept the requested id, else the first part listed when the
split was made), `segmentForwarding` is the trail followed, and
`segmentDeleted` says whether nothing is live any more. A `documentId` sent
alongside a `segmentId` that disagrees with what it resolves to is refused
(`422`) rather than the segment's silently winning.

**Versions, and refusing a stale edit (slice 5).** Every segment carries a
`version`, and every writing action names the version it read
(`expected_version`); if the segment has changed since, the write is
refused with `409` — never silently merged, never silently overwritten.
Editing while out of reach of the engine (a device offline) is **not
supported** in this work: a queue of stale edits made while disconnected is
refused one by one, same as any other stale edit, with no reconciliation.

`PUT /api/segments/{segment_id}` changes one segment's `anchor`,
`baseline`, `kind`, `kind_raw`, `parent_segment_id` and/or `is_furniture`
(body: `SegmentUpdateParams` — `segment_id` matching the path, plus
`expected_version`; `document_id`/`pass_id` are not accepted — a segment
never moves pass or document, that is a merge). A stale `expected_version`
is refused (`409`, body: `{message, segment_id, expected_version,
current_version, changed}` — `changed` names exactly the fields that moved
since); an update to a deleted (or merged-away) segment is refused
(`409`).

`POST /api/segments/delete` soft-deletes one or more segments in the same
pass and document (body: `segment_ids`, `expected_versions` — one per id
— optional `reason`), writing a `SegmentVersion` snapshot and a `deleted`
forwarding note for each. This REPLACES slice 3's internal stand-in: it is
now a real, undoable action with a real inverse. `POST
/api/segments/undelete` brings them back (body: `segment_ids`), clearing
`deleted_at` and writing a `restored` forwarding note.

`POST /api/segments/{segment_id}/restore-version` writes the segment back
to one of its own recorded versions (body: `version`, `expected_version`),
as a NEW version — history only grows, nothing is overwritten in place.
Restoring a version number that was never recorded for this segment (a
version that belongs to a different segment, or simply does not exist) is
a `404`.

`GET /api/segments/{segment_id}/versions` lists one segment's own history
(`SegmentVersion` rows, oldest first) without touching any other segment's
rows. `GET /api/segments/{segment_id}` returns the live row, resolving
through the same forwarding walk as the citable reference when the id has
been merged, split or deleted, and saying so
(`resolved_from_forwarding`, `trail`).

Access follows the same rule as every other library-scoped route today (a
valid token bound to the library, write-checked per target id; no
finer-grained per-document read check yet — see #4917 for the known gap in
that check for artifact-scoped reads).

### Workflow folder presentation

`GET /api/workflows/folders` returns the presentation metadata for workflow
folders — `path`, `display_name`, `sort_order`, and `icon` per folder, plus a
`count`. The order is the order work actually happens (prepare, find regions,
read, clean, translate, extract, catalogue), which is data rather than a rule,
so the capability bar draws its verbs from this list instead of a literal in
Swift. A folder absent from the list is not hidden: the client sorts it after
the known route with a fallback glyph, so a user's own folder appears the
moment they make one.

### Chain step execution

`POST /api/chains/{chain_id}/execute-steps` runs a chain's steps as real,
sequential workflow runs — the workflow bar's staged chain. The body is
`ExecuteChainStepsRequest` (`inputs`: the frozen run inputs shared by every
step; each step merges its own `static_inputs` on top). The response is `202`
with `ChainStepsAcceptedResponse`: an `execution_id` and, per step, a
pre-assigned `thread_id` and `stream_url`, so a client can attach to a step's
SSE stream before that step starts. Poll
`GET /api/chains/executions/{execution_id}` for per-step statuses. Unknown
chain ids return `404`; a chain with no steps returns `400`.

### Workflow runs

`GET /api/workflow-execution/runs` lists workflow runs from the **runs table** — the same
record the toolbar popover reads, and deliberately NOT the event log that `GET /api/activity`
reads. Those two disagreed, and this is the store that settles it: a run with no `activities`
rows at all still appears here, because a run that produced no events is still a run that
happened. Optional `status` repeats to filter (`?status=failed`), with `limit` (1–500, default
50) and `offset`. Paging, sorting and filtering are pushed to SQL, so the cost of listing does
not grow with how many runs the library holds.

`POST /api/workflow-execution/runs/delete` deletes runs in bulk, and "Clear Failed" is the
same audited action with a status filter rather than a second path — one audited action, two
ways of asking. **Checkpoints are left alone**: a deleted run hides the run without destroying
what it produced, and a thread's checkpoint goes separately via
`DELETE /api/workflow-execution/threads/{thread_id}`. That separation is the point, so
clearing a list of failures cannot quietly discard work.

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

## The source model

These are the routes of the source model — the layer that holds what is on a
page (segments, their shapes, their readings), the facts that describe it
(language, script, direction), the orders a scholar reads it in, the links
between its parts, and the interchange formats it reads and writes. Every write
below goes through the one audited action layer, so each answer carries an
`audit_id` and each change has an inverse.

### A segment's readings

`GET /api/segments/{segment_id}/readings`

- One line can have several readings — a recogniser's, a scholar's correction, a
  normalisation, a translation — and exactly one of each kind COUNTS. The answer
  lists them and names the counting one per kind, so a caller never has to
  decide which is authoritative.
- Optional `kind` narrows to one kind. A provisional segment id is accepted,
  because asking what a line says has to work before anybody has edited the
  page.
- Refuses with `404` when there is no such segment. A **provisional** id is
  accepted here on purpose, unlike on the write routes: a reader asking what a
  line says must work before anybody has edited the page.

`POST /api/segments/{segment_id}/readings/choice`

- Records which reading counts. **Only a person may**: a machine choosing which
  of its own outputs is the true one is exactly the judgement this layer exists
  to keep human, so a run's context is refused with `403`.
- Also `422` for a reading kind this library does not have, and for a reading
  whose anchor does not match the segment it is being chosen for: choosing a
  reading of somewhere else is a mistake worth a sentence rather than a silent
  write.

### A page's derived text

`GET /api/segments/document/{document_id}/text`

- The page's text is WORKED OUT, never stored: it is the working pass's
  segments, each contributing its counting reading. The answer carries `spans`
  pointing back at the segment and representation each stretch came from —
  text with no way back to the reading it came from is a wall of words.
- `pass_id` reads a named pass instead of the working one, and the answer always
  says which pass it used and why (`pass_basis`).
- `order` follows a named reading order; omitting it means box order, which the
  answer reports honestly as `order: null` rather than claiming a name.
- Furniture — running heads, folio numbers, catchwords — is left out unless
  `include_furniture` is set, because a page number in the middle of a sentence
  is worse than a missing one.
- `omitted` names every segment the order names that the text does not contain,
  each with a reason: `deleted`, `furniture`, `other_pass` (with the pass that
  holds it) or `unknown`. A cross-pass continuation and a deleted line must not
  look the same, because a silently shortened transcription looks like a correct
  one.
- Refuses with `404` for no such pass or an `order` id that names nothing, `409`
  for an order that was withdrawn, and `422` when the named order is an order of
  a **different pass** from the one being read — the sentence names both passes
  and says which `pass_id` to ask for, because a text assembled from one pass's
  readings in another pass's order is a sentence nobody wrote.

### A segment's picture

`GET /api/segments/{segment_id}/picture`

- PNG bytes of the segment's own area, cut to its shape: cropped to its box plus
  `margin`, masked outside its polygon with `mask`, levelled along its baseline
  with `straighten`, and bounded by `size` (the default is bounded, not
  unlimited).
- Bytes rather than a storage reference, because the storage routes address a
  document and not one of its derived crops — and a local path would break the
  rule that the engine may be remote.
- It refuses rather than answering when the segment was measured against a
  different image from the one on the document: a picture of the wrong place is
  worse than an error.
- That refusal is a `422` whose sentence names the image it was measured on and
  the one that is there now. The same `422` covers every other reason a picture
  cannot be made honestly.

### Source settings: language, script and direction

`GET /api/source-settings/resolve`

- The three facts and the text encoding for ONE selection (`segment_id`, or
  `document_id` for the page), each with the rung that answered it: the segment,
  the document, the project, or a default. A fact that does not say where it came
  from cannot be argued with.
- For one selection and not a list, deliberately: resolving every segment of a
  page here would be one cascade walk per row.
- Refuses with `404` when the node it is asked about does not exist.

`PUT /api/source-settings`

- States a fact, or stops stating it — an empty value clears rather than writing
  a blank, so "nobody has said" and "somebody said nothing" stay different.
- A level it does not own is refused by name. Segment-level facts belong to
  `segment.update`, which owns a segment's own fields; this route owns the
  project and the document.
- Every refusal is a `422` that names what was wrong: a level this route does not
  own, a level that is not a level, a project fact outside the known keys, a
  script code that is not ISO 15924, a direction outside the known set, a node
  reference with no target, or an empty value sent to the setter instead of the
  clearer.

### Reading orders

`POST /api/reading-orders`

- Creates a named order over a pass. A page holds several: the order as written,
  a commentary order, an imposed order, and a **flow**, which is the one kind
  whose entries may name segments of another pass because text continues onto
  the next folio.
- `seed_from_pass` fills the new order from the pass's own box order, which is
  what makes an as-written order agree with what a recogniser produced.
- Refuses with `409` when a segment is already in the order, or when a segment
  belongs to a different pass and the order is not a flow — that distinction is
  the flow's whole point — and `422` when an order's positions have run out of
  room and need renumbering first, which is a request to renumber rather than a
  failure.

`GET /api/reading-orders/document/{document_id}`

- A source's orders, the as-written one first. `include_deleted` shows withdrawn
  ones, since an order is soft-deleted and restorable like everything else here.
- The entry and neighbour reads refuse with `404` for no such order and `409` for
  a deleted one, rather than answering emptily: an order that was withdrawn and
  an order with nothing in it are different facts.

`GET /api/reading-orders/{order_id}/entries`

- ONE LEVEL of one order — the top level, or the children of `parent_entry_id`.
  Orders nest (regions in order, lines in order within each), and returning a
  whole tree would make a bounded read depend on how deeply somebody nested
  their reading.

`GET /api/reading-orders/{order_id}/neighbours`

- What reads before and after one segment **in this order**. Always of a named
  order: there is no "next segment" call without one, because a page holds
  several orders and answering from a default would be the engine picking a
  scholarly reading without saying so.
- Two bounded lookups, not a walk of the order.
- `422` when no order is named, because there is no default order to fall back
  to.

### Typed links

`GET /api/links/types`

- This library's link vocabulary: each type's key, its label, its inverse label,
  and whether it is built in. Aliases are reported alongside, so a client that
  knows a display name can find the one key it maps to.

`GET /api/links/of/{end_id}`

- Every link touching one thing, **from either side**. "What relates to this
  line" is one question a reader asks, not two, so it is one call and two
  indexed reads. `include_deleted` shows withdrawn links.

`POST /api/links`

- Relates two ends by a typed link, with an optional `certainty` and `note`. An
  unknown link type is refused by name rather than being created on the fly: a
  vocabulary that grows by typo is not a vocabulary.
- Both refusals are `422`: an unknown link type (the sentence names the
  vocabulary), and a link missing one of its two ends. A display alias is
  resolved to its one key first, so `references` and `cites` are the same link
  rather than two.

### Interchange formats

`GET /api/formats`

- Which interchange formats this build reads and writes, with each one's
  extensions and whether it is schema-validated. A client asks rather than
  hard-coding a list that will be wrong the next release.

`POST /api/documents/{doc_id}/import`

- A PAGE XML, ALTO, hOCR, TEI or YOLO file becomes a **new pass** on the
  document. `format` forces a format instead of recognising one from the bytes;
  `name` says what to call the pass.
- An import does NOT become the working pass. Somebody else's file arriving is
  not a decision about which reading of the page is authoritative.
- Content the model has no field for is kept and labelled, so exporting back to
  that format writes it out again rather than quietly dropping it.
- The refusals are the point and carry a sentence the app is expected to show:
  `409` when this exact file is already a pass (the sentence names which),
  `422` when nothing recognises the file or its shapes lie outside the page it
  declares (the sentence names the formats this build reads, or the segments that
  disagree), `404` for no such document or an unreadable upload.

`GET /api/documents/{doc_id}/export/{format_name}`

- Writes one page out as PAGE XML, ALTO or TEI, returning the file as text with
  the filename to save it under, plus a **loss report**: what the format cannot
  carry, named rather than dropped silently.
- `pass_id` picks the pass (the working pass by default), `order_id` the reading
  order (as written by default), `reading_kind` which kind of reading to write.
- An export that does not validate against its schema is a reported failure and
  **no file**, because a file that exists and does not validate is one somebody
  sends to a colleague.
- Refuses with `404` for a format nothing here knows, for a document with no pass
  to export, and for an order that names nothing; `409` for a format this build
  reads but cannot write; `500` for an export that failed validation, which is
  our bug and not the caller's.
- The loss report is not a warning to be skipped. A format that cannot carry fine
  geometry, or direction, or a rival reading says so by name, and the round trip
  subtracts exactly what the report names.

## Page-model and paleography routes (2026-09)

Each line is drawn from the route's own summary in `openapi.json`.

**Campaigns**, the order in which a source's work was laid down:

- `GET /api/campaigns/document/{document_id}`: a source's campaigns, first laid down first.
- `GET /api/campaigns/reading/{representation_id}`: the campaigns of one reading.
- `GET /api/campaigns/segment/{segment_id}`: the campaign one segment belongs to.

**Conversion** of older results to the page model when a library opens:

- `GET /api/conversion/status`: what the conversion has done, is doing, and has left.
- `POST /api/conversion/{run_id}/seen`: a person has seen this run's report.

**Import**, pairing images with their layout files:

- `POST /api/documents/import-batch`: files dropped together (multipart), paired exactly as when their folder is dropped.
- `POST /api/ingest/files`: several files ingested as one set; a layout file that pairs with an image in the set becomes a pass on that image.

**Editorial, statements and matches:**

- `GET /api/editorial/segment/{segment_id}`: a segment's live editorial facts, and its counting reading.
- `GET /api/segments/{segment_id}/statements`: what is said about a segment.
- `GET /api/segments/document/{doc_id}/matches`: the matches recorded on one page, for review.
- `GET /api/segments/passes/{pass_id}/original`: the file an imported pass was read from, byte for byte.

**Places and georeferencing:**

- `GET /api/entities/{entity_id}/place`: a place as of a date, never the nearest geometry.
- `GET /api/entities/{entity_id}/linked-places`: a place as Linked Places Format.
- `GET /api/links/naming`: every segment that names a place `same_as` a URI.
- `GET /api/georeference/documents/{doc_id}/geojson`: an image's segments placed in the world, as GeoJSON.
- `GET /api/georeference/passes/{pass_id}/transform`: a pass's transform, with residuals.
- `PUT /api/georeference/passes/{pass_id}/transformation`: choose the transformation type; returns 422 with the number of GCPs needed when a pass has too few.
- `GET /api/georeference/segments/{segment_id}/world-shape`: one segment's shape in the world.

**Hands, meaning who wrote what:**

- `GET|POST /api/hands`: list the project's hands, or create one.
- `POST /api/hands/{hand_id}/withdraw`: withdraw a hand.
- `POST /api/hands/attributions`: attribute a segment to a hand.
- `POST /api/hands/attributions/{attribution_id}/withdraw`: withdraw an attribution.
- `GET /api/hands/segment/{segment_id}`: every live judgement of a segment's hand, rivals side by side.
- `GET /api/hands/{hand_id}/attributions`: everything in one hand that the caller may read.

**Letterforms and signs:**

- `GET /api/letterforms`: every live mark of a character, allograph or hand; at least one of the three must be named.
- `GET /api/letterforms/allographs`, `GET /api/letterforms/features`: the allographs, and the features in use.
- `GET /api/letterforms/segment/{segment_id}`: the letterform description of one segment.
- `GET|POST /api/signs`: list signs, or declare one.
- `GET /api/signs/{sign_id}/instances`: a sign's instances.
- `POST /api/signs/{sign_id}/withdraw`: withdraw a sign.

**Reading orders:**

- `GET /api/reading-orders/flows/onto/{document_id}`: the flows this page's segments could join, nearest earlier page first.
- `POST /api/reading-orders/{order_id}/place`: the single reorder call made by the Reader, the Inspector and the Segments pane. It is audited and undoable.

**Rights:**

- `POST /api/rights`: set rights on a target.
- `GET /api/rights/effective`: what applies to a target; every record above it, combined tighten-only.
- `POST /api/rights/{record_id}/withdraw`: withdraw a rights record.

**Fonts:**

- `GET /api/fonts`: the bundled fallback fonts, in fallback order.
- `GET /api/fonts/{name}`: one bundled font file, or its licence.
