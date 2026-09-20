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

## Slice 10 — named reading orders, flows, and the one typed-link record (#4930, #4931)

**Pins:** `source.order.named-multiple`, `source.order.next-previous`, `source.segment.flow`;
`source.link.typed`, `source.link.any-depth`, `source.link.both-ways`. (`source.canvas.*` is app
work and waits for the canvas's own spec, → #3085.)

### Reading orders

**What exists.** No stored order. The region-edit code sorts boxes by character span, else top
then left (`_reading_order` in `api/routes/document/artifacts.py`). After slice 6 a converted
segment remembers its old place as `metadata.box_index`.

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
`readingorderentrys(order_id)`, `readingorderentrys(segment_id)`.

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
- A converted page's `as-written` order equals today's `_reading_order` of the same boxes.

### One typed-link record

**What exists (four link records, four vocabularies).** `NoteLink` (`models/knowledge.py`:
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
