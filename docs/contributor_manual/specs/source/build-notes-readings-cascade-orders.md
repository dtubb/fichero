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
later step. Corrected 2026-09-20: slice 6 re-points nothing, it only reports. The lasting
segment id lives in the anchor, `SourceAnchor.segment_id`, one shape for readings, marks,
supports and claims; it is built HERE, under #4932, with `resolve_anchor`; see "Where a
lasting segment reference lives" in the identity and storage notes.)

**Owed by this slice to the text editor (13b), so it is not retrofitted:** once a segment has
readings, `segment.split` and `segment.merge` must say what happens to them, in the SAME
action. Split: each part may name the stretch of the reading it takes (a character offset);
with none given, the reading stays on the kept part and the new parts have none. Merge: the
kept segment's reading becomes the members' readings joined in reading order, as a new
reading whose maker is the person who merged; the members' readings stay on their (soft
deleted) segments and come back with an unmerge. Undo of either puts the readings back
exactly. These are parameters of the existing actions, never new actions.

**What exists.** `ContentRepresentation` (`models/__init__.py`): `id`, `document_id`, `kind`
(a **closed** enum: transcription, normalized_text, translation, transliteration, markdown,
html, svg), `content`, `language`, `script`, `source_anchor`, `parent_representation_id`,
`derived_from_representation_id`, `producer_run_id`, `producer_tool`, `producer_model`,
`review_state` (source, draft, reviewed), `created_at`. `ContentRepresentationRevision`: a
person's revision, with `reviewer: str = "human"` **as a default the caller can leave or set**.
Routes in `api/routes/document/content_representations.py`: list for a document, list
revisions, and one action, `representation.revise`.

**Where readings actually live today (VERIFIED by search on disk, 2026-09-19): in artifacts,
not here.** Nothing in the engine ever *creates* a `ContentRepresentation`: the only code that
touches it is its own route file (list, list revisions, revise), and two files in the app.
Every transcription, translation and cleaned text a workflow makes is an **`Artifact`** row
(`artifact_type`, `content`, `provider`, `model`, `run_id`, `source_artifact_id`, `version`).
So the type exists and is well shaped, and the data is somewhere else. Built naively, this
slice would make a **second store of readings** beside artifacts: the exact fault this whole
programme exists to remove.

**So readings get the same treatment segments got in slices 1 and 6: one read seam, then
writers move one at a time.**

- The readings call below answers from **either** store and the caller cannot tell: real
  `ContentRepresentation` rows, and, for text that still lives in an artifact, a **provisional
  reading** (`id: legacy-reading:<artifact_id>`, `provisional: true`, kind from the artifact's
  type, maker from the artifact's provider and model, `document_id`, no `segment_id` unless
  the page is converted and the artifact's boxes carry character spans, in which case each
  line's stretch of the artifact's text is offered as that line's provisional reading).
  `assert_not_provisional` refuses these ids on every write, as it does `legacy:` ones.
- **Nothing copies artifact text into readings, ever, in bulk.** A person's correction of a
  provisional reading writes one real reading (through `representation.create`, naming the
  artifact it corrects in `derived_from_artifact_id`, a new optional field). Workflow tools
  move to writing readings **tool by tool, in later slices**, each in its own commit, and an
  artifact stays the record of a *run's output*.
- Which of the two is "the transcription" for a page is answered by the one counting function
  below, over both kinds of candidate.

This is put to the maintainer (morning file) only as a fact to know; the approach is the
reversible one, and it is the pattern already accepted for segments.

**A reading IS this record, grown. No second record.**

`ContentRepresentation` gains (all optional, added on open; no data migration):

| Field | Type | Notes |
|---|---|---|
| `segment_id` | str \| None | the segment it reads. `document_id` stays required. Never a `legacy:` id |
| `level` | str \| None | how normalised: shipped defaults `as_written`, `expanded`, `normalised`; open list |
| `read_from_rendition_id` | str \| None | the image it was read from |
| `guideline` | str \| None | the transcription convention it follows |
| `provenance_kind` | `ProvenanceKind` | **engine-set** from how the write arrived; never in a params model (→ #4868, → #4869) |
| `created_by` | str \| None | WHICH person or agent wrote it. **Engine-set from `ctx.actor`**, same name and posture as `Segment.created_by`. Added 2026-09-26 while building: `source.reading.author-and-guideline` requires "its author (person, or model and run)", and this table originally carried only the model-and-run half (`producer_model`, `producer_run_id`). `provenance_kind` says a PERSON read this line; an apparatus in a library two people transcribe in has to say WHICH, and a reading exported to an edition carries its own record or carries nothing |
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
- **Passes are ranked by a rule of their own, and it is the app's existing one** (ruled
  2026-09-03, after a drawn region vanished behind a newer machine run). `resolve_working_pass(
  project_rule, pass_choices, passes_with_makers) -> PassAnswer { pass_id | None, basis }`:
  a live human choice of pass wins; with none, a pass that a person made **or that carries any
  segment a person made** comes first, then a pass made from a file's own text layer, then the
  newest. `passes_with_makers` therefore carries, for each pass, its own maker **and whether
  any of its segments is a person's**: the function never reads a pass's maker alone. This is
  the same ranking the app has (`OCRGeometrySelection`'s one ranking core, app slice A stage
  2), now worked out by the engine, so the app and the engine cannot disagree about which pass
  is shown; when this lands, the app's ranking reads the engine's answer and its own copy goes.
- **Showing a pass says nothing about who made its parts.** A curated pass on top does not make
  its machine-made segments or readings a person's. Each still carries its own
  `provenance_kind`; in a strict project each machine reading is still labelled unchosen until
  a person chooses. `resolve_counting` (readings) and `resolve_working_pass` (passes) are two
  functions for two questions and must not be folded into one.

### Strict, with no choice, when PEOPLE disagree: the answer is `none` — resolved 2026-09-26

**Two sentences above pulled against each other, and this records which one governs.** The
strict bullet says "the newest reading is returned with basis `newest-machine-unchosen` (or
`newest-human`)". The `.equal-alternatives` test says "three human readings of one kind with
certainties coexist; **the counting answer is `none` until one is chosen**". Both cannot hold
when three people have read one line.

Ruled while building slice 8: **in a strict project, when more than one PERSON has recorded a
reading of a kind and nobody has chosen, the counting answer is `none`.** One person's reading,
or machines' readings only, still returns the newest with its basis exactly as the bullet says —
there is no disagreement to record in either of those cases.

Why, in one sentence: **an engine that settles a disagreement between two historians by
timestamp is making an editorial decision**, and recording that two scholars read a line
differently is the thing this model exists to do rather than the thing it is allowed to resolve.
It is also the only reading under which the design pin
`source.reading.chosen-follows-project-rule` — "in a strict project only a person chooses the
reading that counts" — means anything at all.

A **relaxed** project does settle it by date, and a person's still outranks a machine's. That is
the one place the two rules genuinely differ on people's readings, and it is tested both ways.

Recorded in `resolve_counting`'s own docstring as well, so the next reader meets the reasoning
where the code is.

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

### Both halves of a split offer the machine's reading of the box they came from — resolved 2026-09-26

**Stated because it surprises people, not because it is a defect.** A split part inherits its
source box's `metadata["box_index"]` (slice 6, so the parts stay in read order rather than falling
to the end of a converted page). The readings seam finds a provisional reading through that index,
so after splitting one line into two, **both parts offer the machine's whole-line text as a
provisional reading** — the same text, on two half-boxes.

Ruled: **keep it.** It is honest — the machine did say that about the box each part came from — it
is labelled `provisional: true` and machine-made, and the derived page text still prefers a
person's reading over it. Suppressing it would be worse in two ways: it would hide the only
reading that exists for that region, and it would have the engine decide that a machine's guess no
longer applies to a piece of the box it was made about, which is another editorial decision the
engine is not entitled to make (see the strict-project ruling above — the same principle).

**Owed to slice 13b, the text editor.** 13b is where a person actually SEES this, and a scholar
looking at the same full-line text on two half-boxes will reasonably wonder whether something
duplicated. The editor's author needs to know that **a reading's scope can be wider than the
segment showing it**, and to say so in the surface, rather than learning it from a confused user.

Pinned by `tests/unit/api/test_readings_across_split_and_merge.py`, whose `_real_contents` helper
documents the distinction it filters on.

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
- `source.pass.working` / `.working-follows-project-rule`: the truth table of
  `resolve_working_pass`, including **a machine pass carrying one human segment outranking a
  newer machine pass** (the 2026-09-03 case), a text-layer pass outranking a newer machine
  pass, and a human choice outranking both; and, on that winning mixed pass, a machine reading
  still reported as a machine's and unchosen in a strict project.
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

## Slice 8b — converting a whole project (#4924 until it has its own issue). After slice 8; nothing reaches the app until the programme is done.

Ruled 2026-09-20. Rules in `segments-and-geometry.md` ("Converting a whole project: the rules").
**Pins:** `source.convert.starts-when-a-project-opens`, `.only-the-running-engine`,
`.snapshot-first-and-proved`, `.refused-when-disk-is-short`, `.the-machine-stays-usable`,
`.a-page-is-all-or-nothing`, `.stops-starts-and-repeats-safely`, `.half-done-reads-the-same`,
`.report`, `.words-move-with-the-boxes`; and `source.store.never-converted-by-a-migration`.

**What exists to build on (VERIFIED on disk 2026-09-20; use these, do not write second ones).**
- The page action: `segment.convert_and_edit` with no `edit` (slice 6). One document, one
  transaction, all of the page's results or none, repeatable ids, a real second guard, typed
  refusals. With no edit it has no inverse, which is right here.
- Snapshots: `db/storage_snapshots.py`: `snapshot_library(...)`,
  `auto_snapshot_before_risky_operation(...)`, `restore_snapshot(...)`, and a retention rule
  (`max_snapshots`, `_enforce_retention`) **that would delete the pre-conversion snapshot if
  nothing stops it.**
- Background priority: `core/background_compute.py::set_background_qos()`.
- One seam for every reader: `GET /api/segments/document/{doc_id}` and `live_geometry`.

### Snapshot pinning already exists — corrected 2026-09-26

**The notes above say the retention rule "would delete the pre-conversion snapshot if nothing
stops it", which reads as "a pin has to be built". It does not.** `LibrarySnapshot.is_pinned`
exists, and `_enforce_retention` skips a pinned snapshot in BOTH of its passes — the expiry pass
and the keep-the-last-N pass. Verified on disk 2026-09-26.

So the runner **sets the flag that is already honoured** and adds no second mechanism. A spec
that tells a builder to write what already exists is how second paths start, which is the fault
this whole programme exists to remove.

There is no `pin_snapshot()` helper: the flag lives on the record and `_save_snapshot_record`
persists it. Written through that rather than a new helper, because one caller does not earn an
API.

Pinning is also **best-effort on purpose**. A snapshot that is proved but not pinned is still a
way back; refusing a conversion because a bookkeeping flag could not be written would be
refusing over the wrong thing. The report carries the snapshot id either way, so the way back
stays findable even if retention later tidies the record.

### Where the report lives: its own table — ruled 2026-09-26

The notes leave this as "the build lane's first question; one home, not both". **It is
`ConversionRun`, table `conversionruns`, in the LIBRARY's own database.** The activity record is
the wrong home, for four reasons checked on disk rather than assumed:

1. **Activities are deleted by age** (`ActivityStore.delete_old`). The rule says the report is
   "shown once, **kept**"; a record that must persist does not belong in a store built to be
   pruned.
2. **Activities live in a different database file.** This report is the account of what happened
   to THIS library's data and names a snapshot of it, so it has to travel with the library. Move
   the package to another machine and an activity log left behind takes the only record with it.
3. **The report has mutable state; activities are append-only events.** `seen_at` gates
   un-pinning the snapshot — the snapshot is exempt from retention until the run has finished
   AND a person has seen the report — and that is a field that changes after the fact.
4. **It must be queryable by its parts.** "Which projects refused for disk, and how much did
   they need" is a column query in its own table and a JSON scan in an activity payload.

**The runner: one function, `convert_project(db, library_path)`, started by the engine after
the project has opened.** Not at open, not in a migration, not from the CLI.
1. **Anything to do?** Count unconverted results with boxes (one query). None: write nothing,
   not even a report. This is what makes every later open free.
2. **Disk.** `shutil.disk_usage` against the snapshot's likely size (the last snapshot's size,
   or the project file's) plus the new records, times a stated margin. Short: record
   `refused_disk` with the numbers in the report, stop, try again at the next open.
3. **Snapshot**, `initiator="system"`, a reason that names the conversion, and **pinned**: a
   snapshot the conversion depends on is exempt from retention until the run is finished and
   the report has been seen. Then **prove it**: read it back (open its exported tables) and
   compare row counts, table by table, with the project's. A mismatch is `refused_snapshot`.
4. **Pages**, oldest first, at background priority: for each document with an unconverted
   result, invoke the page action as the system actor with the run's id as `run_id`. After
   each page: yield, and stop at once if the engine is shutting down or a person's request is
   waiting (measure that it does; see tests). `AlreadyConverted` and `NothingToConvert` are
   not failures (an edit got there first). Any other refusal or error: record document, result
   and reason, carry on.
5. **Report**, one kept record for each run: started, finished, snapshot id and place, pages
   converted, pages skipped with reasons, pages failed with reasons, seconds. The app shows it
   once. Where the record lives (its own small table, or the existing activity record) is the
   build lane's first question; one home, not both.

**Progress is the markers, not a counter.** "What is left" is always "results with boxes and no
marker", asked of the database. A quit, a crash or a second run cannot make it wrong. Do not
store a cursor.

**One audit row for each page**, by the system actor, counts and ids only (slice 6 already
holds it under 10 kB). A project of 20,000 pages adds 20,000 small rows to the record; say so
in the report, and measure the chain check afterwards.

**With readings on segments (why 8 comes first).** The page action gains one step: each
converted segment's words become a reading on that segment, maker and all, from the same
`segments_from_result` answer; the pass's whole text becomes the pass's reading. From then
the block is no longer the only home of the words, `ArtifactHoldsTheOnlyWords` has nothing
left to protect and goes, and `live_geometry`'s text fill reads from readings. The master test
still holds: before equals after, but for ids.

**New results after conversion.** Until the tools write segment records themselves, a result
saved with boxes is converted by the page action as soon as it is saved (default taken; in the
questions file). `vision_base`'s in-place update of a converted result must make a NEW result,
not fail the run (slice 6 step 5 review).

**Multi-user and a remote engine.** The engine converts, whoever connects, once: a project has
one engine, so one runner; guard it with a lock in the project's own database so two openings
cannot start two. It acts as the system actor; people's permissions are untouched, and
conversion changes nothing a reader sees, so nobody is shown anything new.

**Tests** (temporary projects only, built the way `tests/conftest.py` builds one).
- The master test, for a whole project: every page's seam answer before equals after, but for
  ids; and **at every point in between** (convert half, compare all; convert the rest, compare
  all). Same for `GET /api/artifacts/{id}`, the artifact lists, search, a claim's reveal, an
  export.
- Stop after page *n* (kill the runner), start again: the final state equals an uninterrupted
  run's, row for row and id for id; run a third time: zero writes, no report.
- A page made to fail (a result whose boxes cannot convert): it is in the report, it still
  reads from its block, every other page converted.
- An edit during the run, on a page not yet reached and on one already done: both land, same
  ids as an untouched run gives.
- Snapshot missing, snapshot unreadable, snapshot with a wrong count: nothing converts. The
  pinned snapshot survives `max_snapshots` worth of later snapshots.
- Disk short (patched `disk_usage`): nothing converts, the report has the numbers, the next
  open tries again.
- Opening is not delayed: the open call returns before the runner's first page (assert on
  order, and measure the open).
- Usable machine: with the runner busy on a large temporary project, a person's read and a
  person's edit each finish within a stated bound. A measured number, not a comment.
- A migration-shaped guard: the guardrail from slice 6 still fails on a fixture migration that
  writes segments; and a test that the CLI has no command that converts a project file itself.
- Restore: restore the pinned snapshot into a temporary place and show the project reads as it
  did before the run. Never exercised on a real project.

## Slice 9 — the cascade: language, script and direction, with where each came from (#4938)

**Pins:** `source.lang.cascade`, `.says-where-from`, `.reading-overrides`, `.three-facts`,
`.registries`, `.project-declared`, `.unknown-is-not-unexamined`, `.many-per-page`;
`source.dir.per-segment`, `.logical-order-stored`; the engine half of
`source.resolve.one-cascade`. (`source.dir.reader-lays-out` is app work, after the editor.)

**What exists.** `llm/language_policy.py` resolves **one document's language**:
`resolve_language(requested=, document=, text=, policy=, detect=) -> LanguageResolution
{language, status, source, basis}`, with a stated precedence (a language pinned on the
workflow node; then a language a person set on the document; then the app-wide policy: `one`,
`many`, `document`, or `unset`, the last keeping an English fallback "so existing libraries do
not shift"). `Document.language` and `language_meta` keep known / unknown / never-determined
apart. The policy is **one app-wide setting** (`configured_policy()`). `LibrarySetting {id,
value}` is a key-value record in a library's own database, with one use today. Script lives
only on a reading. Direction lives nowhere.

**The design: extend that resolver; do not write a second one.**

- **Where a value can be set** (the one list): app, project, folder, document, page, region,
  line, word, character. App stays where it is (the policy). **Project** values are
  `LibrarySetting` rows (keys `source.language`, `source.script`, `source.direction`,
  `source.record_rule`; the value a small JSON string). **Folder, document and page** are
  nodes: a new optional JSON field on `Document`, `source_settings: dict | None`, added on
  open, holding any of `language`, `script`, `direction` with `set_by` and `set_at`.
  `Document.language` and `language_meta` stay exactly as they are and keep their meaning (a
  document's *own determined* language); they are read as the document level's language when
  `source_settings` has none. **Region to character** are segments: three optional fields on
  `Segment`, `language`, `script`, `direction`, plus `settings_set_by` and `settings_set_at`.
- **One function:** `resolve_setting(db, *, key, segment_id=None, document_id=None,
  requested=None) -> SettingResolution { value, status, level, level_id, basis }`, in
  `llm/language_policy.py` beside `resolve_language`. It walks **up**: the segment, its parent
  segments, the page, the document, each folder above it, the project, the app. The first
  level that says something wins. `level` and `level_id` are what "says where from" shows.
  For `key="language"`, the document-and-above part **is** today's `resolve_language`, called,
  not copied, so its precedence, its refusal to guess, and its `unset` behaviour for existing
  libraries are untouched.
- **Three facts.** `language` is a BCP 47 tag; beside it an optional `glottocode` (a second
  field on the same value, not a second registry). `script` is an ISO 15924 code, the honest
  ones included (`Zxxx`, `Zyyy`, `Zzzz`, and `Qaaa` to `Qabx` for a script a project declares).
  `encoding` is `full` | `part` | `none` | unknown, worked out where it can be from
  `llm/script_coverage.py`'s exemplar sets and otherwise set by a person; it is **not** stored
  on every segment: it is a property of a *script in a project*, kept in one project record
  (`LibrarySetting` key `source.scripts`, a list of `{script, name, encoding, declared: bool}`),
  which is also where a project declares a script no registry has.
- **Direction** is one of `ltr`, `rtl`, `ttb`, `btt`, `alternating`, `follows-baseline`, plus,
  for a region, `line_progression` (the way its lines or columns succeed each other). With
  nothing set anywhere, direction is worked out from the resolved script (a small table:
  `Arab`, `Hebr`, `Syrc` and kin give `rtl`; `Hani`, `Hira`, `Kana`, `Hang`, `Mong` say
  "may be vertical" and resolve to `ltr` unless a level says otherwise) and the answer's
  `level` is `derived-from-script`, so it is never mistaken for something a person set.
- **Stored text stays in reading order.** Nothing in this slice reorders a string; the rule is
  pinned by a test on a mixed right-to-left and left-to-right reading.
- **A reading's own language and script win for that reading** (`ContentRepresentation.language`
  and `.script`, which exist).
- **The same walk answers for models and guidelines** (`key="model:<job>"`, `key="guideline"`):
  the walk is general; the keys are registered when the models and projects work arrives.
  Today's app-wide role defaults are read as the app level. No second resolver is written then.

**Actions.** `source_setting.set` and `source_setting.clear`: params `level` (`project` |
`node` | `segment`), `target_id` (none for project), `key`, `value`; they record `before:
{value}` and `after: {value}` (a setting is not a researcher's words); each is the other's
inverse. Setting a node's `language` through this action also calls today's
`set_user_language`, so the two never disagree.

**Routes.** `GET /api/source-settings/resolve?key=&segment_id=&document_id=` (the answer with
its level); `PUT /api/source-settings`; the seam's `SegmentRead` gains `language`, `script`,
`direction` as **set on the segment** (not resolved: resolving every segment of a page in a
list call would be a walk for each row; the app asks for the resolved value of the selection).

**ChangeSpec.** `domains=["source_setting","segment"|"document"]`; `segment_ids` or
`document_ids`; event type `source_setting.changed`.

**Migration and old libraries.** New optional columns only. A library made before this slice
resolves exactly as it did: a test runs `resolve_language` and `resolve_setting(key=
"language")` over the same fixture documents and asserts equal answers, for each of the four
policy modes.

**Refusals** (typed, tested): a tag that is not well-formed BCP 47 (`BadLanguageTag`); a script
code neither in ISO 15924 nor declared by the project (`UnknownScript`, naming how to declare
one); a direction outside the list; setting a value on a `legacy:` segment.

**Tests, by behaviour.**
- `.cascade` / `.says-where-from`: a Basque gloss inside a Latin page inside a Spanish folder
  inside a project set to `es`: the gloss resolves `eu` at level segment, a sibling line
  resolves `la` at level page, a line on another page resolves `es` at level folder; clearing
  the page value makes the sibling resolve from the folder.
- `.unknown-is-not-unexamined`: never-determined, unknown and known stay three answers through
  the walk.
- `.reading-overrides`: a translation's language is its own, whatever the segment resolves to.
- `.project-declared`: a declared script resolves and an undeclared private code is refused.
- `.many-per-page`: one page with three scripts resolves each segment to its own.
- `source.dir.per-segment`: `rtl` on a region is inherited by its lines; `alternating` set on a
  region is reported for each line; with nothing set, `Arab` gives `rtl` at level
  `derived-from-script`.
- `source.dir.logical-order-stored`: a reading with Arabic and digits is stored and returned
  byte for byte in reading order.
- Equal answers with `resolve_language` on an old library, in all four policy modes.

**For the maintainer:** nothing. (That a folder can carry settings, set in the Inspector, was
ruled on 2026-09-19.)

### A project declares scripts, not languages — resolved 2026-09-26

`source.lang.project-declared` says "a language **or** script no registry has". Built, the two
halves came out different shapes, and the asymmetry is the honest one rather than an unfinished
half.

A **script** is stored as a code (`Segment.script`, `Document.script`,
`ContentRepresentation.script`), so a project-declared script needs somewhere to record what its
code means: nothing in the world can resolve `Qaaa`. That store is `LibraryScript` (table
`libraryscripts`: `code`, `name`, `encoding`, `declared`), and `assert_known_script` refuses a
private-use code the library has not declared, on writes only — the reading-kinds rule, so a
project that tidies its declarations never loses stored text.

A **language** needs no store, because `Document.language` holds a canonical **name** (#2092),
not a tag. A project working in an unregistered language already writes that name and the
cascade carries it; the declaration and the value are the same string, and a `LibraryLanguage`
table would be a second place holding one fact. What the language half gets instead is a
predicate, `language_is_project_declared`, for BCP 47's own private-use range (`qaa`–`qtz`, and
any `x-` subtag), so a value can be shown as the project's own. A test pins the absence of the
table so a later change of mind has to be argued rather than drifted into.

Three departures from the plan above, each deliberate:

- **A table, where this document said a `LibrarySetting` row holding a JSON list under key
  `source.scripts`.** Same information; the table is typed, queryable, and migrated by the
  mechanism every other model already uses, where the k/v row needs a serialiser, a
  deserialiser and a hand-written migration for a shape that is already a model. It follows
  `LibraryReadingKind`, which slice 8 set as the pattern for a per-library vocabulary.
- **`UnknownScript` refuses two things, not "a code neither in ISO 15924 nor declared".**
  Fichero ships no copy of ISO 15924, so the engine cannot tell `Latn` from `Lxtn` offline. It
  refuses a malformed code and an undeclared private-use code, and passes a well-formed one it
  cannot confirm. Refusing everything unconfirmable would refuse real scripts; a short
  hand-kept list would look authoritative while being wrong. The refusal that carries the
  behavior is the private-use one.
- **`encoding` is stored and never computed.** The field carries the spec's three values
  (`full` | `part` | `none`) with `None` for not established. Whether Fichero *works out* an
  encoding from `llm/script_coverage.py` is the open question on the encoding item; nothing
  here presumes an answer, and it can be filled later without changing the record.

Also found, and **not** patched here: `source.lang.registries` asks that "language holds a BCP 47
tag", and at document level it cannot — the field is a name by design. The tag lives only on
`LanguageSpec` (the model-coverage lookup), so no document, segment or reading can state one.
That needs its own decision (a second field, a migration of names to tags, or recording the
clause as unmet) and is reported, not quietly worked around.

### The write path: `segment.update` grew, and clearing is its own action — resolved 2026-09-26

Found while building item 7: `Segment.language` and `.script` were fields **no action could set**,
so `many-per-page` could not be true end to end however faithfully the read seam carried them — a
page comes back as three answers only if something can record three.

- **The writer is `segment.update`, not a new action.** It already owns the version snapshot, the
  stale check, the inverse and the audit row; a second writer for the same row would be a second
  place to keep all four correct. `language`, `script` and `direction` are parameters on it; the
  metas are NOT parameters, because provenance is engine-set from `ctx` (#4868/#4869) and a caller
  that could send one could claim a person set what a model guessed.
- **Extending the writer exposed a defect that would have shipped.** `SegmentVersion` is the
  preimage undo restores from, and it did not carry the three facts — so a restore would have left
  a language change at its new value and lost a fact it never touched. A field the update can
  change and the preimage cannot carry is worse than a field nobody can edit. The three facts,
  their metas and `line_progression` are now snapshotted and restored.
- **Clearing is `segment.facts_clear`, a separate action.** Every optional field on
  `segment.update` means "not given", and overloading one to also mean "set this to nothing" would
  make two different instructions indistinguishable to a reader. Clearing is also the rarer,
  more deliberate act — a curator withdrawing a statement rather than correcting it — and it earns
  its own audit row. It names the facts to clear explicitly, because clearing a language while
  meaning to clear a direction is a loss nothing warns about, and it clears each fact's meta with
  it: provenance for a fact that no longer exists would say a person determined something that is
  not there.
- **Clearing is the write side of `unknown-is-not-unexamined`.** A cleared fact FALLS THROUGH to
  the next level; an examined-and-undetermined one STOPS the walk. The two are written by
  different actions and a test asserts the difference by resolving after each.

Both refusals reach a caller as 422 through the one `_as_http_error` mapping rather than at their
call sites, so there stays one place that maps a refusal to a status code.

### The single entry point did not survive contact — ruled 2026-09-26 (option A)

This document designed ONE setter for every level, `source_setting.set` with a `level` parameter.
Built, it came out as two, and the reason is a constraint the notes did not know about.

By the time the setter was written, `segment.update` already owned a segment's version snapshot,
its stale check, its inverse and its audit row, and the three facts had gone in as ordinary
columns beside the segment's others. Routing a segment's language through `source_setting.set`
would have made `segment.update` **the only segment action that cannot change some of the
segment's own columns**. That is not untidiness: it is an oddity whose correctness depends on
nobody noticing it, and a later reader "fixing" it is the failure mode. So:

- **`segment.update`** sets a segment's language, script and direction; **`segment.facts_clear`**
  withdraws them.
- **`source_setting.set` / `.clear`** own the **project** level (`LibrarySetting` rows under
  `source.<key>`) and the **node** level (a `Document`'s own columns), and refuse
  `level="segment"` with a typed refusal that NAMES `segment.update` — a refusal saying only "not
  supported here" sends the reader hunting for something one call away.
- The asymmetry is documented at **both** ends, because one-ended documentation is how the "fix"
  happens: the reader meets the odd side first.

"One code path per thing" is satisfied either way — there is exactly one way to set a segment's
language under both designs — so the rule does not choose between them, and the tiebreak is which
one a stranger reads correctly.

**The node level is a `Document`'s own columns, not a `source_settings` JSON bag** as this document
sketched. A bag holding `language` beside the existing `language` column would be two homes for
one fact about one document, which is the duplication the programme removes. `Document.direction`
and `direction_meta` were added so the node level carries the same three facts, in the same shape,
as a segment does.

**The invariants are identical at every level**, which is the point of ruling rather than
drifting: provenance engine-set from `ctx` and never accepted from a caller, `assert_known_script`
and `assert_known_direction` called on the way in, and clearing meaning NEVER DETERMINED rather
than `unknown` (a positive finding that somebody looked). A validated segment path beside an
unvalidated project path is the sibling-defect shape, and there are tests asserting the project
and node levels refuse exactly what the segment level refuses.

**One read answers all of it**: `GET /api/source-settings/resolve?document_id=&segment_id=` returns
language, script, direction and encoding, each with the rung that answered — for ONE selection,
never for a list, because resolving every segment of a page would be one walk per row. That is why
the seam carries what is SET and this answers what is RESOLVED.

### Direction is the third fact, and the one place the cascade derives — resolved 2026-09-26

`source.dir.per-segment` and `source.dir.logical-order-stored`, engine half. Direction walks the
same rungs as language and script, through the same `_stated_fact` reader (`resolve_direction`
beside `resolve_script`), so there is one cascade and not three. Three decisions worth writing
down:

- **The derivation is a SOURCE, and `level` stays four pure rungs** — ruled 2026-09-26 after it
  was first built, wrongly, as a fifth level. With nothing set anywhere the answer is worked out
  from the resolved script and reported as `source="derived-from-script"` with `level=None`, which
  is the accurate reading of the rule that `None` means NOT STATED: no rung stated it, because
  nobody did. A `level` that sometimes holds a non-rung cannot be reasoned about, and it is the
  same conflation refused when `source` was proposed as the home for the rung. The distinction a
  reader needs — a direction worked out versus one a person chose — is carried by `source`, the
  field a caller already inspects to decide whether to trust a value, and a test asserts the two
  are distinguishable for the same value (`rtl` derived from `Arab` versus `rtl` set on the
  region).
- **Deriving at all is justified, and this is why it is not the `Zyyy` mistake**: a direction has
  to be decided either way, because the text gets drawn on a screen, while a script is a claim
  about the source that nobody is forced to make. The same reasoning is recorded at the
  derivation itself, not only here.
- **"May be vertical" is not a direction.** `Hani`, `Hira`, `Kana`, `Hang`, `Mong` and kin
  resolve `ltr` like anything else — modern horizontal Japanese is the common case and guessing
  `ttb` would be wrong more often than right — but the set is named (`script_may_be_vertical`)
  so a surface can ask about exactly those.
- **`line_progression` is a separate field, region-only, and not at the seam.** Vertical
  Japanese is `ttb` text whose columns progress `rtl`; a right-to-left line in a European book
  still progresses `ttb`. One field could not say both. It is absent from `SegmentRead` because
  no surface reads it yet, and a field the app never asks for is a field nobody keeps correct.

`direction_meta` rather than the `settings_set_by` / `settings_set_at` pair this document
sketched, for the same reason the language level was folded into `language_meta`: one shape for
one idea, already built, already read by four levels.

## Slice 10 — named reading orders, flows, and the one typed-link record (#4930, #4931)

**Pins:** `source.order.named-multiple`, `source.order.next-previous`, `source.segment.flow`;
`source.link.typed`, `source.link.any-depth`, `source.link.both-ways`. (`source.canvas.*` is app
work and waits for the canvas's own spec, → #3085.)

### Reading orders

**What exists — corrected 2026-09-26 (#4930).** No stored order, and **TWO ordering rules, which
order different things.** This section previously cited `_reading_order` in
`api/routes/document/artifacts.py`; there is no such function anywhere in the engine, and the
description that followed it was right about one of the two:

**THREE ordering rules, and the third is the one `as-written` must use.** They agree wherever
`box_index` exists and diverge exactly where slice 10 is exercised.

| Rule | Orders | Key | Tie-break with no `box_index` |
|---|---|---|---|
| `reading_order(pairs)` (`media/ocr_geometry.py`) | boxes | char span when every member has one, else top-then-left | — |
| `_segment_row_sort_key(row)` (`routes/document/segments.py`) | rows, for the app's index mapping | `box_index` | `(created_at, id)` — **creation order** |
| `_segment_order_key(row)` (`routes/document/segment_readings.py`) | rows, for derived text | `box_index` | `(bbox_y, bbox_x, id)` — **page order** |

`reading_order` lives beside `union_bbox` because the old store's combine and the new store's
joined text both need it, and "a second copy of this rule is how two combines would start
disagreeing about word order" (#4924). `_segment_row_sort_key` never falls back to the bare `id`,
"a random uuid the app's index mapping cannot use" (#4921 review); `live_rows_in_order` imports it
rather than copying it. In all three, `id` is only ever the LAST resort that makes the sort total,
never a meaningful position.

**RULED 2026-09-26: `as-written` is PAGE order, so slice 10 imports `_segment_order_key`.** The
argument is in the name. *As written* means the order the source was written in — down the page and
across the line. A line a person drew last but positioned third **was written third**, and an order
that put it last would report the order of the editing session, not the order of the source: a
claim about a scholar's working habits dressed as a claim about a manuscript. Creation order is
right where it is used — the app's index mapping must hand rows back in the order the app sent
them, or the indices mean nothing — and that is a different question from what the page says. **Two
row orderings that disagree on purpose is correct here; what was missing was anyone writing down
why.**

After slice 6 a converted segment remembers its old place as `metadata.box_index`, which all three
rules read first, which is why they agree on a converted page.

**One of the three had a defect, found 2026-09-26 while enumerating them for this slice.**
`_segment_order_key` sorted `(box_index, bbox_y, id)` with no `bbox_x`: two segments on one line
share a `bbox_y`, and a hand-drawn word has no `box_index`, so **the words of a hand-segmented line
came out of the derived text in uuid order** — precisely the paleography case, where a scholar
segments words by hand. Fixed in `a79b901d8`; never released (the commit that introduced it is not
in `v2026.09.20` or `main`). The lesson for slice 10: `reading_order` was cited in a comment beside
that key and a nearly identical rule was written from memory anyway, so **import the rule or say in
a comment why you cannot**.

**Models.** `ReadingOrder` (table `readingorders`): `id`; `document_id`; `pass_id` (an order
belongs to one pass); `name` (`as-written` is made with every pass; others are free);
`kind: str` (`as-written` | `imposed` | `commentary` | `flow` | project terms);
`provenance_kind` (engine-set); `created_by`; `certainty: float | None`; `created_at`;
`deleted_at`. `ReadingOrderEntry` (table `readingorderentrys`): `id`; `order_id`; `segment_id`;
`position: float`; `parent_entry_id: str | None` (orders nest: regions in order, lines in order
inside each); `version: int`.

**Positions are fractions.** Putting an entry between two others writes **one** row (the
midpoint). When two neighbours come closer than 1e-9, the action refuses with
`OrderNeedsRenumbering`, and a separate, rare, audited `reading_order.renumber` rewrites that
order's positions as 1.0, 2.0, 3.0 (the only action that touches many rows of one order, and
never more than one order). The app never renumbers.

**The `as-written` order** is made by `segment.pass_create` and by conversion: entries in
`metadata.box_index` order for converted boxes (which already carries today's sort), else in
creation order. It is a machine's order (`provenance_kind` from the pass) until a person
edits it.

**A flow** is a `ReadingOrder` of kind `flow` whose entries may be segments of **different
pages of one document group** (`document_id` is then the group's node id, and each entry's
segment names its own page). That is the one place an order crosses pages.

**Indexes:** `readingorders(document_id)`, `readingorders(pass_id)`,
`readingorderentrys(order_id)`, `readingorderentrys(segment_id)`, declared in
`db/migrations/schema.py`'s `(name, SQL, reason)` list beside slice 8's, each with its reason
stated — that list is the one place indexes are declared and the guardrail reads it.

**Grounded 2026-09-26: the `neighbours` read needs a FIFTH index, `(order_id, position)`.** With the
four above, answering "what is before and after this segment in this order" means reading the
order's entries and picking the neighbours in memory: bounded by the ORDER's size, which is fine for
a fifty-line page and is not fine for a flow across a codex, where one order can hold thousands of
entries. The bounded form is two indexed lookups — `ORDER BY position LIMIT 1` either side of the
segment's own position — and that wants a composite `(order_id, position)`. It also wants a typed
persistence method rather than SQL in the route (#1876: raw SQL only behind a typed method in the
persistence layer), which is where `source.store.bounded-reads` and the architecture rule meet.

**Actions.** `reading_order.create` (`document_id`, `pass_id`, `name`, `kind`);
`reading_order.place` (`order_id`, `segment_id`, `after_entry_id | None`, `parent_entry_id?`,
`expected_version?`): records `before: {entry_id, position, parent_entry_id} | null`, `after:
{entry_id, position}`; inverse places it back or removes it; `reading_order.remove`;
`reading_order.renumber`; `reading_order.delete` (soft). Ids and numbers only in the audit.

**Reads.** `GET /api/reading-orders/document/{doc_id}` (orders, no entries);
`GET /api/reading-orders/{order_id}/entries?parent_entry_id=` (bounded: one level at a time);
`GET /api/reading-orders/{order_id}/neighbours?segment_id=` →
`{previous_segment_id, next_segment_id}`, **always of a named order**; there is no "next
segment" call without one. The derived page text of slice 8 takes its order from here.

**Refusals** (typed, tested): an entry for a segment of another pass (`OrderPassMismatch`),
except in a `flow`; a segment placed twice in one order (`AlreadyInOrder`); `neighbours` with
no order named (422); `OrderNeedsRenumbering`; a `legacy:` id.

**Tests, by behaviour.**
- `source.order.named-multiple`: one page, its `as-written` order and an `imposed` order over
  the same word segments in a different sequence; both read back; deleting one leaves the
  other.
- `source.order.next-previous`: neighbours differ between the two orders for the same word;
  the call without an order is refused.
- `source.segment.flow`: a flow over the last lines of page 1 and the first of page 2 yields
  derived text that reads straight through, furniture left out.
- Moving one entry writes one row (count the rows whose `version` changed); a forced
  renumber is its own audit row.
- **Two tests, not one** (corrected 2026-09-26): a converted page's `as-written` order equals
  **`_segment_order_key`** over that pass's live rows — page order, per the ruling above, not
  `live_rows_in_order`, which is the app's index mapping and answers a different question — and an
  unconverted page's `as-written` order equals `reading_order` over the artifact's boxes. The
  earlier single test paired the row order against the box sorter, which is the wrong pairing for
  the case it named, and it cited a function that does not exist, so written literally it could not
  import.
- **The ordering rule is IMPORTED, never re-implemented.** `ReadingOrderEntry.position` is a float
  placed by midpoint, so the fallback when positions tie or are absent decides the order — in a
  record with no `box_index` of its own. The lazy fallback is `id`, which is exactly what #4921
  forbids. A test asserts the `as-written` order of segments created in one transaction (identical
  `created_at`, unordered uuids) is stable and is NOT uuid order. If neither existing rule fits a
  case, that is a finding to report, not a licence to write a third.

### One typed-link record

**What exists (four link records, four vocabularies) — verified against the code 2026-09-26
(#4930): this list is ACCURATE.** All four exist as written, `PredictionLink` included and
correctly described as a value inside a prediction's metadata rather than a table.

Two records the list does NOT name, and deliberately: `KnowledgeClaimLink` and `LibraryItemLink`
are the KG's own links, and `LibraryItemLink` already reuses `KnowledgeClaimLink`'s typed
`ClaimRelationType` ("KG relations and library links share one relation ontology"). They are
outside this slice — worth knowing when the vocabulary below is chosen, because **a fifth
vocabulary beside an existing shared one would be the drift this consolidation exists to remove.**

`NoteLink` (`models/knowledge.py`:
`source_note_id`, `target_note_id`, `link_type` follows | references | contradicts | supports |
free, `annotation`); `SpatialConnection` (`models/canvas.py`: `room_id`, `source_node_id`,
`target_node_id`, `connection_type`, `link_subtype`, `created_by`, `metadata`); `CanvasItem` of
kind link (`source_item_id`, `target_item_id`); and `PredictionLink` (a value inside a
prediction's metadata: `target_claim_id`, `link_type` next_logical | supports | contradicts |
refines).

**This slice makes the one record and puts segments on it. It does not move the other four.**

`TypedLink` (table `typedlinks`): `id`; `from_kind`, `from_id`; `to_kind`, `to_id` (kinds:
`segment`, and later `note`, `document`, `claim`, `canvas_item`); `link_type: str` (from the
vocabulary below); `directed: bool`; `provenance_kind` (engine-set); `created_by`;
`certainty: float | None`; `note: str | None` (a short reason, not source text); `created_at`;
`deleted_at`. Indexes on `(from_id)` and `(to_id)`, which is what makes a link reachable from
either end.

**Vocabulary:** table `librarylinktypes` (`key`, `label`, `inverse_label`, `builtin`), seeded on
open with the design's list (glosses, comments-on, answers, quotes, expands, reorders, marks,
captions, labels, continues, translates, same-as, names) **and** the existing four records'
words (follows, references, contradicts, supports, free, next_logical, refines,
derived_from, interprets), so that when the other records converge no word is lost. A project
can add keys.

**Grounded 2026-09-26 (#4930/#4931): that seed list COLLIDES with the KG's own vocabulary, and one
collision is a near-miss spelling.** `ClaimRelationType` — already shared by `KnowledgeClaimLink`
and `LibraryItemLink` — holds `caused_by`, `cites`, `contradicts`, `corroborates`, `derives_from`,
`duplicate_of`, `follows`, `refines`, `related_to`, `supports`. Against the seed list above:

- **Four exact duplicates**: `follows`, `refines`, `supports`, `contradicts`. Seeding them as new
  keys would give one library two keys per idea, one of which the KG already uses.
- **One spelling collision, which is the dangerous kind**: the seed list's `derived_from` versus
  `ClaimRelationType.derives_from`. Two keys, one relation, differing by a single letter — nothing
  would ever report them as the same thing, and a query for one would silently miss the other.
- **One near-synonym to rule on rather than seed blind**: `references` (from `NoteLink`) beside
  `cites` (from the KG). They may be the same relation under two names, or a deliberate distinction;
  either is fine, but not by accident.
- **Genuinely new and worth having**: the manuscript-facing words the KG has no equivalent for —
  glosses, comments-on, answers, quotes, expands, reorders, marks, captions, labels, continues,
  translates, same-as, names — plus `interprets` from `SpatialConnection`.

**THE RULE, not just this instance: a vocabulary is seeded from every set that already holds the
idea, with the overlap collapsed to one key each — never as a second list beside an existing one.**
Where a plan and stored data disagree about a SPELLING, the stored data wins: changing stored data
means a migration, changing a plan means editing a line. So the four duplicates take
`ClaimRelationType`'s spelling, and `derived_from` becomes `derives_from`.

Otherwise the record built to remove four vocabularies ships a fifth that disagrees with the one two
records already share — the drift this consolidation exists to remove, reintroduced by its own seed.
That is the same shape as a third sort key beside two existing ones and a second copy of a
provenance rule beside its own docstring: **before adding any list, set or key, ask what already
holds that idea.**

**A guard, because a list nobody re-checks drifts the first time someone adds a word:** a test
asserting that no pair across the seeded keys and `ClaimRelationType`'s values differs only by
inflection or underscore. `derives_from`/`derived_from` is the near-miss that test exists for —
two keys, one relation, one letter apart, where a query for one silently misses the other and looks
like an answer.

**Convergence is routed, not done here** (each is its own later slice, with its own tests and
its owner's spec): notes (`NoteLink` rows read through a view of `TypedLink`, then written
there); the canvas (`ui/library-view-modes.md`, → #3085: a connector is a `TypedLink` plus a
position); predictions (the metadata value stays a value; its `link_type` words are already in
the vocabulary). Until then the four keep working untouched, and **no new code may add a fifth
link record**: a guardrail greps models for a new class with `source_*_id` and `target_*_id`
fields outside the allowlist.

**Actions.** `link.create` (`from_kind`, `from_id`, `to_kind`, `to_id`, `link_type`,
`directed?`, `certainty?`, `note?`); `link.delete` (soft); `link.restore`. Inverses of each
other. Audit: ids, kinds, type.

**Reads.** `GET /api/links?kind=segment&id=<segment_id>&direction=out|in|both&depth=1`
(`depth` up to 8; a walk with a visited set, so a ring of links ends; past 8 it **says** it
stopped, with `truncated: true` and the frontier ids, which is honest for a browse call and
different from forwarding, where stopping short would be wrong).

**ChangeSpec.** `domains=["link","segment"]`; `segment_ids` = both ends when they are segments;
event types `link.created`, `link.deleted`.

**Refusals** (typed, tested): an unknown `link_type` (`UnknownLinkType`, naming the list); a
link from a thing to itself; an end that does not exist or is a `legacy:` id; a segment end
that has been forwarded (the action resolves it through `resolve_segment` and links the live
segment, saying so in its result).

**Tests, by behaviour.**
- `source.link.typed`: a gloss linked to its word with type, direction, maker and certainty;
  a project-added type works; an unknown one is refused.
- `source.link.any-depth`: a comment on a comment on a line is reached at depth 3; a ring of
  three returns three and ends; depth 9 is refused.
- `source.link.both-ways`: from the word, the gloss is found (`direction=in`); from the gloss,
  the word (`out`); a link whose segment was merged is found from the kept segment.
- A link across two documents works.
- The four existing link records' tests still pass untouched.

**For the maintainer:** nothing new. (That there is to be one typed-link record, with the
canvas's connector converging on it, came out of the reviews and is in the spec; the canvas
half belongs to the canvas's own spec.)
