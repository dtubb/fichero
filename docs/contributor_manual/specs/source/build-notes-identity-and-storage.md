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

**The two tables arrive when a library opens, not when someone first looks.** Both models are
registered in `Database._all_schema_models()`, so `_materialize_schema()` makes the empty
tables and their indexes at open, with every other table (this is the ruled default: schema on
open, data on first edit). A read therefore creates nothing, and slice 1's test keeps its
strong form: reading twice changes neither the list of tables nor any row count. (If a
read-only way of opening a library is ever added, it must skip `_materialize_schema`, and the
seam must treat "no such table" as "no rows". The engine has no such path today.)

**Reading by area takes a rectangle.** The route's parameter is `area=x,y,w,h` (fractions of the
image, the form an anchor's rect has), never a grid key: the tile grid is the engine's own
detail and can change. "By area" means **every segment whose box intersects the rectangle**.
A segment is filed under the tile of its centre, so the engine must also return a wide
segment that covers the area and is centred outside it (file it under every tile it covers,
or treat segments larger than a tile as always candidates). **And a small segment can straddle
a tile edge**: its centre, and so its tile, just outside the tiles the rectangle touches, its
box reaching in. So candidate tiles are those of the rectangle **grown by half a tile on every
side**; with the larger-than-a-tile clause that is complete, and a true intersection test then
removes the extras. Tests: a region as wide as the page, centred outside the asked-for area,
comes back; a small segment centred in the next tile whose box crosses into the area comes
back; the same segment wholly outside does not. Any raw SQL fragment used for this is a
**constant** with every value bound (tiles as one list parameter), so that rule can be
checked by a guardrail.

**Locks are taken in the house order: the transaction gate, then the connection lock.**
`_execute` does gate then lock, and a transaction holds the gate for its whole life. `save_many`
must enter `self.transaction()` and start it **before** it takes `_lock`; the reverse order
lets an importer's batch deadlock against a person's open edit. Test: two threads, one holding
a transaction open between two statements, the other calling `save_many`; both finish within
a timeout. When a nested level of a transaction fails, the whole transaction is marked
rollback-only, so a caller that catches the error cannot commit half a batch.

**Bulk writes are one audited action like any other.** `Database.transaction()` is re-entrant;
`save_many` must join it (not issue its own `BEGIN`), so that `segment.create_many` is
registered `atomic=True` and its rows and its audit row commit together or not at all.

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
make a library database **file** with today's `artifacts` table and **no** `segments` or
`segment_passes` table; close it; **open it through `Database` twice**; assert nothing raised, no `segments` rows exist, the artifact
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
- `source.store.bounded-reads`: **the bound is the route's answer as a client receives it.**
  With 200,000 segments in one source, spread as a real source is (500 page documents of 400;
  made with `save_many` in a temporary library; marked `slow`), `GET
  /api/segments/document/{doc_id}?kind=` for one page returns in under 200 ms. Separately, a
  dense page (20,000 segments on **one** page): a read by kind **and by area** (`area=x,y,w,h`) returns in under 200 ms; a whole dense page in one read is measured and
  **reported, not asserted**. Timing the SQL alone does not pin this behaviour. A read with
  no `document_id` is refused. (A lean read path, raw rows to the read shape with no
  intermediate model, is **slice 3b**, needed before the editor's trial, not now.)
- `segment.create_many` is atomic: force the audit write to fail and assert no segment row
  remains.
- No audit row written by these actions contains a `content` or `text` key.
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
`annotation`; **never a claim**: a statement is carried, in the statements step with slice 8,
by adding a `SourceSupport` to the same claim, recorded here as `claim_support` so uncarry
removes exactly that support; copying a `KnowledgeClaim` would say a thing twice in the
graph); `original_id`; `copy_id`; `created_at`. It is what makes a
carry undoable: the copies it lists are what the inverse removes.

**Indexes** (added to `migrate_segment_indices`): `segmentmatchs(from_segment_id)`,
`segmentmatchs(to_segment_id)`, `segmentforwardings(old_segment_id)`,
`segmentcarrys(match_id)`.

**Only live segments take part.** Merge, split and carry refuse (`SegmentNotLive`, naming the id
and why) any segment that has been deleted or merged away, and a `keep_id` that is not live:
otherwise merging a deleted segment writes a newer `merged` note over its `deleted` one, and a
delete quietly becomes a merge. **Every write route refuses a `legacy:` id with a 422**, never
a 500; one parametrized test sends one in every id field of every write route.

**A diamond is not a loop.** People will split a line and later join the parts again by hand,
or split A into B and C and merge those into D. Reaching an id a second time during the walk
is therefore **skipped**, not an error, and each live id is collected once. A real loop is a
cycle of `merged` notes among ids that are not live (X into Y, Y into X, neither restored):
that is what the merge refusal looks for, on merged notes only, and what the walk raises on.
After a split, resolving gives **all** the live parts, and names the primary one (the part
that kept the id; else the first part listed when the split was made, the walk ordering each
level by the note's `sequence`); `/api/locations/resolve` returns
them all (`liveSegmentIds`) and never quietly picks one. Notes about one id are ordered by an
append sequence, not by timestamp alone.

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

**One way back, and versions only go up.** A segment's state returns by exactly one path:
`SegmentVersion`. `restore_version`, the undo of an update, **unmerge and unsplit** all restore
from the snapshot that merge, split and update wrote, and each writes a **new** version equal
to the old one; a version number is never set back, and `(segment_id, version)` is unique in
`segmentversions` after any sequence of actions. No inverse takes geometry from the audit
record; inverses carry ids and version numbers, read from `after`.

**Undoing a change that is no longer the latest is refused.** An inverse names the version the
action left (`expected_version = after.version`), so if the segment has changed since, the
undo is refused as stale, with what changed, and nothing is overwritten. The same holds for
undoing an undo. (`undelete` needs no expected version: a deleted segment cannot change, since
update, merge, split and carry all refuse it, so "is it deleted" is its whole precondition;
its inverse carries the versions from **after** the undelete.)

**Redo is refused until the shared undo route changes (→ #4957).** The generic undo route's redo
leg replays the **original** action's recorded params, `expected_version` included. With
versions only going up, the action and then its undo have each bumped the version by the
time of a redo, so the replayed number is stale and the redo gets a clean 409. That is tested
as the truth (it must not be papered over with a false success), and the answer is **not** to
weaken "versions only go up". The fix is for redo to be **the inverse of the inverse**, worked
out from the undo's own `after` at that moment, never a replay of stored params. That is a
change to the shared registry's redo leg (`api/routes/system/actions_registry.py`), for every
domain at once, with its own tests; it is not to be done inside the segments router. No other
domain combines an expected version with undo today, so segments are the first to need it.

**Typed notes are short.** `reason` and `note` are capped at 200 characters, are an operator's
note, and must not quote a source: they are recorded inside the tamper-evident chain. Whether
any typed words belong there is the maintainer's question (morning file).

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

## Slice 6 — first-edit conversion (#4924). Do not start before #4957 (redo) reports.

Rewritten 2026-09-20 against the code of slices 1 to 5 as committed on `spec/page-model`.
Claims about existing code are graded VERIFIED (read on disk) or INFERRED.

### Corrected 2026-09-20 after the build lane's recon (`agent-work/source-model/recon-slice-6.md`)

The recon checked these notes against the code and found them wrong in six places. Each was
verified again on disk by the spec author before the notes were changed; one of the recon's own
findings was wrong in its mechanism and is corrected here too (combine). Changed: no version
rows at conversion; the pass's text has the same hole as a box's; the primary key is no guard;
combine; the curation log; one `live_geometry` instead of two read helpers; and three small
facts (no `Artifact.updated_at`; the permission check reads ids from params; the helper and its
guardrail were described as existing and do not).

### Assumptions this section is written under (assumptions, not rulings)

Each is the maintainer's to rule; each is in the morning file. If one is ruled the other way,
the part of the design that moves is named.

- **A1. Conversion is lazy**, on a page's first edit (the 2026-09-19 ruling). An eager
  whole-project conversion, if ever wanted, is **this same action with no edit, run once for
  each page after a snapshot**, and nothing else. The design below makes that true: the action
  takes one document, its `edit` is optional, and the ids it makes are repeatable, so a page
  converted eagerly and a page converted lazily end up byte-identical. Nothing batch-rewrites
  a real project; no migration writes a segment.
- **A2. Every result with boxes becomes its own pass**; the working pass is the one the Source
  view was showing (the `artifact_id` the edit names). Conversion never merges or deletes a
  pass. *If ruled otherwise:* only step 2's loop changes.
- **A3. No new free text in the audit chain.** The action's params carry today's
  `ArtifactRegionsEditRequest` unchanged, which already has a `text` field that
  `artifact.regions_edit` already writes into the chain (VERIFIED, `artifacts.py`). Slice 6
  adds no other text: `before` and `after` hold ids, counts and numbers only. `reason` and
  `note` keep their 200-character cap. **One thing to stop on is named under "Text" below.**
- **A4. Not built on:** #4942 (Segments pane), #4950 (recipes as files), #4953 (rights).

### Four things found in the built code that slice 6 must not trip on

1. **A stored segment returns no text and no page number.** VERIFIED:
   `segment_read_from_row` sets `text=None` and `page_index=None`. A box read from the block
   returns both. Converted as the older draft of these notes said, every box on the page would
   lose its words on screen at the first edit. Settled under "Text" below.
2. **The app still draws from `Artifact.ocr_geometry`.** VERIFIED: app stage 2 is held, and
   `ArtifactService.editRegions` takes the edited `Artifact` back and draws its boxes. If the
   block is kept untouched and nothing else is done, a person's move would appear not to
   happen. Settled under "What the old app sees" below.
3. **`audit_id` on a version or forwarding row is not the audit row's id.** VERIFIED: each
   slice 4 and 5 action mints `audit_id = uuid.uuid4().hex` for its rows, and
   `ActionRegistry.invoke` then creates the `ActionAudit` with its own default id. The two
   never meet, so "which audited action made this version" cannot be looked up. Not slice 6's
   to fix, but slice 6 must not copy it. **Wanted from the #4957 lane:** `ChangeSpec` gains
   `audit_id: str | None`; when set, `invoke` uses it as `ActionAudit.id`. One line each side;
   the existing actions then pass the id they already mint. Filed on #4955's list.
4. **A pass with `source_artifact_id` can be made by hand** (`POST /segments/passes`,
   VERIFIED). So "this page has a pass that names an artifact" cannot mean "converted". The
   older draft's `is_converted` is replaced below.

### The one idea: conversion stores exactly what the seam already returns

`segments_from_result(...)` (VERIFIED, `models/segments.py`) is the one function that turns a
block of boxes into `PassRead` + `SegmentRead`s: kinds, anchors, polygons, baselines, the
degenerate-box handling, and who made each box. Conversion **calls that function and saves its
output as rows.** It does not read `ocr_geometry` itself and has no second mapping. One new
function, `rows_from_reads(pass_read, segment_reads) -> (SegmentPass, list[Segment])`, is the
whole translation.

That gives the slice its master test, **"conversion changes nothing you can see"**: the seam's
response for a document just before conversion and just after a conversion with no edit are
equal field for field, except `id`, `pass_id`, `provisional`. Every awkward input in the list
at the end is a case of that one test.

### 1. One audited action, one undo step

`segment.convert_and_edit`, registered `atomic=True`, `undoable=True`.

- **Params:** `document_id: str` (one, never a list), `artifact_id: str | None`,
  `edit: ArtifactRegionsEditRequest | None`. `artifact_id` and `edit` come together or not at
  all (422 otherwise). With neither it is the eager form of A1.
- **Steps, inside the registry's one `db.transaction()`:**
  1. Load the document's artifacts that have boxes and are not yet converted (see 3). If
     `artifact_id` is given and **is** converted: raise `AlreadyConverted` (see 2, the race).
     If there is nothing to convert and no edit: `NothingToConvert`.
  2. For each, `segments_from_result` → `rows_from_reads` → `save` the pass, `save_many` the
     segments, set the artifact's marker (see 3). **No `SegmentVersion` row is written.**
     VERIFIED: a version row is a PREIMAGE, `segment.create` writes none, and
     `snapshot_segment_version` saves the current state and bumps `row.version` in place. A
     converted segment is a new row at version 1 like any created one. Writing "version 1"
     here would leave every segment at version 2 holding a preimage of a state nothing ever
     replaced, break `SegmentStale.changed` and `restore_version`, fail the master test, and
     cost 20,000 single saves on a dense page. The first edit writes the first preimage, by
     slice 5's own path.
  3. **Report** exact matches; re-point nothing (the manager's ruling, 2026-09-20; see "Where a
     lasting segment reference lives" below). Run slice 4's one matching rule,
     `_anchor_matches_segment` (same rendition, all four numbers within 1e-6, never overlap
     or nearness), over the document's readings, marks, source supports and claims, and list
     every match in the result as `would_point: [{kind, id, segment_id}]`. Nothing is written
     to any of the four, and never to the old `KnowledgeClaim.source_segment_id`.
  4. Record the working pass (`SegmentPassChoice`, only when `artifact_id` is given).
  5. If `edit` is given: translate it (see "What the old app sees") and apply it through the
     **same internal functions** the slice 5 actions call, not through `registry.invoke` (a
     nested invoke would write a second audit row). Those internals must be callable without
     the HTTP layer; where a slice 5 action body raises `HTTPException` directly, lift the
     body into a plain function that raises the typed error and let the route map it.
- **`before`:** `{document_id, converted_artifact_ids: []}`. **`after`:**
  `{pass_ids, segment_count, artifact_ids, would_point_count, choice_id,
  edit: {…what the matching slice 5 action records in its own `after`…}}`. Numbers and ids.
  **Not** 20,000 segment ids: they are repeatable from `artifact_ids` (see 2), and a dense page
  must not put a megabyte in the chain.
- **`target_ids`:** the document id and the artifact ids, for the audit row. (Corrected: the
  permission check does not read these. It reads ids from the PARAMS,
  `authz.target_ids_from_params`, VERIFIED; see 5.)
- **ChangeSpec:** `domains=["segment","artifact","document"]`, `document_ids`, `artifact_ids`,
  `pass_ids`; **no `segment_ids` list for the converted boxes** (same reason; the app re-reads
  the page on `segment.converted`), but the edit's own touched `segment_ids` are listed.
- **Any failure in any step marks the transaction `rollback_only`** (VERIFIED: nested
  `Database.transaction()` does this and the outermost level raises). A half-converted page
  cannot exist. `save_many` must run **inside** the registry's transaction, in the house order
  GATE then LOCK; slice 3's review found it opening its own and taking them the other way, and
  that fix is a precondition here. Probe: make the 3rd artifact's `save_many` raise, and
  assert zero rows and no marker for artifacts 1 and 2.

**What slice 6 needs from #4957 (redo).** Today redo replays the original action's name and
params (VERIFIED, `actions_registry.py::undo_action`). For this action that replay is only
correct because of two things this slice guarantees: the conversion part is **repeatable**
(same ids, see 2) and **skipped when already done** (on redo the page is still converted, see
6, so only the edit is re-applied). So: (a) if #4957 keeps replay, `convert_and_edit` must on
replay take the converted branch and apply the edit to the same segment ids; (b) if #4957
moves to "redo is the inverse of the inverse", the inverse action's own `invert` returns the
edit as the matching slice 5 action. Either way **a segment *added* by the triggering edit
must get the same id on redo.** Since the second redo review (a redone step is undone through
its own inverse) redo of an add is an UNDELETE of the same row, so this now holds without
help. The manager has also ruled an optional `id` on the create params, minted repeatably;
if that is built, mint it from the artifact, the word "add" and **the count of all segments
ever made in that pass, deleted ones included**, never from the live position: add, delete,
add again at the same position would otherwise give a deleted segment's id to a new one,
which is the one thing an id must never do. Until #4957 lands, redo of this action is refused with slice 5's typed
refusal, not attempted.

### 2. Identity: provisional ids become real ids exactly once

- **Repeatable ids.** A converted box's id is
  `uuid5(SEGMENT_CONVERSION_NAMESPACE, f"{artifact_id}:{box_index}").hex`; its pass's is
  `uuid5(…, f"pass:{artifact_id}").hex`. Same shape as `_new_id()`. The namespace is one
  constant in `models/segments.py`, never changed. This is what makes A1 true, makes redo
  safe, and keeps the audit payload small. "An id is never given to another segment" holds:
  the id belongs to that box of that result forever. Segments made any other way keep
  `_new_id()`.
- **No forwarding rows are written at conversion.** A forwarding note records that one
  lasting id gave way to another. A provisional id was never lasting: it names a position.
  20,000 notes for a dense page would also be 20,000 rows that say nothing a function cannot.
  Instead one function, `real_id_for_provisional(legacy_id) -> str`, parses
  `legacy:<artifact>:<box>` and returns the uuid5.
- **What a reader holding a provisional id gets afterwards.** Reads: `resolve_segment` and
  `POST /api/locations/resolve` accept a provisional id, map it with that function, and answer
  with the real id and `was_provisional: true` **only if that row exists**; if the artifact is
  not converted the answer is what it is today. Writes: unchanged, refused
  (`ProvisionalSegmentIdError`, 422). A client is told the real id; it is never silently
  written through.
- **Two edits racing on one page.** Both pass the route's "not converted" look. The
  registry's transaction serialises them (GATE then LOCK). The loser re-reads the marker
  **inside** the transaction, finds it set, and raises `AlreadyConverted`. The route catches
  exactly that error and re-routes the same request down the converted branch, once. That is
  the routing decision made again on fresh state, not a fallback. **The primary key is no
  guard** (corrected): `save` and `save_many` are `INSERT … ON CONFLICT (id) DO UPDATE`
  (VERIFIED, `db/__init__.py`), so a second conversion would not fail, it would OVERWRITE,
  and the overwrite would differ from the first: the winner's edit has already moved a box,
  and the loser would write that box back from the block at version 1. A person's edit lost,
  silently. So: the marker re-read is the **first read inside the transaction** (any `db.get`
  inside it takes the gate, VERIFIED by the recon), and, as the real second guard, the action
  does `db.get(SegmentPass, <the repeatable pass id>)` for each artifact before saving and
  raises `AlreadyConverted` if one exists. The race test asserts the winner's moved box is
  still moved. The loser's edit then meets slice 5's compare-and-set like any other edit. Test with
  two threads and a barrier; assert one pass per artifact, one conversion audit row, and
  either two applied edits or one typed `SegmentStale`.

### 3. The block of boxes afterwards, and how the seam chooses

- **The block is kept, untouched, for good**: it is the record of what the machine produced,
  and (see "Text") still the home of each box's words. Conversion and everything after it
  never write `Artifact.ocr_geometry` again. Test: the artifact row's dump, minus the marker,
  is byte-equal before and after conversion, after an edit, and after undo.
- **The marker.** `Artifact.geometry_superseded_by_pass_id: str | None`, additive, added on
  open. **An artifact is converted when its marker is set.** The seam and the action also load
  the pass it names; marker set and pass missing or soft-deleted **raises**
  (`ConversionMarkerDangling`), never falls back to the block. This is per artifact, not per
  document: a machine run after conversion still writes a block today, shows beside the rows
  as a provisional pass, and is converted by the next edit (step 1 converts "not yet
  converted", which is why a second conversion on one document is normal, not refused).
- **The seam** (`list_document_segments`, VERIFIED to return rows and then every artifact
  with boxes): its second loop skips an artifact whose marker is set. That one `if` is the
  whole choice. Without it a converted page returns every box twice; that is the first test.
- **Other readers of the block.** All go through `live_geometry` (see "What the old app
  sees"); only the conversion and the seam's text fill read the raw block.

### Text and page numbers (the hole found in built code)

Until readings hang on segments (slice 8), a box's words have one home: the kept block.

- **The pass's text has the same hole** (found by the recon, VERIFIED: `pass_read_from_row`
  returns `text=None` and `SegmentPass` has no text column). `PassRead.text` is the exact
  string every box's `char_start` and `char_end` count into, and the reader-to-source linking
  runs on those numbers. `pass_read_from_row` gains the same optional source block and
  returns the artifact's own text from it. It is **never rebuilt by joining box texts**: one
  character's difference moves every span after it. The kept block is the home of the pass's
  text as well as each box's, until readings attach.
- `rows_from_reads` stores `metadata["box_index"]` (already what slice 3's sort key reads,
  VERIFIED) and `metadata["page_index"]`.
- `segment_read_from_row` gains the source artifact's block as an optional argument; for a
  row with `metadata.box_index` it returns that box's `text`, and `page_index` from metadata.
  One `db.get(Artifact)` for each pass, which the route already does (VERIFIED).
- A **combined** segment returns its members' texts joined in `_reading_order`, from
  `metadata["member_box_indexes"]` on the kept segment. Computed at read; nothing new stored.
  Combining an already combined segment joins the union of both lists.
- **STOP POINT for the manager, not decided here.** `add` may carry typed `text` (VERIFIED:
  `ArtifactService.editRegions(… text:)`). After conversion there is nowhere lawful to keep
  it: not the block (never written again), not the audit chain beyond what A3 allows, and a
  `metadata["text"]` on the row would be a second home for words that slice 8 then has to
  move row by row. Default taken, reversible: **an `add` with non-empty text on a converted
  page is refused** (`TextNeedsReadings`, 422) until slice 8; an `add` with empty text, which
  is what the rubber-band draw sends, works. If the app sends typed text on add in practice,
  slice 8's smallest part must come before slice 6 instead. INFERRED that it does not; the
  lane should grep the call sites of `addRegion` before building.

### What the old app sees (the app does not change in this slice)

- `PUT /api/artifacts/{artifact_id}/regions` stays and **always invokes
  `segment.convert_and_edit`** (changed 2026-09-20 to what was built, which is better than the
  earlier draft's two routes): the action converts whatever on the page is not yet converted,
  which after the first edit is normally nothing, then applies the edit. One path, one audit
  row for each edit, one undo step, and it is the branch the losing side of a race needs
  anyway. The inverse is the inner action's own, read from the record that action made for
  itself. **Combine is the exception to watch:** it is a merge PLUS a reshape of the kept
  segment, so its inverse must undo both (and remove the `member_box_indexes` it added);
  the merge's inverse alone leaves the kept box as the union on top of the boxes it
  swallowed (step 5 review, FIX FIRST).
- **A moved box carries its outline with it.** The old app sends only a rectangle. The row's
  polygon and baseline are mapped from the old rectangle to the new one (translate, and scale
  when the size changed), never left where the line used to be.
- **An added box takes an ordinary new id.** Repeatable ids are for converted boxes only:
  eager conversion has no add, and redo of an add is an undelete of the same row. (A count
  of "all segments ever made" is not monotonic while `unsplit` hard-deletes parts, so an id
  minted from it can collide and refuse every later add.)
- **Index translation.** The app sends positions in the list it was last given. One function,
  `live_rows_in_order(db, pass_id)` (live rows sorted by slice 3's `_segment_row_sort_key`),
  serves both the projection below and the translation: index *n* is the *n*-th row of that
  list. Never `metadata.box_index` directly, because after a delete the app's positions shift
  and the stored box indexes do not. An index past the end is a typed 422.
- **One function for a result's geometry (the manager's ruling, 2026-09-20; one code path).**
  `live_geometry(db, artifact) -> OCRGeometryResult | None` returns the block when the marker
  is unset and, when it is set, the boxes filled from `live_rows_in_order` with text as above.
  It replaces both helpers the earlier draft named (`read_ocr_geometry` and
  `geometry_for_api`; **neither was ever built**, and the earlier draft was wrong to describe
  them as standing). Every consumer calls it. The recon found **six** that would otherwise
  serve a box's old place after a person's edit (VERIFIED list in the recon, §3.2):
  `_artifact_response` (whole block, and `region_count` and `geometry_rendition_id` on every
  list response); `GET /api/artifacts/{id}/region` and
  `POST /api/documents/{doc_id}/text-regions`, which are how a claim or a search hit finds
  its pixels, so a highlight must never point where a box used to be; and the workflow tools
  `diary_entries`, `align_transcript` and `merge_geometry`. `vision_base`, which WRITES
  `ocr_geometry` onto an existing artifact, refuses a converted one with a typed error.
  The raw `artifact.ocr_geometry` read stays for exactly two callers that want the machine's
  original: the conversion, and the seam's text fill. A guardrail script (to be written in
  this slice, with a fixture that fails it) lists them. The row in the database is never
  touched. The dozen Swift readers that subscript boxes by position keep their invariant
  because both sides use the one ordering. When app stage 2 draws from the seam, the filled
  form is for the old routes only; say so in the docstring with the issue number.
- **Combine** (the recon's mechanism corrected; VERIFIED `_action_merge` makes no new segment:
  it keeps `keep_id`, soft-deletes the others and leaves the kept row's shape untouched).
  The route picks as `keep_id` **the member at the lowest position**, so the kept segment
  keeps its id and its `box_index` and sorts into exactly the slot today's code uses
  (`keep_at = min(indices)`). In the same action the kept segment is then updated to the
  union rectangle, `char_start = min`, `char_end = max` (when every member has them) and
  becomes the person's, which is what today's combine produces; `member_box_indexes` is set
  for the text join. No reorder, no colour change in the Inspector.
- **Order of the other verbs.** `add` has no `box_index`, so it sorts after every converted
  box, by `(created_at, id)`: the end of the list, which is where today's add appends. Today's
  request has no split or carry verb; when the editor adds split, its parts need a place in
  the order (recorded for that slice, not solved here).
- **The curation log (ruled by the spec author).** Today each edit is appended to
  `metadata["curation_log"]` inside the block and the route's docstring says the history
  travels with the artifact. VERIFIED: nothing in the engine or the app ever READS that log.
  After conversion the block is never written again, so the log stops at the first edit and
  stays there as the record up to that point. **Accepted; change the docstring.** From then on
  the history is the segment's own versions and forwarding notes and the audit record: who,
  when and what, for each segment, which is more than the log held. Carrying that history
  out of the app is the export slices' work, from those records. No second log is kept.

### Where a lasting segment reference lives (ruled by the spec author, 2026-09-20; built under #4932, not here)

VERIFIED on disk: four models carry a `SourceAnchor`: `ContentRepresentation.source_anchor`
(a reading), `Annotation.anchor` (a mark), `SourceSupport.source_anchor`,
`KnowledgeClaim.source_anchor`. **Corrected 2026-09-20 (slice 6 lane, checked in code): that is
three stored kinds and one embedded model.** Readings, marks and claims are tables. A
supporting source is not a record of its own: it is embedded in claims and in entities, has no
id, and draws nothing today. "One shape" covers it all the same, which is the advantage of
putting the id in the anchor: wherever an anchor is embedded, the id goes with it, and nothing
has to walk entities (scoped by a list column, so finding them means scanning the project) to
convert a page. Only one has anywhere to put a segment id today,
`KnowledgeClaim.source_segment_id`, and it means something else: it is supplied by the client
on claim create and patch (`api/routes/claim/claims.py`), published in the contract, produced
by nothing in the engine, and historically names an entry in a segmentation artifact's
`data["segments"]`, not a `Segment` row.

- **One shape, not four: `SourceAnchor.segment_id: str | None`.** All four already carry the
  anchor, the anchor is stored as one JSON value inside each record, so the field is additive
  with no migration, and an old record simply reads `None`. It is what
  `source.statement.on-segment` already says: the id, with a copy of the anchor beside it.
  The stored rectangle stops being the pointer and becomes **the record of where the ink was
  when it was pointed at**; the id is the pointer. That is "ids never move" applied to
  pointing: the rectangle may go stale, the id cannot.
- **Rules on the field.** Set only by the engine or checked by it: never provisional
  (`assert_not_provisional`); the segment's document must equal `anchor.document_id`; a
  `Segment`'s own `anchor.segment_id` is always `None` (a validator on `Segment`; a segment
  does not point at a segment, and `refines` stays what it is).
- **Reading it.** One resolver, `resolve_anchor(db, anchor) -> ResolvedAnchor`: with a
  `segment_id`, follow slice 4's `resolve_segment` to the live segment and answer with ITS
  current shape; if it ended in a delete, answer with the stored rectangle and say so. Without
  one, the anchor's own numbers, as today. Every place that turns an anchor into pixels calls
  it. No index is needed: "everything resting on segment X" is always asked inside X's
  document, which is how slice 4's `_records_anchored_to` already looks (by document, then
  filter).
- **The old `source_segment_id`: left exactly as it is.** Not renamed (it is in the published
  contract and in generated Swift), not reused (two meanings in one column of real projects is
  not acceptable, as the manager ruled), never written by source-model code. Its contract
  description changes to say what it is: "names an entry in a segmentation artifact; not a
  segment record; use `source_anchor.segment_id`". Existing values are untouched and never
  read as row ids. Removing it is a contract change for a later release, not this work.
- **What deferring costs, plainly.** An anchor is a stored rectangle. After a person moves a
  box on a converted page, a mark, reading, support or claim anchored BY RECTANGLE to the old
  place still shows the old place. Nothing re-points anything today either, but today nobody
  can move a box that something else rests on and then see both. Smaller than it sounds for
  claims: they mostly point by CHARACTER span (VERIFIED by the recon: no KG, claim, search or
  embedding code reads geometry), and a span finds its pixels through `live_geometry`, so it
  follows a moved box as soon as slice 6 lands. The cost falls on anchors that carry a
  rectangle: marks a person drew, and any reading or claim saved with a box.
- **What a person actually sees, by kind** (slice 6 lane, checked in the app's code and pinned
  by three tests; recorded on #4932). After a box is moved: a **mark** stays where the box
  used to be, because every rectangle a mark draws (wash, underline, strike, star, check, note
  glyph, the note editor's place, the hit test) comes from its stored rectangle through one
  accessor, `AnnotationService.regionRect`, and the crop popover's picture is cut by the engine
  from the stored rectangle too. A **claim** follows the move by character span and not by
  stored rectangle, and on a PDF the page view draws the rectangle and returns before the span
  branch, so a claim carrying both draws at the old place. A **supporting source** and a
  **reading** draw nothing yet. **This is not new with conversion**: today's move changes the
  block's box and leaves the mark's rectangle alone in exactly the same way. Conversion makes
  it matter, because curating boxes becomes ordinary. Also corrected: `/region` and
  `/text-regions` have no call site in the app; it resolves spans itself from the artifact
  route (now live). Those two routes stay live for MCP and later callers.
- **The link is NOT lost when a box moves** (a point on which the lane's note and this ruling
  differ, and the difference is the whole value of the interim). Matched against the LIVE row,
  an old rectangle matches nothing the moment the box moves, and nothing can recover it. The
  interim below does not match against the live row. It matches against the **kept block**,
  whose boxes never move, and the block box's position gives the repeatable id. So the link
  from "the rectangle this mark was made from" to "that box's segment" can be found at any
  later time, for good. It follows that the list of matches reported at conversion is a
  convenience, not the only evidence, which is one more reason it does not belong in the
  permanent record (slice 6 review, FIX FIRST 3).
- **A cheap interim that stores nothing (recommended; can follow slice 6 directly).** The kept
  block never changes, so it is a permanent table from "the rectangle a box had" to "the box's
  position", and position gives the repeatable id. In `resolve_anchor`, for an anchor with no
  `segment_id` on a converted result: find the block's box whose rectangle equals the anchor's
  by slice 4's one rule, take its repeatable id, and resolve that. A pure function; nothing
  written; and when #4932 later stores the id it stores the same one. It only helps anchors
  that matched a box exactly, which is the only case slice 6 would have re-pointed anyway.
- **Does the interim rescue marks? The engine half does; the app must ask.** Proposed as its
  own small slice, **6b, under #4932, straight after slice 6 and ahead of slice 8**, because a
  mark in the wrong place is the one thing here a person can see. It is NOT app stage 2 (that
  is the overlays drawing from the store, held, and much larger).
  - Engine: `resolve_anchor`; the annotation and claim reads gain a `resolved_anchor` beside
    the stored one (the stored one is never rewritten); the crop popover's cut uses the
    resolved rectangle. Tests: mark a line, convert, move the line → the read's resolved
    rectangle is the new place and the stored one is unchanged; a free rectangle that matches
    no box resolves to itself; a mark on a deleted segment resolves to its stored rectangle
    and says the segment is gone.
  - App, one accessor: `AnnotationService.regionRect` returns the resolved rectangle when the
    read carries one, else the stored one. Every mark drawing already goes through it. And
    the PDF page view prefers the resolved anchor over the stored rectangle before returning.
    Mounted tests, not source scans: the wash is drawn at the new place after a move.
  - A mark a person drew free, matching no box, stays where they drew it. That is right: it
    was about a place, not about a line.

### 4. Who made what

- The pass and each segment get exactly the `provenance_kind` `segments_from_result` derives
  (VERIFIED: `_derive_pass_provenance_kind`, and `_box_is_hand_drawn` for a box a person drew
  into a machine result). A machine's boxes are stored as the machine's, a hand-drawn box as
  the person who drew it, an unknown as `unknown`. **Never the converting person's.**
  `created_by` on converted rows is the artifact's provider or `None`, never `ctx.actor`.
- Only the triggering edit is the person's: the touched segment goes to version 2 by slice 5's
  own path (its preimage row names `ctx.actor` as the one who changed it), its
  `provenance_kind` becomes human, and that segment alone becomes human-curated.
  Probe: convert a 50-box machine page with one move; assert 49 rows still `workflow`, one
  `human`, and the app's ranking core (pass is human OR any segment is) now ranks that pass as
  hand-curated, which is today's behaviour after a region edit.

### 5. Multi-user

- The route uses `get_library_database_for_write`; the registry checks
  `authz.assert_can_write` for every id in params (`document_id`, `artifact_id`), which after
  #4917 resolve to the document and its folders (VERIFIED in review). No new check is written.
- Tests, mounted through the route: a viewer's first edit → 403, **zero** segment rows, no
  marker, artifact byte-equal; an editor denied this document → 403, same assertions, and the
  same editor succeeds on another document; an editor denied a folder above → 403. The
  conversion must not run before the check: assert on rows, not only on the status code.
- **The artifact must belong to the document (the manager's ruling; security).** The
  permission check resolves `document_id` and `artifact_id` from params independently, so an
  `artifact_id` from ANOTHER document passes both if the person may write both. The action's
  first step after the marker read: `artifact.document_id == params.document_id`, else a typed
  422 (`ArtifactNotOfDocument`), nothing written. Test it. VERIFIED the same gap in one built
  action: `segment.pass_create` accepts a `source_artifact_id` from another document (and one
  that does not exist) without a check. Harmless-looking today (it copies provider and model),
  but once the seam fills text from the source block it would show document B's words on
  document A's page to someone who may not read B. Fix with this slice or before it.
  `segment.match_propose` does not check that its two segments share a document either;
  create, create_many, update, delete, undelete, merge and split do check (VERIFIED); carry
  checks each copy's anchor against its segment, and inherits whatever its match allowed
  (INFERRED, not traced).
- A person allowed the edited artifact's document converts **all** its results' boxes. They
  all belong to that one document, so one check covers them. Say so in the docstring.

### 6. Undo: the edit is undone, the conversion is kept

The older draft, and the spec rule it pinned, had undo delete every converted row and return
the page to provisional ids. That **is achievable** (the block is untouched, the ids are
repeatable), but it is the wrong trade, and the rule is changed in `segments-and-geometry.md`
in the same commit as these notes:

- It needs the only **hard delete** in the segment store, of up to 20,000 rows plus their
  versions, behind a "has anything depended on these since" test. That test cannot be written
  simply: after edit 2 and its undo, the rows carry versions 3 and 4 from actions that are
  all undone, and with redo changing under #4957 "later actions that still count" is a moving
  definition. When the test says no, the person's **first edit cannot be undone at all**,
  which is the worst outcome on the table.
- Keeping the conversion costs nothing anyone can see: the master test above is exactly the
  statement that a converted, unedited page reads the same as an unconverted one.
- It is what A1 needs anyway: if conversion can be run with no edit, it must be harmless to
  leave in place.

So: `invert(before, after)` returns the inverse of **`after.edit` only**, as the matching
slice 5 inverse (move → `segment.update` back to the recorded geometry with the recorded
version; delete → undelete; combine → unmerge; add → delete), through slice 5's own inverse
builders. It reads only `after`, as slice 5's review required. The marker, passes, rows and
version 1s stay. Undo of the eager form (no edit) is refused: `NothingToUndo`. The trap the old
rule closed (the old inverse restoring the artifact beside new rows) stays closed, because
`artifact.restore` is never the inverse of anything on a converted artifact; test that
`artifact.regions_edit` is unreachable once the marker is set.

Recorded in the morning file as a default taken, reversible: a true "unconvert" can be added
later as its own owner-only action precisely because ids are repeatable.

### 7. Behaviours, data, existing data, tests

All tests in a temporary library built as `tests/conftest.py` builds one. Never a real one.

| Behaviour | Data | Existing data | Test |
| --- | --- | --- | --- |
| `source.store.ids-on-first-edit` | rows + marker appear at first edit | reading ten times writes nothing; the artifact row's dump is byte-equal (`Artifact` has no `updated_at`) | one move → a pass for every result with boxes; ids real; second move converts nothing |
| `source.store.conversion-changes-nothing-seen` (new) | none beyond the above | the master test, run over every awkward input below | seam before == seam after, but for `id`, `pass_id`, `provisional` |
| `source.store.conversion-ids-repeatable` (new) | uuid5 ids | eager and lazy agree | convert a copy of the same fixture twice in two libraries: identical ids; a provisional id resolves to the real one on reads, is refused on writes |
| `source.store.converted-boxes-keep-their-maker` (new) | `provenance_kind`, `created_by`; no version rows at conversion | a hand-drawn box inside a machine result stays the person's | the 50-box probe in 4 |
| `source.store.undo-first-edit-keeps-conversion` (replaces `…conversion-undo-leaves-nothing`) | inverse from `after.edit` | block never restored | move, undo: geometry back, version 3, rows and marker remain, block byte-equal; `artifact.regions_edit` refused on a converted artifact |
| `source.store.one-page-per-conversion`, `.no-batch-rewrite` | one `document_id` | document B untouched | guardrail script as in the older draft, plus: params model has no list of documents |
| `source.store.conversion-reports-exact-matches` (replaces `…repoints…`) | none written | every record left byte-equal | an exact match is listed with the segment id it would take; one off by 0.01 is not; all four record kinds byte-equal after |
| `source.store.old-app-still-works` (new) | projection + index translation | the app's positions | move, delete, then move "index 3": the box moved is the one the projection listed fourth |

**Awkward inputs to probe when the build is reviewed** (each is a row of the master test
unless it says otherwise):

- An undrawable box: stored with the anchor's rect unset and `metadata.geometry_problem`,
  bbox columns zero, still a row, still in order, still holding its position so later indexes
  do not shift (the app's zero-size placeholder relies on this).
- Gaps or repeats in stored box indexes: cannot arise from `segments_from_result` (index is
  list position); if `rows_from_reads` is ever handed them it **refuses the pass**
  (`BoxIndexesNotContiguous`) and the whole action rolls back.
- A pass whose source artifact has since been removed (INFERRED: artifacts are hard-deleted;
  no soft-delete field found on `Artifact`): the seam returns the rows with `text=None` and
  no `artifact_type`, and does not raise. A marker can no longer dangle, the artifact is gone.
- A result with an empty box list, and a document with none: no pass is made for it; with an
  edit of `add`, conversion makes the one empty pass for `artifact_id` so the new box has a
  pass to live in (today's "bootstraps an empty user geometry").
- A dense page, 20,000 boxes. Two separate bounds, measured, not quoted from a comment: the
  **read** by area stays under slice 3's 200 ms bound on the converted page; the **conversion
  itself** is measured and reported, with no bound asserted until there is a number (one
  `save_many` for segments, no version rows; never a row-at-a-time loop; audit payload under
  10 kB, asserted).
- A multi-page PDF result: `page_index` survives conversion for every box.
- Polygons and baselines: present before, equal after.

### What an app slice would need once this engine half exists (app stage 2 stays held)

Listed only; nothing here is to be built.

1. Draw overlays from `SegmentStore`, not `Artifact.ocr_geometry`; then the engine's
   projection (`geometry_for_api`) is deleted. Same issue, two halves, in that order.
2. Edit by segment id and `expected_version` through the slice 5 routes; stop sending box
   positions. The zero-size placeholder rule stays until then.
3. On `segment.converted`, re-read the page and swap provisional ids for real ones
   (`real_id_for_provisional` has a Swift twin, or the app simply re-reads; prefer re-read).
4. Selection held across conversion: a selected provisional id maps to its real id, so the
   box a person just moved stays selected.
5. Show a typed `SegmentStale` as "this box changed elsewhere", not a generic failure.
6. Add-with-text waits on slice 8 (see the stop point).
7. The Swift tests on this branch have still never been executed; run them before any of it.

## Owed after the redo reviews (#4957; before the segment editor, and before slice 6's `combine`)

From `reviews/redo-4957-review.md` and `-review-2.md`. Agreed with the safety set's request.

1. **`expected_versions` on `segment.merge`, `segment.split`, `segment.carry`, and on
   `unmerge`, `unsplit`, `uncarry`**, one number for every segment the action touches, compared
   before anything is written (`SegmentStale`, as update and delete do). Each forward action's
   `after` gains `versions` for every id it touched, so the inverse worked out from that `after`
   carries fresh numbers on every lap, and the replay path's refresh has something to read.
   Tests, through the undo route, on rows: redo of a merge after another person reshaped a
   member is refused; undo of a split after another person edited a part is refused, and the
   part is still there.
2. **`unsplit`, `uncarry` and `match_withdraw` soft-delete**, and the redo of split, carry and
   propose restores what they removed (as redo of create now restores rather than re-creates),
   so part, copy and match ids come back the same. `unsplit` is today the one hard delete in
   the store; after this there is none.
3. **Undelete, unmerge and unsplit refuse** when the segment's pass or parent is no longer
   live, with a typed reason; never a live segment in a deleted pass.
4. Slice 6 inherits all three through `combine` (a merge) and `add` (a create).

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
4. **Keeps a box's position equal to the engine's index; does not add a second index.** About
   a dozen readers address a box by its **position in `OCRGeometry.boxes`** and hand that
   number to the engine (`RegionInteractionLayer`, `ZoomableImagePreviewMac+Regions`,
   `+Annotations`, `+RegionEntry`, `RegionSelection`; found by search, 2026-09-20). Stage 1's
   `engineIndex` reaches only one of them (`displayIndexedBoxes`), so one dropped box would put
   two kinds of index into one selection. So the mapping keeps the invariant they all rely on:
   **an undrawable segment stays in the list, at its place, as a box marked not drawable**
   (zero-size rect; never drawn; never hit), which is what today's zero-width boxes already
   are. While mapping, `boxIndex` values must be exactly `0 ..< count`, no gap and no repeat,
   or the pass is refused and reported. `engineIndex` leaves the box type (it is part of the
   synthesised equality today, which makes the same boxes unequal across the two paths).
   Addressing by id, not index, arrives with the editor, when converted pages stop having a
   box index.
4a. **Says where `ocrGeometryArtifactId` comes from, because nothing else will.** Every curation
   verb (move, delete, combine, promote) sends its edit to the artifact named by
   `ocrGeometryArtifactId`. Today that value is set by `loadSelected`'s fetch
   (`selected?.artifactId`). When the fetch goes, **it is the chosen pass's
   `source_artifact_id`** (slice 1's `PassRead` carries it for this), set in the same place the
   chosen pass is decided, and nowhere else. It is a plain optional string: a wrong value
   compiles, and sends a person's edit to the wrong result **without any error**. So it has a
   behaviour and a test of its own (below).
4b. **Two one-line guards for zero-size boxes**: `RegionHitTesting.pick` and
   `OCRGeometryOverlay.hoveredBox` skip a box with no area, so a placeholder can never be hit
   or hovered. Nothing depends on hitting a zero-width box today.
4c. **The readers that address a box by position: ten, confirmed by the app lane's reading**
   (`agent-work/source-model/recon-app-slice-A-stage-2.md`), none of which needs to change
   under point 4. They include `AnnotationMarkRendering.wordIndices` and
   `promoteSelectedWords`. `ArtifactPanel+Regions.swift` is **out of scope**: it is the
   Inspector's view of one artifact's own boxes, not a view of a source's segments, and stays
   on the artifact.
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

**Which document the PDF page asks for, and whether the seam answers (checked on disk,
2026-09-20).** `PDFPageWithToolbar` asks for `effectiveGeometryDocumentId`: the **page child's**
id when the pane is on its own page (then every box is shown: `isPageScoped`), otherwise the
**parent PDF's** id (then boxes are filtered by `pageIndex`). Today's fetch is strictly for
that one document (`OCRGeometrySelection.loadSelected` calls `getArtifacts(forDocumentId:,
includeDescendants: false)`), and the seam's query is the same rule (`db.query(Artifact,
document_id=doc_id)` in `api/routes/document/segments.py`: that document's own artifacts, no
children, no parent). **So the seam returns for either id exactly the artifacts today's path
would consider, and there is no slice 1 gap here.** With slice 1b's `page_index`, the parent
case filters as it does today. Stage 2 must pass the same `effectiveGeometryDocumentId` to the
store, not the rendered document's id.

**One case will look different, on purpose, and should be looked at.** Today's ranking works on
a lean list of artifacts that has no boxes in it, so it **cannot see** a hand-drawn box inside
a machine result; the code says so, and says why (looking would cost a fetch for each
candidate). So today a newer machine run does cover a person's region that was drawn into an
older machine result. With every segment already in hand, the ranking can see it, and the
2026-09-03 rule is at last honoured in that case: the curated pass stays on top. "A page looks
the same" is therefore true **except** where today's behaviour falls short of the ruled one.
The verify run should include this case and expect the curated result.

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
- Pure: the index test (a pass with an unset-rect segment in the middle: the mapped list has
  the same count as the pass, the box after it sits at its own `boxIndex`, the placeholder is
  not drawable and cannot be hit); a gap or a repeat in `boxIndex` refuses the pass; a machine pass carrying one human segment ranks ahead of a newer machine pass (the
  2026-09-03 case); the preferred artifact's pass wins over the ranking, and does not when it
  has nothing drawable; the mapped `OCRGeometry` equals the old artifact path's for the same
  boxes, **including `text`, `pageIndex` and `isHandDrawn`**; `apply(_:)` with `segmentIds`
  replaces exactly those items; twenty thousand segments: the display geometry is computed
  once for each change, not for each read (count the computations).
- **An edit goes to the chosen pass's artifact** (`source.app.edits-name-the-chosen-pass`): after
  the switch, perform a region move through the same code path a drag takes; assert the
  artifact id sent to the engine equals the chosen pass's `source_artifact_id`; and again with
  an artifact preferred from the Inspector (the id follows the preference); and with no pass
  chosen (no id, and the verbs are disabled, not sent with a stale one).
- A zero-size placeholder is never returned by `RegionHitTesting.pick` or `hoveredBox`.
- Engine-backed: against a temporary library, a two-page PDF shows each page its own boxes; a
  parent PDF id and a page-child id each return what today's strict fetch for that one
  document would.
- **On screen: "not seen working" until looked at.** Nothing on this path mounts a view. The
  manager's build-and-verify run opens the same documents before and after: an image with
  regions (count and position of boxes; the frame gate refusing a re-framed image), a
  multi-page PDF (each page its own boxes), a page with a hand-drawn region under a newer
  machine run (the region still shows), an artifact selected in the Inspector (its boxes
  show), and **one region edit on a page that has a zero-width box before the edited one**
  (the right box moves). That last check is the one that would have caught stage 1's index
  fault.
