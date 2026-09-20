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
