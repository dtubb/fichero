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
