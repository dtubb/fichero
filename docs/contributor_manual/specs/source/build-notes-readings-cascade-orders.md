# Source Model — Build notes: readings, the cascade, orders and links (slices 8 to 10)

> Milestone: source-model
> Manual: TBD — none of its own; engineering notes behind `readings-and-apparatus.md`,
> `languages-scripts-signs.md` and `segments-and-geometry.md`.
>
> **Status: DRAFT.** Engineering detail for the engine worker, one section for each slice. The
> maintainer does not need to read this file; nothing here changes the design. No behaviours
> of its own. Code facts were read on disk on 2026-09-19; the worker re-reads each file before
> editing it. Ids keep the code's current nouns. The standing rules and the rule about what an
> audit record may carry are in `build-notes-identity-and-storage.md` and apply here.

## Slice 8 — readings on segments, and "which counts" worked out (#4934, #4929, #4932)

**Pins:** `source.reading.set`, `.kinds`, `.level-recorded`, `.read-from`,
`.author-and-guideline`, `.corrections-are-new`, `.equal-alternatives`,
`.chosen-is-worked-out`, `.chosen-follows-project-rule`, `.machine-is-labelled`,
`.maker-set-by-engine`, `.written-read-pair`, `.stretch-names-its-reading`,
`.char-confidence-on-line`; `source.pass.working`, `source.pass.working-follows-project-rule`;
`source.point.by-id-or-span`, `source.point.text-is-derived`. (`source.statement.*` is its own
later step: claims gain a segment id in slice 6's re-pointing and nothing more here.)

**What exists.** `ContentRepresentation` (`models/__init__.py`): `id`, `document_id`, `kind`
(a **closed** enum: transcription, normalized_text, translation, transliteration, markdown,
html, svg), `content`, `language`, `script`, `source_anchor`, `parent_representation_id`,
`derived_from_representation_id`, `producer_run_id`, `producer_tool`, `producer_model`,
`review_state` (source, draft, reviewed), `created_at`. `ContentRepresentationRevision`: a
person's revision, with `reviewer: str = "human"` **as a default the caller can leave or set**.
Routes in `api/routes/document/content_representations.py`: list for a document, list
revisions, and one action, `representation.revise`.

**A reading IS this record, grown. No second record.**

`ContentRepresentation` gains (all optional, added on open; no data migration):

| Field | Type | Notes |
|---|---|---|
| `segment_id` | str \| None | the segment it reads. `document_id` stays required. Never a `legacy:` id |
| `level` | str \| None | how normalised: shipped defaults `as_written`, `expanded`, `normalised`; open list |
| `read_from_rendition_id` | str \| None | the image it was read from |
| `guideline` | str \| None | the transcription convention it follows |
| `provenance_kind` | `ProvenanceKind` | **engine-set** from how the write arrived; never in a params model (→ #4868, → #4869) |
| `machine_confidence` | float \| None | for the whole reading |
| `char_confidences` | list[float] \| None (JSON) | one for each character, where the recogniser gave them |
| `char_positions` | list[float] \| None (JSON) | each character's place along the line (0 to 1), so no character segments are needed |
| `corrects_representation_id` | str \| None | a correction names what it corrects |
| `pair_id`, `pair_role` | str \| None | written-and-read pairs: same `pair_id`, roles `written` and `read` |
| `campaign_ids` | list[str] \| None | which campaigns it takes in (used from slice 14) |
| `sign_map` | dict \| None (JSON) | position to declared sign (used from slice 14) |

**`kind` opens.** The column is already a string. The enum becomes a string field checked
against a vocabulary table, following the project's existing pattern for an extendable list
(`library_entity_types`): new table `libraryreadingkinds` (`key`, `label`, `builtin: bool`),
seeded idempotently on open (a migration function in `db/migrations/schema.py`) with
**exactly today's seven values plus** `as_read_aloud`, `description`, `coordinate`, `music`,
`drawing`. (The design's "as written / expanded / normalised" are **levels** of a
transcription, not kinds.) Every `match` or `==` on `ContentRepresentationKind` in the engine
and every Swift `switch` on the generated enum is a call site: the worker lists them with
`find_references` before editing, and the generated Swift type changes from an enum to a
string, which app code must absorb in the same slice. A test proves an unknown kind
round-trips and an old row still reads.

**The revision's `reviewer` default is the same defect as machine claims stored as human.** It
becomes `provenance_kind`, engine-set; existing rows are read as they are (never rewritten);
a test sends `reviewer="human"` from an MCP context and sees `agent` recorded.

**"Which counts" is worked out.** New record `ReadingChoice` (table `readingchoices`): `id`,
`document_id`, `segment_id`, `kind`, `representation_id`, `chosen_by`, `chosen_at`,
`superseded_at` (a later choice supersedes; rows are never deleted). Beside it, slice 6's
`SegmentPassChoice`. One pure function, `resolve_counting(project_rule, choices, candidates)
-> CountingAnswer { representation_id | None, basis: "chosen" | "newest-human" |
"newest-machine-unchosen" | "none", labelled_machine: bool }`:

- a live human choice wins, in any project;
- **strict** project, no choice: the newest reading is returned with basis
  `newest-machine-unchosen` (or `newest-human`) and `labelled_machine` true when a machine made
  it: shown, labelled, not the record;
- **relaxed** project, no choice: newest counts, a person's outranks a machine's;
- the same function, given passes, answers "which pass is working".

The project rule is read through one call, `project_record_rule(db) -> "strict" | "relaxed"`,
which returns `strict` until project settings exist (slice 9 and the projects work give it a
real source). Nothing is stored about counting except human choices, so flipping the rule
rewrites nothing (test: flip, assert zero writes, answers change).

**Actions** (all in `content_representations.py`; params `extra="forbid"`, no `id`, no
`provenance_kind`):

| Action | Params | Audit records | Inverse |
|---|---|---|---|
| `representation.create` | `document_id`, `segment_id?`, `kind`, `content`, `language?`, `script?`, `level?`, `source_anchor?` (worked out from the segment when absent), `derived_from_representation_id?`, `corrects_representation_id?`, `guideline?`, `read_from_rendition_id?` | **`after: {representation_id, segment_id, kind, content_sha256}`: an id and a digest, never `content`** | `representation.retract` (sets `retracted_at`; the row stays) |
| `representation.pair` | `written_id`, `read_id` | ids | `representation.unpair` |
| `reading.choose` | `segment_id`, `kind`, `representation_id` | `before: {choice_id | null}`, `after: {choice_id}` | `reading.choose` of the earlier one, or `reading.unchoose` |
| `pass.choose_working` | `document_id`, `pass_id` | same shape | same |

Undo of a create is a retraction, which needs no content from the audit row. (This is the
default for morning question 8. Today's `representation.revise` is left as it is.)

**A stretch of a reading.** `SourceAnchor.char_start/char_end` already exist. A pointer to a
stretch also carries `representation_id` (an anchor extra today; a named field after slice 7).
When a reading is superseded, a helper re-places the stretch on the new text **only when the
same characters are found exactly once**; otherwise the pointer is reported as unplaced. Never
re-measured by position alone.

**A page's text is worked out.** `document_text(db, document_id, *, pass_id=None, order=None,
kind="transcription", include_furniture=False) -> DerivedText { text, spans: [{segment_id,
representation_id, start, end}] }`, from the working pass, its *as written* order (slice 10;
until then, box order) and the counting reading of each segment. Today's `Document.page_content`
and artifact `content` are **not** rewritten; consumers move to this call one by one, each in
its own commit.

**Routes.** `GET /api/segments/{segment_id}/readings` (list, with the counting answer);
`POST /api/content-representations` (create); `POST /api/segments/{segment_id}/readings/choice`;
`GET /api/segments/document/{doc_id}/text`. Slice 1's `SegmentRead.text` stays as "the box's
own text" for provisional segments and becomes the counting reading's text for real ones.

**ChangeSpec.** `domains=["representation","segment"]`; `segment_ids`, `document_ids`; event
types `representation.created`, `reading.chosen`, `pass.working_chosen`.

**Refusals** (typed, tested): a `legacy:` segment id (`ProvisionalSegmentIdError`); a
`segment_id` whose document differs; an anchor inconsistent with the segment's shape
(`ReadingAnchorMismatch`); a choice made by a caller who is not a person
(`ChoiceNeedsAPerson`); a kind not in the vocabulary (`UnknownReadingKind`, naming the list);
pairing two readings of different segments.

**Tests, by behaviour.**
- `.set` / `.corrections-are-new`: three readings on one segment; adding one changes no other
  row; a correction names its target and the target's text is unchanged.
- `.equal-alternatives`: three human readings of one kind with certainties coexist; the
  counting answer is `none` until one is chosen.
- `.chosen-is-worked-out` / `.chosen-follows-project-rule` / `.machine-is-labelled`: the truth
  table of `resolve_counting` as a pure test; flipping the rule writes nothing.
- `.maker-set-by-engine`: a create through the MCP context is recorded `agent` whatever the
  body says; a params model with `provenance_kind` is refused.
- `.kinds` / `.level-recorded`: an unknown kind is refused with the list; a project-added kind
  round-trips; `level` is stored and never inferred (a reading with no level reads back as
  none, not `as_written`).
- `.written-read-pair`, `.read-from`, `.char-confidence-on-line`, `.stretch-names-its-reading`:
  one test each, including a stretch reported unplaced when its words occur twice.
- `source.point.text-is-derived`: the derived text of a page equals the join of its segments'
  counting readings in order, with spans that point back; leaving furniture out drops a
  running head.
- Audit payloads of every action contain no `content`.
- Old library: opens twice; existing representations read unchanged with every new field
  empty.

**For the maintainer:** nothing new. (Question 8, on words in the audit chain, already covers
the default taken here.)
