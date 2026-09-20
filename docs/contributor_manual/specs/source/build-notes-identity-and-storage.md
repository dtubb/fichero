# Source Model — Build notes: identity and storage (slices 2 to 6)

> Milestone: source-model
> Manual: TBD — none of its own; engineering notes behind `segments-and-geometry.md`.
>
> **Status: DRAFT.** Engineering detail for the engine worker, one section for each slice, in
> build order. The maintainer does not need to read this file: the design is in
> `source-model.md` and `segments-and-geometry.md`, and nothing here changes it. It has no
> behaviours of its own; it names the behaviours each slice pins. Slice 1 is in the
> foundation ("Build order"). Code facts were read on disk on 2026-09-19; the worker re-reads
> each file before editing it. Ids keep the code's current nouns (library, document, artifact).
>
> Standing rules (from the foundation): every write is one typed, audited, undoable action
> (`actions/registry.py`, `@action`); pydantic models; routes carry `response_model=` so they
> reach the OpenAPI contract; `sync_openapi_schema.sh` regenerates the contract, the Swift
> client input and the CLI (never hand-edit them; `info.version` stays `2026.9.8`); a change
> event for every write; temporary libraries only; tests carry the pytest marker
> `source_model` and name the behaviour id they pin in their docstring.
>
> **What an audit record may carry (default taken; morning file, question 8).** An action's
> `params`, `before` and `after` sit inside the tamper-evident chain and can never be rewritten.
> So segment actions record **ids, kinds, versions and geometry**, and **never a reading's typed
> text**. Nothing in slices 2 to 6 writes reading text at all.

## Slice 2 — the change stream names segments and passes (#4920)

**Pins:** `source.events.segment-ids`.

**Why now.** `emit_change` (`api/change_stream.py`) carries typed id lists (`entity_ids`,
`claim_ids`, `document_ids`, `artifact_ids`, `citation_ids`, `reference_ids`,
`interpretation_ids`). With no segment list, a segment edit could only say "this document
changed", and a window would redraw a whole page.

**Engine.**
- `api/change_stream.py`: `ChangeEvent` gains `segment_ids: list[str] = []` and `pass_ids:
  list[str] = []`; `emit_change(...)` gains keyword arguments `segment_ids: Iterable[str] = ()`
  and `pass_ids: Iterable[str] = ()`, handled exactly as `artifact_ids` is (sorted, de-duplicated,
  omitted from the wire when empty if that is what the others do: copy, do not invent).
- `actions/registry.py`: `ChangeSpec` gains the same two lists, and `ActionRegistry._emit`
  passes them through to `emit_change` beside the others.
- Replay and the event log: wherever a `ChangeEvent` is serialised for replay, the two lists
  ride along. An **old** logged event with neither key must still decode (default empty).
- Domain name for the events later slices emit: `segment` (event types `segment.created`,
  `segment.updated`, `segment.deleted`, `segment.converted`, `pass.created`). This slice
  registers nothing that emits them.

**App.** `Services/LibraryChangeStream.swift`: `struct ChangeEvent: Decodable` gains
`segmentIds: [String]` and `passIds: [String]`, decoded with a default of empty so an engine
that does not send them still decodes. No consumer is added in this slice (there is no segment
store yet); emitting with no subscriber matches how `artifact.updated` first landed.

**No schema change, no migration, no action, no route.**

**Refusals.** None.

**Tests.**
- `emit_change(..., segment_ids=[b, a, a])` delivers `segment_ids == [a, b]` to a subscriber
  (pins `source.events.segment-ids`).
- A `ChangeSpec` with `segment_ids` and `pass_ids` reaches the subscriber through
  `registry.invoke` of a throwaway test action.
- An event serialised before this change (no `segment_ids` key) still decodes, engine side
  and, in a Swift unit test tagged `.models`, app side.
- An event with only `segment_ids` set does **not** populate `document_ids` by itself (a later
  slice decides to send both; the stream must not guess).

## Slice 3 — `Segment` and `Pass` records (#4921)

**Pins:** `source.store.record-per-segment`, `source.store.bounded-reads`,
`source.pass.named-authored`, `source.pass.never-overwrites`, `source.segment.one-primitive`,
`source.segment.open-kinds`, `source.segment.lasting-id`, `source.segment.box-is-derived`,
`source.segment.rerun-is-new-pass`.

**How tables come to be.** A pydantic model saved through `Database.save()` gets its table on
first save (`_ensure_table`: table name is the class name lower-cased plus `s`; lists, dicts
and nested models are stored as JSON; missing columns are added on open). So the models below
*are* the schema. Indexes are never made by that path: they are hand-written in
`db/migrations/schema.py`.

**Ids.** `id: str = Field(default_factory=_new_id)` (`uuid4().hex`, as every model). **Minted
by the engine, never accepted from a client**: create actions take no `id` in their params, and
a params model that carries one is refused by validation (`extra="forbid"`). An id is never
reused and never reassigned: nothing in any slice updates a segment's `id`, `document_id` or
`pass_id`.

**Models** (`models/segments.py`, beside slice 1's read shapes; exported from
`models/__init__.py`).

`SegmentPass` (table `segmentpasss` by the naming rule; if that reads badly, set the name the
way `CanvasLayout` does in `Database._table_name` and say so in the commit):

| Field | Type | Notes |
|---|---|---|
| `id` | str | engine-minted |
| `document_id` | str | the source (a page or document node) this pass covers |
| `name` | str | defaults to the run's or the tool's name |
| `provenance_kind` | `ProvenanceKind` | the existing enum; set by the engine from how the write arrived |
| `actor` | str \| None | user id, or tool name |
| `provider`, `model` | str \| None | as on an artifact |
| `run_id` | str \| None | groups the passes of one run |
| `source_artifact_id` | str \| None | the artifact whose boxes this pass was made from, if any |
| `import_file`, `import_checksum` | str \| None | for an imported pass |
| `created_at` | datetime | `utc_now` |
| `deleted_at` | datetime \| None | soft delete; a pass is never removed |

`Segment` (table `segments`):

| Field | Type | Notes |
|---|---|---|
| `id` | str | engine-minted; never moves |
| `document_id` | str | required |
| `pass_id` | str | required; **exactly one pass** |
| `parent_segment_id` | str \| None | the ladder; no order lives here |
| `kind` | str | open list; defaults are the anchor's granularity words plus the non-text kinds |
| `kind_raw` | str \| None | a model's own label, kept beside the tidy one |
| `anchor` | `SourceAnchor` (JSON) | the place: rect, polygon, `rendition_id`, char span, `rotation`. Authoritative |
| `baseline` | list[list[float]] \| None (JSON) | normalised to the anchor's image |
| `bbox_x`, `bbox_y`, `bbox_w`, `bbox_h` | float | **written by the engine only**, worked out from the anchor; no params model accepts them |
| `tile` | str | coarse tile key worked out from the box (an 8 by 8 grid over the image: `"x3y5"`; a segment crossing tiles takes the tile of its centre), for reads by area |
| `confidence` | float \| None | machine confidence of the *shape*, if the tool gave one |
| `is_furniture` | bool | default False |
| `provenance_kind` | `ProvenanceKind` | engine-set |
| `created_by` | str \| None | |
| `version` | int | starts at 1 (used from slice 5) |
| `created_at`, `updated_at` | datetime | |
| `deleted_at`, `deleted_by` | datetime \| None, str \| None | soft delete; the row is never removed |
| `metadata` | dict (JSON) | what an import or a tool gave that the model has no field for |

Left out on purpose until their slices: several shapes and time spans (slice 7), language,
script and direction (slice 9), table cells (after 7), campaigns and hands (slice 14).

**Indexes** (one new function `migrate_segment_indices(conn)` in `db/migrations/schema.py`,
each `CREATE INDEX IF NOT EXISTS`, guarded by "does the table exist", called from
`_ensure_table` the way `migrate_knowledge_indices` is for its tables, so they appear with the
table and again harmlessly on every open):

| Index | Serves |
|---|---|
| `segments(document_id)` | "the segments of this source" (slice 1's seam, conversion's "is this page converted") |
| `segments(pass_id)` | "the segments of this pass"; pass comparison |
| `segments(parent_segment_id)` | children of a region or line |
| `segments(kind)` | reads by kind; combined with `document_id` by the planner |
| `segments(tile)` | reads by area, with `document_id` |
| `segmentpasss(document_id)` | "the passes of this source" |
| `segmentpasss(run_id)` | grouping passes by run |

DuckDB's indexes are single-column; composite needs are met by filtering on `document_id`
first. If the timing test below fails, add a `doc_kind` key column (`<document_id>:<kind>`)
and index that, and say so in the commit.

**Migration and old libraries.** No data moves. `migrate_segment_indices` is the only new
migration. Test in the shape of `tests/unit/db/test_catalogue_chunk_artifact_type_migration.py`:
hand-build a library database with today's `artifacts` table and **no** `segments` table; open
it; run the migration **twice**; assert nothing raised, no `segments` rows exist, the artifact
rows are byte-for-byte unchanged, and a first `Segment` save then creates the table and the
indexes.

**Actions** (`api/routes/document/segments.py`, in the router slice 1 made; each route calls
`registry.invoke` directly in its own body, as `check_routes_use_action_layer.py` requires):

| Action | Params (pydantic, `extra="forbid"`) | Records for its inverse | Inverse |
|---|---|---|---|
| `segment.pass_create` | `document_id`, `name`, `run_id?`, `source_artifact_id?` | `after: {pass_id}` | `segment.pass_delete` |
| `segment.pass_delete` | `pass_id` | `before: {pass_id}` | `segment.pass_restore` (clears `deleted_at`) |
| `segment.create` | `document_id`, `pass_id`, `kind`, `anchor`, `baseline?`, `parent_segment_id?`, `kind_raw?` | `after: {segment_ids}` | `segment.delete` of those ids |
| `segment.create_many` | `document_id`, `pass_id`, `segments: list[...]` (uses `save_many`) | `after: {segment_ids}` | `segment.delete` of those ids |

Update and delete of a segment arrive in slice 5, with versions. What the audit payload
carries: ids, kinds and anchors (geometry). No text.

**ChangeSpec.** `domains=["segment"]`; `segment_ids`, `pass_ids`, and `document_ids=[document_id]`
with `document_parents`; `emit_type` `segment.created` / `pass.created`.

**The seam now reads both.** Slice 1's `GET /api/segments/document/{doc_id}` returns rows where
a document has them (`provisional: false`) and the old boxes where it does not.

**Refusals** (typed errors, each with a test): a params model carrying `id`, `bbox_*`, `tile`,
`version` or `provenance_kind` (validation, 422); a `pass_id` whose `document_id` differs from
the segment's (409, `SegmentPassMismatch`); a `parent_segment_id` in another pass or document
(409, `SegmentParentMismatch`); a `legacy:` id anywhere (`assert_not_provisional`); an anchor
whose `document_id` is not the segment's.

**Tests, by behaviour.**
- `source.segment.lasting-id`: create; read back; the id is engine-made; a client-supplied id
  is refused.
- `source.segment.box-is-derived`: the four box columns equal the anchor's bounds for a rect
  and for a polygon; supplying them is refused.
- `source.segment.one-primitive` / `.open-kinds`: a region, a line, a word and a picture are
  all `Segment`s; an unknown `kind` string round-trips; `kind_raw` is kept.
- `source.pass.named-authored` / `.never-overwrites` / `source.segment.rerun-is-new-pass`: two
  passes over one document keep separate segments; creating the second changes no row of the
  first (row count, `updated_at`).
- `source.store.record-per-segment`: "the lines of this document in this pass" and "the
  children of this region" are single filtered queries.
- `source.store.bounded-reads`: with 200,000 segments in one source (made with `save_many` in
  a temporary library; marked `slow`), one page at one kind returns in under 200 ms; a read
  with no `document_id` is refused.
- Old-library test above, twice.
- The seam returns rows for a converted document and boxes for an unconverted one, in the
  same response shape.
