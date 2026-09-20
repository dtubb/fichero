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

## Slice 1b — three additions to slice 1's read shapes (#4919; after engine slice 2 reports)

Found by the review of the app's first stage: the engine's answer lacks two things the app
cannot rebuild, and fills one field from the wrong place. All additive; one contract sync.

- **`SegmentRead.page_index: int | None`**, copied from `OCRGeometryBox.page_index`. The PDF
  page view filters boxes by it (`PDFPageWithToolbar.boxesForDisplayedPage`); without it every
  page of a multi-page PDF would show every page's boxes.
- **`PassRead.text: str | None`**, the result's own text (`OCRGeometryResult.text`). A box's
  `char_start` and `char_end` index into **that** text. The app must never rebuild it by
  joining box texts.
- **`PassRead.provider` is the artifact's provider**, and the app's `OCRGeometry.provider` is
  filled from it, not from `name` (which holds the artifact's type).

**Tests.** A two-page PDF fixture: each segment carries its page's index, and filtering by page
gives each page only its own. For every segment with a character span,
`pass.text[char_start:char_end]` equals the segment's `text` (a fixture whose box texts joined
with spaces would **not** equal the pass's text, so the test fails if anything rebuilds it).
The three-way parity test (route, MCP, generated command) covers the two new fields.

## Slice 2 — the change stream names segments and passes (#4920)

**Pins:** `source.events.segment-ids`.

**Why now.** `emit_change` (`api/change_stream.py`) carries typed id lists (`entity_ids`,
`claim_ids`, `document_ids`, `artifact_ids`, `citation_ids`, `reference_ids`,
`interpretation_ids`). With no segment list, a segment edit could only say "this document
changed", and a window would redraw a whole page.

**What the engine worker's reading found (2026-09-19; file and line in
`agent-work/source-model/recon-slice-2.md`), and what it means.**

- **Adding the two lists to `ChangeSpec` does nothing by itself.** `ActionRegistry._emit`
  (`actions/registry.py`, about lines 284 to 291) passes the id lists to `emit_change` through a
  **hand-written list of keywords**, not a loop. A list that is on `ChangeSpec` and not in that
  keyword list is silently never sent.
- **There is no stored event log.** Both "replay" paths are in the running process. But the
  **folded activity stream, which is what feeds remote windows, has its own hard-coded place
  where events are written out**: `_change_event_to_activity_response`
  (`api/routes/system/activity.py`, about lines 100 to 123) writes each id list into
  `ActivityResponse.metadata` as JSON, and that is exactly what Swift's
  `init?(activityMetadata:)` reads. Miss this site and a remote window never sees a segment
  event, one hop before the Swift gap.
- **The risk is silent omission, not refusal.** Nothing checks which id lists an event carries.
  There are **four hand-written sites that must agree and are not enumerated anywhere**:
  `_emit`, the activity fold, and Swift's two ways of building a `ChangeEvent`
  (`init(from:)` for the direct stream, `init?(activityMetadata:)` for remote windows). The
  existing guardrail (`check_emit_change_coverage.py`) only checks that `emit_change` is
  called at all.
- **The gap is already open today:** the engine sends `artifact_ids` and `interpretation_ids`,
  and Swift decodes neither.

**The rule this slice sets (so the test is written against a rule).** `emit_change`
**de-duplicates every id list and keeps the order it was given** (first occurrence wins), for
all lists, old and new. It does not sort. A store that patches items in place gains nothing
from a duplicate, and order can carry meaning (the order things were changed in). Today
`emit_change` does neither; this is a small behaviour change for every list, made once, here.

**Engine.**
- One declared tuple, `CHANGE_ID_LISTS = ("entity_ids", "claim_ids", "document_ids",
  "artifact_ids", "citation_ids", "reference_ids", "interpretation_ids", "segment_ids",
  "pass_ids")`, in `api/change_stream.py`. **`_emit` and the activity fold read it, so neither needs an
  edit for a new kind.** (A new kind still needs its field on `ChangeEvent` and `ChangeSpec`
  and its keyword on `emit_change`; one test asserts that those four agree with the tuple,
  because a mismatch would otherwise drop every event behind `emit_change`'s catch-all, logged
  only at debug.)
- `ChangeEvent` gains `segment_ids: list[str] = []` and `pass_ids: list[str] = []`;
  `emit_change(...)` gains the two keyword arguments; de-duplication (order kept) is applied to
  every name in the tuple, in one loop.
- `actions/registry.py`: `ChangeSpec` gains the two lists, and **`_emit` iterates the tuple**
  to build the keywords it passes, replacing the hand-written list.
- `api/routes/system/activity.py`: **`_change_event_to_activity_response` iterates the same
  tuple** to write the lists into `metadata`.
- Domain name for the events later slices emit: `segment` (event types `segment.created`,
  `segment.updated`, `segment.deleted`, `segment.converted`, `pass.created`). This slice
  registers nothing that emits them.

**App** (`Services/LibraryChangeStream.swift`). `ChangeEvent` gains `segmentIds`, `passIds`,
**and the two the engine already sends and Swift drops today, `artifactIds` and
`interpretationIds`**, in **both** `init(from:)` and `init?(activityMetadata:)`, each
defaulting to empty so an engine that does not send them still decodes. Swift has no way to
read the engine's tuple, so its half is protected by the contract test below. No consumer is
added in this slice (there is no segment store yet).

**No schema change, no migration, no action, no route.**

**Refusals.** None.

**Tests.**
- **One round trip for every declared kind, through both paths**: for each name in
  `CHANGE_ID_LISTS`, emit an event carrying that list; assert it arrives at a direct-stream
  subscriber, and that the activity fold's `metadata` carries it. The test iterates the tuple,
  so a kind added later is covered without editing the test (pins `source.events.segment-ids`,
  and closes the silent-omission class).
- A `ChangeSpec` with `segment_ids` and `pass_ids` reaches a subscriber through
  `registry.invoke` of a throwaway test action (this is the test that fails today's
  hand-written keyword list).
- De-duplication with order kept: `segment_ids=[b, a, b, c]` arrives as `[b, a, c]`; the same
  for an old list (`document_ids`), so the rule is pinned for all of them.
- An event with neither new key still decodes, engine side and, in a Swift unit test tagged
  `.models`, app side, **for each of Swift's two init paths**.
- Swift decodes `artifactIds` and `interpretationIds` from a recorded engine event, through
  both init paths (the gap that is open today).
- **The fixture is compared, never written, in a normal test run**: the engine test builds the
  expected fixture from the tuple with a fixed timestamp and fails, naming the command that
  regenerates it, when the committed file differs. A test run never dirties the tree.
- `emit_request_change` (a hand-written wrapper with the seven old lists, called by nothing) is
  deleted, or made to forward every declared list: a fourth hand-written site is how a
  whole-page refresh creeps back in.
- A contract test holds the Swift side to the engine's tuple: a fixture file of one event
  carrying every declared list, written by an engine test from `CHANGE_ID_LISTS`, is decoded
  by a Swift test that asserts every list is non-empty. A kind added in the engine and not in
  Swift fails there.
- An event with only `segment_ids` set does **not** populate `document_ids` by itself.

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

## Slice 4 — matches, forwarding notes, a citable reference (#4922)

**Pins:** `source.segment.match-record`, `source.segment.forwarding-notes`,
`source.segment.carry-across-a-match`, `source.segment.citable`.

**Models** (`models/segments.py`).

`SegmentMatch` (table `segmentmatchs`): `id`; `document_id`; `from_segment_id` (the older);
`to_segment_id` (the newer); `state: str` (`proposed` | `accepted` | `rejected`);
`proposed_by_kind: ProvenanceKind` (engine-set); `proposed_by: str | None`;
`accepted_by: str | None`; `accepted_at: datetime | None`; `certainty: float | None`;
`note: str | None` (a short reason; **not** source text); `created_at`. Many to many is
allowed (one old line became two).

`SegmentForwarding` (table `segmentforwardings`), **append-only**: `id`; `document_id`;
`old_segment_id`; `kind: str` (`merged` | `split` | `deleted` | `restored`);
`new_segment_ids: list[str]` (JSON; empty for `deleted`); `actor`; `audit_id` (the action that
wrote it); `reason: str | None`; `created_at`. No action ever updates or deletes a row here;
undoing a merge writes a *new* `restored` row.

`SegmentCarry` (table `segmentcarrys`): `id`; `match_id`; `carried_kind: str` (`reading` |
`annotation` | `claim_evidence`); `original_id`; `copy_id`; `created_at`. It is what makes a
carry undoable: the copies it lists are what the inverse removes.

**Indexes** (added to `migrate_segment_indices`): `segmentmatchs(from_segment_id)`,
`segmentmatchs(to_segment_id)`, `segmentforwardings(old_segment_id)`,
`segmentcarrys(match_id)`.

**The resolver** (one function, `resolve_segment(db, segment_id) -> ResolvedSegment`, used by
everything that follows an id): walks `SegmentForwarding` from `old_segment_id`, newest row for
each id first. It is an iterative walk with a visited set. **Depth cap 64: past it, it raises
`SegmentForwardingTooDeep`; it never returns a partial answer.** A revisited id raises
`SegmentForwardingLoop` (it should be unreachable, because the merge refusal below prevents
loops; the raise is the safety net). Result: `ResolvedSegment { requested_id, live_segment_ids:
list[str], trail: list[forwarding rows], ended_in_delete: bool, deleted_by, deleted_at }`.

**Actions.**

| Action | Params | Records for its inverse | Inverse |
|---|---|---|---|
| `segment.match_propose` | `from_segment_id`, `to_segment_id`, `certainty?`, `note?` | `after: {match_id}` | `segment.match_withdraw` |
| `segment.match_accept` | `match_id` | `before: {state}` | `segment.match_set_state` back to `proposed` |
| `segment.match_reject` | `match_id` | `before: {state}` | same |
| `segment.merge` | `segment_ids: list[str]` (two or more, one pass), `keep_id` | `before`: each absorbed segment's id, anchor, kind, parent, version; `after: {kept_id, forwarding_ids}` | `segment.unmerge` (restores the absorbed rows from `before`, writes `restored` forwarding rows) |
| `segment.split` | `segment_id`, `parts: list[{anchor, baseline?}]` (two or more) | `before`: the segment's anchor and version; `after: {kept_id, new_segment_ids, forwarding_id}` | `segment.unsplit` |
| `segment.carry` | `match_id`, `kinds: list[str]` | `after: {carry_ids, copy_ids}` | `segment.uncarry` (deletes exactly those copies) |

`segment.match_accept` is refused for a caller whose `ProvenanceKind` is not `human` (only a
person accepts). `segment.carry` requires an `accepted`, **one-to-one** match for readings; for
a many-to-many match it carries nothing of kind `reading` and returns `not_carried` with the
reason. Carrying **copies**; the original stays where it was.

Audit payloads: ids, anchors, kinds, versions. No reading text is copied into a payload: a
carry records the ids of the copies, and the copies themselves are ordinary rows.

**The citable reference.** `fichero:segment/<library_uuid>/<document_id>/<segment_id>`, a plain
string worked out on request (`library_uuid` from the existing `library_identity` table). It
is **not** a new resolver: `POST /api/locations/resolve` gains an optional `segmentId` (and
accepts the string form), calls `resolve_segment`, and answers with the live segment's
document, page and anchor, plus the trail when the id was forwarded. Route:
`GET /api/segments/{segment_id}/reference` returns `{reference, segment_id}`.

**ChangeSpec.** `domains=["segment"]`; `segment_ids` = every id touched (kept, absorbed, new);
`pass_ids`; `document_ids`; event types `segment.merged`, `segment.split`, `segment.matched`.

**Refusals** (typed, each tested): merging segments from different passes or documents
(`SegmentPassMismatch`); **merging into a segment that already forwards to the one being
absorbed** (`SegmentForwardingWouldLoop`, names both ids); a `keep_id` not among
`segment_ids`; a split with fewer than two parts, or parts outside the image; accepting a match
as a machine (`MatchNeedsAPerson`); carrying across a match that is not accepted; any `legacy:`
id.

**Tests, by behaviour.**
- `source.segment.match-record`: propose as a tool, accept as a person; a tool's accept is
  refused; both segments keep their own ids; nothing in either row changed.
- `source.segment.forwarding-notes`: merge A into B, split B into C and D, delete C: resolving
  A returns D alive and says C was deleted, by whom and when, in **one call**; a hand-made chain
  of 65 raises `SegmentForwardingTooDeep`; merge A into B then B into A is refused; after undo
  of a merge the old forwarding row is still there beside a `restored` row.
- `source.segment.carry-across-a-match`: a one-to-one carry copies a reading and an annotation,
  leaves the originals, names the match on each copy; `segment.uncarry` removes exactly the
  copies; a one-to-two match carries no reading and says so.
- `source.segment.citable`: the reference resolves through `/api/locations/resolve`; after a
  merge the same reference resolves to the kept segment with the trail; after a delete it says
  deleted; the same answers come back over MCP and the generated command.
- Audit payloads of every action above contain no free text longer than `note` and `reason`.

## Slice 5 — versions for each segment, and refusing a stale edit (#4923)

**Pins:** `source.segment.versioned-alone`, `source.segment.delete-is-undoable`,
`source.edit.stale-is-refused`.

**Model.** `SegmentVersion` (table `segmentversions`), append-only: `id`; `segment_id`;
`version: int`; `document_id`; `pass_id`; `parent_segment_id`; `kind`; `kind_raw`; `anchor`
(JSON); `baseline` (JSON); `is_furniture`; `deleted: bool`; `actor`; `provenance_kind`;
`audit_id`; `reason: str | None`; `created_at`. It is a full copy of the segment's own fields at
that version, so undo restores **from ordinary data**, not from the audit chain. Index:
`segmentversions(segment_id)`.

Every action that changes a segment (this slice's and slice 4's merge and split, which are
updated to do so) writes the new `SegmentVersion` in the same transaction and bumps
`Segment.version`.

**Actions.**

| Action | Params | Records for its inverse | Inverse |
|---|---|---|---|
| `segment.update` | `segment_id`, `expected_version: int`, and any of `anchor`, `baseline`, `kind`, `kind_raw`, `parent_segment_id`, `is_furniture` | `before: {segment_id, version}`, `after: {segment_id, version}` | `segment.restore_version` to `before.version` |
| `segment.delete` | `segment_ids: list[str]`, `expected_versions: dict[str,int]`, `reason?` | `before: {segment_id: version}` | `segment.undelete` |
| `segment.undelete` | `segment_ids` | `before: {segment_id: version}` | `segment.delete` |
| `segment.restore_version` | `segment_id`, `version`, `expected_version` | `before: {version}` | `segment.restore_version` back |

Delete sets `deleted_at` and `deleted_by`, writes a `deleted` version and a `deleted`
forwarding row; the row stays. Undelete clears `deleted_at`, writes a version and a `restored`
forwarding row. Restoring a version writes a **new** version whose fields equal the old one:
history only grows.

**Compare-and-set.** Inside the action's transaction: read the segment; if `version !=
expected_version`, raise `SegmentStale` (HTTP 409) carrying `segment_id`, `expected_version`,
`current_version` and `changed: list[str]` (the field names that differ between the two
versions, from `SegmentVersion`). Nothing is written. `Database.save()` is last-write-wins by
itself, so this check is the whole protection; it must sit inside the transaction, not before
it.

**Reads.** `GET /api/segments/{segment_id}/versions` (`response_model` a list of
`SegmentVersion`); `GET /api/segments/{segment_id}` returns the live row, resolving through
`resolve_segment` when the id has been forwarded (and saying so).

**ChangeSpec.** `domains=["segment"]`; `segment_ids`; `pass_ids`; `document_ids`; event types
`segment.updated`, `segment.deleted`, `segment.restored`.

**Refusals** (typed, each tested): `SegmentStale`; updating a deleted segment
(`SegmentDeleted`); restoring a version of another segment; changing `document_id` or
`pass_id` (not accepted by the params model); a `legacy:` id.

**Not supported, and said so:** editing while out of reach of the engine. A queue of stale
edits is refused one by one; there is no merge. (Foundation, morning question 15.)

**Tests, by behaviour.**
- `source.segment.versioned-alone`: three updates to one segment leave three versions of it and
  change no other segment's row or version; `restore_version` to the first makes a fourth
  equal to the first.
- `source.segment.delete-is-undoable`: delete, then undo through the generic undo route
  (`api/routes/system/actions_registry.py`): the segment is live, its id unchanged, and an
  annotation anchored to it still resolves; the forwarding trail shows `deleted` then
  `restored`.
- `source.edit.stale-is-refused`: two updates made against version 1; the second is refused
  with `changed` naming the field the first one changed; the row equals the first update.
- Undo restores from `SegmentVersion`: a test that blanks the audit row's `before` and still
  restores proves the payload is not the source of truth.

## Slice 6 — first-edit conversion (#4924). Do not start before slices 1 to 5 are committed.

**Pins:** `source.store.ids-on-first-edit`, `source.store.no-batch-rewrite`,
`source.store.one-page-per-conversion`, `source.store.conversion-undo-leaves-nothing`,
`source.store.conversion-repoints-exact-matches`. The design rules are in
`segments-and-geometry.md` ("First-edit conversion: the rules").

**What exists.** Region edits today are one action, `artifact.regions_edit`
(`api/routes/document/artifacts.py`; params `ArtifactRegionsEditActionParams { artifact_id,
edit }`), whose inverse is `_invert_artifact_to_restore` → `artifact.restore` with the whole
previous artifact. **Used unchanged after conversion, that inverse would restore the block of
boxes and leave the new segment rows: two stores.** Note too that its `before` and `after`
are whole artifact dumps, text included: the existing action already puts a researcher's words
in the audit chain (this bears on morning question 8; this slice does not make it worse and
does not fix it).

**Is a page converted?** `is_converted(db, document_id) -> bool`: true when a live
`SegmentPass` exists for the document with `source_artifact_id` set. Never inferred from the
block being absent. A second edit finds it true and does not convert again.

**Marking the block as replaced.** `Artifact` gains one additive field,
`geometry_superseded_by_pass_id: str | None` (a column added on open by `_ensure_table`; no
data migration). The block itself is **kept unchanged** (it is what undo restores, and what
old readers still resolve claims against). One helper, `read_ocr_geometry(artifact, *,
allow_superseded=False)`, is the only sanctioned way to read `artifact.ocr_geometry`; it raises
`GeometrySuperseded` for a superseded block unless the caller is on the short permitted list
(the seam of slice 1; the conversion and its inverse; span resolution for a claim whose anchor
has not been re-pointed). A guardrail script lists the permitted callers; every other reader
found by `grep ocr_geometry` is moved to the seam in this slice or listed with a reason.

**The action.** `segment.convert_and_edit`:

- Params: `document_id`, `artifact_id` (the result being edited), `edit` (today's
  `ArtifactRegionsEditRequest`, unchanged, so the app's existing verbs keep working).
- Steps, in one transaction: (1) refuse if `is_converted`; (2) for **every** artifact of the
  document that has boxes, make one `SegmentPass` (`source_artifact_id` set, `provenance_kind`
  copied from the artifact's run) and one `Segment` for each box with `save_many`
  (`anchor.rect` from the box, `anchor.polygon` and `baseline` from `metadata` where present
  and normalised, `anchor.rendition_id` from the result, `anchor.char_start/char_end`, `kind`
  from the box's level, `metadata` carrying `box_index` so the order of the old list is never
  lost); (3) set `geometry_superseded_by_pass_id` on each; (4) re-point exact matches (below);
  (5) apply `edit` to the new rows of `artifact_id`'s pass through the slice 5 actions'
  internals (one audit row in all, not one for each); (6) write versions.
- The **working pass** is the pass made from `artifact_id` (the one being looked at): recorded
  as a human choice in the form slice 8 will read (`SegmentPassChoice { document_id, pass_id,
  chosen_by, chosen_at }`, table `segmentpasschoices`; the only thing stored about "working").
- `before`: `{document_id, artifact_ids, superseded_was: {artifact_id: null}}`.
  `after`: `{pass_ids, segment_ids, repointed: [{kind, id, segment_id}], choice_id}`. Ids and
  geometry only.
- **Inverse** `segment.unconvert`, params from `after`: hard-deletes exactly those
  `segment_ids`, `pass_ids`, their versions and the choice row (these rows have existed only
  inside this one action's effect); clears each `segment_id` it set on a re-pointed record;
  clears `geometry_superseded_by_pass_id`. The block of boxes was never changed, so nothing is
  "restored": it is simply the truth again. **Refused** (`ConversionHasDependents`, with the
  count) when any later audit row names one of those `segment_ids` or `pass_ids`.
- One document for each invocation: `document_id` is a single string, never a list.
  `source.store.no-batch-rewrite` gets a guardrail as well as a test: a script fails if any
  function in `db/migrations/` references `Segment` or `save_many` on segments, and if any
  action's params model takes a list of document ids for conversion.

**After conversion**, the app's existing region verbs (move, delete, combine, add) go to
`segment.update`, `segment.delete`, `segment.merge`, `segment.create`. The route
`PUT /api/artifacts/{artifact_id}/regions` stays, and decides: not converted →
`segment.convert_and_edit`; converted → translate the edit into segment actions. The app does
not change in this slice (it still sends box indexes; the route maps an index to the segment
whose `metadata.box_index` it is). Moving the app to segment ids is the editor's work.

**Re-pointing exact matches.** In step (4): for each annotation, claim evidence anchor and
content representation of the document whose `SourceAnchor.rect` equals a converted box's rect
**to within 1e-6 on all four numbers, on the same `rendition_id`**, set its `segment_id` (a new
optional field on those records, added on open) and list it in `after.repointed`. A record
with no exact match is left as it is and listed in the action's result as `not_repointed`
with its id and the reason. Nothing is re-pointed by overlap or by nearness.

**ChangeSpec.** `domains=["segment","artifact","document"]`; `segment_ids`, `pass_ids`,
`artifact_ids`, `document_ids`; event type `segment.converted`.

**Refusals** (typed, each tested): a second conversion (`AlreadyConverted`); a document with no
boxes (`NothingToConvert`); undo with dependents (`ConversionHasDependents`); a superseded
block read outside the permitted list (`GeometrySuperseded`); any `legacy:` id in `edit`.

**Tests, by behaviour** (all in a temporary library built the way `tests/conftest.py` builds
one; never a real library).
- `source.store.ids-on-first-edit`: open a document with boxes and read it through the seam
  ten times: no `segments` rows, no artifact `updated_at` change. One region move: rows exist
  for **every** artifact's boxes, one pass each; the moved box's segment has the new rect; ids
  from the seam are no longer provisional. A second move converts nothing more (pass and
  segment counts unchanged but for versions).
- `source.store.conversion-undo-leaves-nothing`: convert-and-edit, then undo through the
  generic undo route: **zero** segment, pass, version and choice rows for the document; the
  artifact row equals its pre-conversion dump byte for byte; the seam returns provisional ids
  again. Convert, make one more edit, try to undo the conversion: refused, count is 1.
- `source.store.conversion-repoints-exact-matches`: an annotation whose rect equals a box gains
  that segment's id and loses it on undo; one that is off by 0.01 is reported, unchanged.
- `source.store.one-page-per-conversion` / `.no-batch-rewrite`: converting document A leaves
  document B's artifacts and row counts untouched; the guardrail script passes, and fails on a
  fixture migration that writes segments.
- Old library: a database made before slices 3 to 6 opens twice with no error and no new
  rows; its first region edit converts.
- A claim whose evidence anchor was not re-pointed still reveals its source after conversion
  (the span resolver is on the permitted-readers list).

## App slice A — the app reads the seam into one store and draws from it (#4954)

Starts when engine slices 1 and 2 are committed. App only. **Nothing new is editable**; a page
must look the same before and after.

**Pins:** `source.app.one-segment-store`, `source.app.overlays-draw-from-the-seam`,
`source.app.segment-events-patch-in-place`, and the app half of `source.one-store`.

**What exists (read on disk 2026-09-19 by a code worker; re-read before editing).**
- **No store owns geometry today.** `OCRGeometrySelection` (`Models/OCRGeometrySelection.swift`)
  decides which artifact's boxes are shown (`loadSelected(documentId:using:)`, ranking
  hand-curated over `text_geometry` over transcription, aligned transcript and regions) and
  fetches them itself through `ArtifactService`, bypassing `ArtifactStore`. `ArtifactEntityStore`
  holds only a per-document `revisions` counter that makes overlay `.task(id:)` keys re-fire
  (→ #4890).
- **Two drawing paths, one decision.** Over an image: `OCRGeometryOverlay` (one `Canvas`), called
  from one site (`ZoomableImagePreviewMac+Overlays.swift`), behind the frame gate
  `geometryFrameMatchesDisplay` (`+Renditions.swift`). Over a PDF: `PDFPageWithToolbar` keeps
  its own `@State ocrGeometry`, filters by page index (`boxesForDisplayedPage`), and has no
  frame gate. Both call `OCRGeometrySelection.loadSelected`.
- **The draw model** is the hand-written `OCRGeometry` / `OCRGeometryBox`
  (`Models/OCRGeometry.swift`), mapped from the generated type in `OCRGeometry.init(generated:)`.
  Views never touch `Components.Schemas.*`. Selection is by index into the full box list
  (`RegionSelection`: artifact id, document id, indices).
- **The service shape to copy:** `ArtifactService.getArtifact(id:)` (generated client call,
  exhaustive switch on the typed response, map to an app model).
- **Events:** `ChangeEventConsumer` (`Services/LibraryChangeStream.swift`: `changeDomains`,
  `apply(_:)`, `resync()`), registered with `LibraryChangeStream.register`. The one store that
  patches by id today is `DocumentStore+ChangeStream.swift` (pending ids, debounced per-id
  patch; delete splices by id). `ArtifactStore` and `AnnotationStore` reload a whole scope.
- **Platforms:** the image overlay's only call site is inside `#if os(macOS)`; iOS and iPadOS
  draw no boxes over images today. `PDFPageWithToolbar` is not gated. `Models/OCRGeometry*.swift`
  import no AppKit.
- **Tests:** every geometry test is a pure unit test. **Nothing mounts a view**: there is no
  ViewInspector, hosting-controller, snapshot or UI test on this path, and no harness for
  "render with fixture data and assert on what is drawn".

**The design.**

1. `Services/SegmentService.swift` — `listDocumentSegments(documentId:artifactId:kind:)` calling
   the generated operation for `GET /api/segments/document/{doc_id}` (name from the regenerated
   client), switching exhaustively on the response, returning app models. No URL is written by
   hand (`check_swift_hand_rolled_urls.py`).
2. `Models/Segment.swift` — hand-written app models `Segment` and `SegmentPass`, mapped in one
   place (`Segment.init(generated:)`), following `OCRGeometry.init(generated:)`. **Every field of
   the generated type is mapped or named as deliberately dropped** in that one function, with a
   test that fails when the generated type gains a field (the known defect on this seam is a
   hand mapping that silently loses a field). `SourceAnchor` is generated as two types (input
   and output); the app gets one hand-written `SourceAnchorValue` mapped from the output type.
3. `Models/SegmentStore.swift` — `@Observable`, the **single owner**: `segmentsByDocument:
   [String: [Segment]]`, `passesByDocument: [String: [SegmentPass]]`, a load state for each
   document, `load(documentId:)`, `segments(documentId:passId:)`. It is the only caller of
   `SegmentService`. It is not a second store: nothing owns geometry today, and
   `OCRGeometrySelection` stops fetching.
4. **`OCRGeometrySelection` keeps the policy and loses the fetch.** Its ranking becomes a pure
   function over `[SegmentPass]` (a pass made from an artifact carries that artifact's type and
   curation state; if slice 1's `PassRead` lacks a field the ranking needs, the engine adds it
   to `PassRead`, the app does not look the artifact up). One answer to "which pass is shown",
   as today.
5. **One shared function** — `SegmentDisplay.geometry(for documentId:, store:, selection:) ->
   OCRGeometry?`: picks the pass, maps its segments to today's `OCRGeometry` / `OCRGeometryBox`
   draw model (rect from `anchor.rect`; `pageIndex`, text, level from kind, confidence; order by
   `boxIndex` so **index-based selection keeps working unchanged**; `renditionId` from the
   anchors, which the frame gate reads exactly as before). `OCRGeometryOverlay`,
   `RegionInteractionLayer` and `PDFPageWithToolbar` all take their geometry from it. **No
   drawing code changes and no new overlay view.** The PDF path keeps its page-index filter
   (whether it should gain the frame gate is a question below, not this slice).
6. **Events.** `SegmentStore: ChangeEventConsumer`, `changeDomains = ["segment", "artifact"]`.
   `segment.*` with `segmentIds`: re-read that document and **replace only the items whose id
   is in the list** (insert new ones, remove ones now absent), never reassign the whole array.
   `artifact.*` with `documentIds` (segments still come from artifacts until a page converts):
   re-read each named document that is loaded, and replace that document's entry only.
   `ArtifactEntityStore.revisions` stays as it is until the overlays' task keys move to the
   store (then it is removed, in this slice, so there are not two refresh signals).
7. **Provisional ids** are carried on `Segment` and shown nowhere. No visual change.
8. **iOS and iPadOS:** `SegmentService`, `Segment`, `SegmentStore` and `SegmentDisplay` are pure
   Swift and compile everywhere; the PDF path uses them on every platform; the image overlay
   stays Mac-only in this slice (giving iOS an overlay is the editor's work).

**Tests.**
- Pure, unit (Swift Testing, tags `.paleography` and `.models`; each test names the behaviour
  id): the mapping keeps every field; a fixture response maps to the same `OCRGeometry` the old
  artifact path produced for the same boxes (rects, order, page index, rendition id); the
  ranking picks the same winner for passes as it did for artifacts, case by case from
  `OCRGeometrySelectionTests`; `apply(_:)` with `segmentIds` replaces exactly those items (the
  other items are the same instances and the array is not reassigned); an `artifact.updated`
  for a document that is not loaded fetches nothing; an event from before slice 2 (no
  `segment_ids` key) still decodes.
- Engine-backed, integration: against a temporary library, the store's segments for a document
  equal the route's.
- **On screen.** No harness mounts these views, and a source scan is not a behaviour test. So
  this slice is reported as **"not seen working"** until someone has looked: the manager's
  build-and-verify run opens the same document before and after the switch, over an image and
  over a PDF, and compares the boxes (count, position, the frame gate refusing a re-framed
  image, selection by click). If a mounted check is wanted as a test, it is an XCUITest in the
  existing UI session harness that opens a seeded library and asserts on the overlay's
  accessibility value (box count); that needs the overlay to expose one, which is a small,
  honest addition.
- Guardrails: `check_swift_hand_rolled_urls.py`, the OpenAPI client parity check.

**For the maintainer** (morning file): whether the app keeps showing **one** winning pass
(default: yes, today's ranking, unchanged); whether PDF pages take the image path's frame gate
(default: no change in this slice); what, if anything, "provisional" should look like
(default: nothing).

## App slice A, stage 2 — the overlays draw from the store (#4954)

Starts when engine slice 2 (segment ids on events), slice 1b (above) and stage 1's fixes are
committed. **A page must look and behave the same before and after.**

**Pins:** `source.app.overlays-draw-from-the-seam`, `source.app.segment-events-patch-in-place`,
`source.app.index-is-the-engines`, `source.app.curated-pass-stays-on-top`, and the app half of
`source.one-store`.

**One commit wires the store in and removes what it replaces.** The same commit that makes the
image overlay, `RegionInteractionLayer` and `PDFPageWithToolbar` take their geometry from
`SegmentDisplay` also:

1. **Removes `OCRGeometrySelection.loadSelected`'s own fetch** through `ArtifactService`. After
   it, `SegmentStore` is the only thing that fetches geometry. Two owners, even for one
   commit, is the fault this slice exists to prevent.
2. **Removes `ArtifactEntityStore.revisions`** as the overlays' refresh signal; their
   `.task(id:)` keys move to the store's entry for the document. One refresh signal.
3. **Takes a preferred `source_artifact_id`.** Today an artifact selected in the Inspector
   (`FocusedArtifact`) outranks the ranking, unless it is known to be empty.
   `SegmentDisplay.geometry(for:store:preferring:)` takes that artifact's id and shows its pass
   first when it has drawable segments. Without this the Inspector's selection silently stops
   choosing what is drawn.
4. **Carries the engine's index.** The draw model's box gains `engineIndex: Int?`, filled from
   `segment.boxIndex`. `OCRGeometry.displayIndexedBoxes` yields that index where present (the
   array offset only on the old artifact path, which this commit leaves with no callers), and
   `RegionSelection` stores it. A segment that cannot be drawn is left out of what is **drawn**
   and changes no other box's address. Two segments of one pass with the same `boxIndex` is a
   reported error, not a silent sort.
5. **Gives the draw model the hand-drawn fact directly.** `OCRGeometryBox.isHandDrawn` becomes a
   stored value set from `segment.isHandCurated`; the rebuild of `provider: "user"` and
   `source: "manual"` goes. (On decode from an artifact, it is still worked out from those two
   strings, in one place.)
6. **One ranking.** `ranked` and `rankedPasses` share one core over `(type, isHandCurated,
   createdAt)`. A pass is hand-curated when its own maker is a person **or any of its segments'
   is**, which needs the segments, so the ranking is worked out in the store when a document's
   entry changes.
7. **Works out display geometry on change, never in a view's `body`.** `SegmentStore` keeps, for
   each loaded document, the chosen pass and its `OCRGeometry`, recomputed when that
   document's entry (or the preferred artifact) changes. Views read the stored value.
8. **Uses the pass's own text and the segment's page index** (slice 1b), and `pass.provider`.

**Events.** `SegmentStore: ChangeEventConsumer`, `changeDomains = ["segment", "artifact"]`.
`segment.*` with `segmentIds`: re-read that document and replace only the items whose id is in
the list (insert new ones; remove ones now absent); the other items stay the same values in
the same positions. `artifact.*` with `documentIds`: re-read each **loaded** document named,
and replace that document's entry only. An event for a document that is not loaded fetches
nothing. Both of `ChangeEvent`'s init paths deliver the lists (slice 2).

**Follow-up carried, not fixed here:** a pass whose segments all have unset rects is not empty,
can win the ranking, and draws nothing, covering a lower pass with good boxes. Today's path
has the same fault with zero-width boxes (noted on → #4955).

**Tests.**
- Pure: the index test (a pass with an unset-rect segment in the middle; select the box after
  it; the index handed to the edit call is that box's `boxIndex`); duplicate `boxIndex` is
  reported; a machine pass carrying one human segment ranks ahead of a newer machine pass (the
  2026-09-03 case); the preferred artifact's pass wins over the ranking, and does not when it
  has nothing drawable; the mapped `OCRGeometry` equals the old artifact path's for the same
  boxes, **including `text`, `pageIndex` and `isHandDrawn`**; `apply(_:)` with `segmentIds`
  replaces exactly those items; twenty thousand segments: the display geometry is computed
  once for each change, not for each read (count the computations).
- Engine-backed: against a temporary library, a two-page PDF shows each page its own boxes.
- **On screen: "not seen working" until looked at.** Nothing on this path mounts a view. The
  manager's build-and-verify run opens the same documents before and after: an image with
  regions (count and position of boxes; the frame gate refusing a re-framed image), a
  multi-page PDF (each page its own boxes), a page with a hand-drawn region under a newer
  machine run (the region still shows), an artifact selected in the Inspector (its boxes
  show), and **one region edit on a page that has a zero-width box before the edited one**
  (the right box moves). That last check is the one that would have caught stage 1's index
  fault.
