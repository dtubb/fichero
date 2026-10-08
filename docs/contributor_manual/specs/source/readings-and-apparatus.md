# Source Model — Readings and the scholar's apparatus — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — part of the "How Fichero represents a source" section: that one patch of ink
> can carry several readings, which one counts, and how hands, campaigns, damage and a
> researcher's own notes are recorded.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Every behaviour below is tagged **[GAP]** with its issue; everything
> is design unless the foundation's "What exists today" says otherwise.

## Intent

A segment is ink. This slice is about what people and machines *say* about that ink: what it
reads, who wrote it, in which campaign of writing, how sure anyone is, and what the researcher
thinks of it. All of it is kept, with its author, and none of it overwrites anything else.

It grows from what exists: a reading today is a `ContentRepresentation` (immutable, anchored,
with language, script, producing tool and model, a review state, and human revisions). This
design keeps that record and lets it hang on any segment, not only on a whole document.

## The design

### Readings are a set

A segment has any number of **readings**. A reading has:

- its **text** (which may include declared signs: see `languages-scripts-signs.md`);
- its **kind**: *as written* (letter for letter), *expanded* (abbreviations opened),
  *normalised* (spelling regularised; this is where the normalization spec's planned second
  text field goes: one reading of kind *normalised*, not a second field), *as read aloud* (the qere; the Japanese reading of a
  Chinese text), *transliteration*, *translation*, *description* (what a picture shows),
  *coordinate* (for a map control point), *music* (the notes or neumes of a music segment,
  in the field's encoding), *drawing* (a diagram, a map outline or a letterform as lines that can be scaled and edited:
  an SVG; the SVG kind and the Convert-to-SVG tool that exist today are this kind). A project can add kinds;
- **how normalised it is**, as a named level. Three sensible defaults ship (*as written*,
  *expanded*, *normalised*) and the list is open: a project can define its own as part of its
  guideline. Levels cannot be reliably converted into each other, so the level is recorded,
  never assumed;

  > **TEI's `<choice>` is two readings, not normalisation prose** (noted 2026-09-27, for whoever
  > builds TEI import or the reading editor next). `<choice><orig>vnto</orig><reg>unto</reg></choice>`
  > and its siblings (`<sic>`/`<corr>`, `<abbr>`/`<expan>`) are ONE segment carrying TWO readings of
  > different kinds — *as written* and *normalised*, or *as written* and *expanded* — whose
  > relationship is stated by the encoder. The model already has both halves: reading kinds, and a
  > reading's normalisation level. So a `<choice>` maps onto two readings of the same segment, and
  > the pair must be written back as a `<choice>` rather than as two unrelated readings. The trap
  > is treating normalisation as a property of THE text: then `<choice>` has nowhere to go but a
  > second field, which is exactly what this spec rules out above, and it gets built twice — once
  > as prose-level normalisation, once as a special case in the TEI reader. Belongs with
  > `source.reading.kinds` and the TEI round trip (`source.format.round-trip-tei`, #4945), not with
  > `historical-text-normalization.md`'s rules, which are about DERIVING a normalised reading, not
  > about carrying one an encoder already made.
  >
  > **Built so far (2026-09-27), and what is owed.** The TEI reader takes a `<choice>`'s AS-WRITTEN
  > side (`orig` / `sic` / `abbr`) for the line's text, keeps the other side verbatim with its
  > character position (the segment's `tei-choice`), and the export's loss report names each one on
  > its own line. It no longer joins both sides into one word (#5130; four DDbDP papyri,
  > `test_tei.py::TestAChoiceIsNotTwoWordsRunTogether`). **Owed:** the pair as TWO readings of one
  > word segment, written back out as a `<choice>`. That waits for word-level segments from TEI.
  > The same holds for an `<app>` that varies PART of a line (a papyrus's one-word `<rdg>`): the
  > `<lem>` is the line's text, the `<rdg>` is kept with its position (`tei-app`) and named by the
  > loss report, and carrying it as a reading of the word is owed with the rest. An `<app>` whose
  > `<lem>` is the whole line still gives the line whole-line readings.
- its **language and script**;
- **what it was read from**: which image of the page, and, for a reading made from another
  reading (a translation, a normalisation), which one;
- its **author**: a person, or a model and run;
- **how sure the machine was**, if a machine made it. If it gave a confidence for each
  character, that is kept on the line's reading; no character segments are made for it;
- **the guideline it follows**, if any (a transcription convention);
- when it was made.

Readings are never edited in place. A correction is a new reading (or a revision of a human
one) that names what it corrects.

### One patch of ink, many conversions

The same segment can be turned into many things, and each is just another reading or another
worked-out thing hanging on it, with its author and what it was made from: a transcription;
an expansion; a translation; a transliteration; a description; a **table of data** (for a
table segment); a **drawing** (for a diagram, a map or a letterform); a vector; a list of
names found. None replaces another. New kinds of conversion are new entries in an open list,
and a new job in a chain, not a change to the model.

### Several readings can all be right

An undotted Arabic word that can honestly be read three ways has three readings of the same
kind, side by side, each with the scholar's certainty. This is different from a machine's
ranked guesses. The model holds both, and does not mix them up.

### Which reading counts

For each kind, one reading can be **the chosen one**: what the Reader shows first, what
export writes. How it comes to be chosen is **the project's rule** (ruled 2026-09-19). In a
*strict* project, which is how every new project starts, only a person chooses: until someone
has, the Reader shows the newest reading and **labels it plainly as a machine's and
unchosen**; search still finds it; an export marks it as machine-made in its loss report. In
a *relaxed* project (a searchable archive, say) the newest reading counts, and a person's
always outranks a machine's. Among machines' readings, an older one never counts while a better one
exists: a reading a person checked comes first, then the one whose reader measured better on this
project, then the newest; the date only breaks ties (#5558). Either way a machine reading is always *shown* as a machine's. Whether a reading was made by a person or a machine is set by the engine from how it
arrived, never claimed by the sender. The choice is itself recorded, with who and when, and
changing it rewrites nothing.

How it is kept: only a person's **deliberate choices** are stored (this segment, this kind,
this reading, who, when). Everything else is worked out when asked. So switching a project
between strict and relaxed changes an answer and rewrites nothing.

**What an audited record may hold** is an open, blocking question (morning file): every
action's record sits in a tamper-evident chain, so a researcher's words stored there could
never be purged. The default taken: reading and segment actions record ids and digests, and
undo restores from the versions kept as ordinary data.

### Written and read

Some ink has two true forms: the abbreviation and its expansion; the word as written and the
word to be read aloud; the Chinese sentence and its reading in Japanese. These are a **pair**
of readings joined as *written* and *read*, not an error and its correction. Corrections
exist too (the scribe wrote it wrong; the editor emends), and are marked as corrections.

### Hands

A **hand** is who put the ink on the page: a named scribe, or "hand B", with a date or period,
a place, a script style, and notes. A hand is a record in the project, shared across sources,
so "everything in hand B" can be asked. A segment, or a campaign of a segment, can name its
hand, with certainty and the author of that judgement. Several scholars can disagree.

A hand is not provenance. Provenance says who made the *record* (a model, a person, a
workflow run). Both are kept, separately, always.

### Campaigns

One patch of page can carry several **campaigns of writing**: the main ink; the rubric; vowel
marks added a century later; reading-marks pressed in with a stylus; the under-text of a
palimpsest; a modern librarian's pencil. A campaign has a name, an order (what lies over
what), and optionally a hand and a date. Segments belong to a campaign. Two campaigns can
share the same characters (the consonants and their later vowels), and a reading can say
which campaigns it takes in.

### Three different kinds of "sure"

1. **The machine's confidence** in its reading. A number from the model.
2. **The scholar's certainty** about a reading, a hand, a link, a date. A judgement, with a
   reason and an author.
3. **The state of the page**: damaged, faded, lost, erased, overwritten, with how much and
   why (water, a hole, trimming), recorded as a fact about the segment.

They are never merged into one number.

Editorial facts are recorded as facts: *unclear*; *lost* (with extent); *restored by the
editor*; *supplied* (left out by the scribe); *superfluous*; *deleted by the scribe*; *added
by the scribe* (and where: above the line, in the margin). The editor's brackets and dots
(the Leiden conventions, or a project's own) are **drawn from these facts** when a reading is
shown or exported. They are never typed into the text.

### Letterforms

For palaeography, a character segment can be described in the terms the field uses: the
abstract character; the recognised form of it (allograph); this scribe's way of making it;
and this very mark on the page; with **components and features** ("ascender: wedged"). The
lists of components and features are open. A hand can then be characterised by its marks,
and marks compared across sources. (The model is Archetype's; see the survey.)

### The researcher's own marks

Notes, highlights, checks and tags go on any segment at any level, exactly as they go on a
document: the same records, not a second kind. (The app's ruled mark is a **check**, not a
star; `ui/reading-markup-annotations.md` owns marks, and what follows extends it: routed.) In
addition:

- marks live in **named sets with an author**, so two researchers' annotations of one source
  can overlap, disagree and be shown separately or together;
- one mark can cover **several segments** that are not next to each other;
- a mark can point at a stretch of a reading as well as at a segment. A stretch always names
  the exact reading it was measured on, never "the chosen one". If that reading is replaced,
  the stretch is carried onto the new reading where the words still match, and otherwise
  reported as unplaced. It is never silently re-measured.

### Dates, in any calendar

A date on a page is ink like anything else: a segment with a reading ("the third year of
King Darius"; "12 Baktun 4 Katun…"; "era 1014"; "the feast of Saint John"). What it *means*
is an interpretation, and there can be more than one.

What exists (`histnorm.dates.jdn-core` in `historical-text-normalization.md`; partly built and
tested): a
date is stored as a **range of days on one common count** (the Julian Day Number), never
collapsed to one guessed day, with conversion from the Gregorian, Julian, French Republican,
Hebrew and Islamic calendars, regnal years and Chinese era names, and "explicitly undated"
kept apart from "no date found". It hangs on a whole document.

What this design adds:

- **A date hangs on a segment**, not only on a document: the dating clause of a charter; a
  diary entry's heading; the date in a colophon.
- **A date has three parts, kept apart.** *As written* (a reading, in its own language and
  script). *In its own calendar*, as parts (era, year, month, day, cycle position), with the
  calendar named from an open list. *On the common count*, as a range of days, worked out
  from the second.
- **Calendars are an open list**, like every vocabulary here. Beyond those built: the
  Seleucid era (common in Aramaic and Syriac sources), Babylonian and other regnal
  reckonings, the Spanish era (thirty-eight years ahead; used in tenth-century Iberia),
  Coptic, Ethiopic, Persian, Indian, Japanese and Chinese era names, indictions, Roman
  consular and *ab urbe condita* years, dating by feast days, and the Maya Long Count and
  Calendar Round. A project can add one.
- **A conversion records its assumptions.** Turning a calendar date into days always rests on
  choices: which correlation between the Maya count and ours; whether an Islamic month began
  by sighting or by table; when the year began (January, March, Easter); which king's reign
  and from when. Each interpretation names the rule and the choices it used, its author, and
  the scholar's certainty. Rival interpretations stand side by side, like rival readings.
- **A calendar with no conversion is still a calendar.** A date can be recorded faithfully in
  a calendar Fichero cannot convert. It is then sortable within its own calendar, shown as
  written, and honestly absent from the common timeline until a rule or a person supplies a
  range.
- **Cycles and partial dates are first-class.** "A Tuesday in Lent", a Calendar Round that
  recurs every fifty-two years, a regnal year without a day: each is a set of possible ranges,
  narrowed by other evidence, not an error.
- **The field's formats in and out**: the extended date format (EDTF) for uncertain and
  approximate dates; TEI's dating attributes (calendar, custom dates, dating method); PeriodO
  for named periods ("the Umayyad period") as ranges with an authority. (Named from general
  knowledge; to be checked. The open question of adopting an off-the-shelf date library, #4364
  (`histnorm.dates.adopt-standards-format`), stays with the normalization spec.)
- The timeline, sorting and search use the common count, so sources dated in different
  calendars can be set in one order.

### Descriptions of pictures

A picture, seal, stamp, diagram or map segment has readings of kind *description* (what it
shows; alt text) and may have **classifications** (a seal; a map; music; a portrait), each
with its author and, if a machine made it, its confidence. A description is a reading like
any other: several can exist, one is chosen, none is overwritten.

## Behaviors (every one is **[GAP]**: designed, not built; each cites its issue on milestone `source-model`, 322)

Readings
- `source.reading.set` — **[OK]** (#4934; pinned by `tests/unit/api/test_segment_readings.py::TestReadingsAreWritten::test_three_readings_of_one_line_coexist_and_adding_one_changes_no_other`) a segment can have many readings; adding one never changes another.
- `source.reading.kinds` — **[OK]** (#4934; pinned by `tests/unit/models/test_reading_kinds_and_choices.py::TestTheKindsListIsOpen::test_an_unknown_kind_is_refused_and_the_list_is_named`) a reading has a kind from an extendable list whose shipped defaults
  are: as written, expanded, normalised, as read aloud, transliteration, translation,
  description, coordinate, music, drawing.
- `source.reading.level-recorded` — **[OK]** (#4934; pinned by `tests/unit/models/test_reading_kinds_and_choices.py::TestTheGrownRecord::test_level_is_never_inferred`) every reading says how normalised it is; the level is
  never inferred or silently converted.
- `source.reading.read-from` — **[OK]** (#4934; pinned by `tests/unit/api/test_segment_readings.py::TestReadingsAreWritten::test_the_image_it_was_read_from_is_recorded`) a reading names the image it was read from, and the reading it
  was made from if it has one.
- `source.reading.author-and-guideline` — **[OK]** (#4934; pinned by `tests/unit/api/test_segment_readings.py::TestReadingsAreWritten::test_a_reading_names_its_author_not_only_the_kind_of_author`) a reading names its author (person, or model and
  run) and any guideline it follows.
- `source.reading.corrections-are-new` — **[PARTIAL]** (#4934; pinned by `tests/unit/api/test_segment_readings.py::TestReadingsAreWritten::test_a_correction_names_its_target_and_leaves_its_text_alone`) a correction is a new reading that names what it
  corrects.
  **And it counts (#5175, 2026-09-28):** a person's correction outranks the reading it names, basis
  `correction`; a chain leaves its last link; ⌘Z brings the corrected reading back; a choice still
  wins; independent readings stay equal alternatives
  (`fichero-server/tests/unit/api/test_a_correction_counts.py::test_a_correction_of_a_persons_reading_does_not_blank_the_line`
  and five more).
- `source.reading.correct-a-line` — **[OK]** (#5499) correcting a line takes the segment and its new
  text, nothing more: `POST /api/segments/{segment_id}/correct` `{text}` (CLI `segments correct-line
  <segment_id> --text ...`, MCP `fichero_segments_correct_line`). It is one `representation.create`, the
  action every correction is, so it is audited and undone as one; the engine fills in the document, the
  reading it corrects (the one counting now, or the file's text a provisional reading still lives in)
  and the compare-and-set: when another reading counts than the one the caller read
  (`expected_counting_id`), it is refused with 409 and nothing is written. Who corrects is the caller,
  so a person's correction counts over a machine's reading. The `kind` defaults to `transcription`.
  Left: the bake-off counting a person's readings on a model's pass as ground truth (#4951).
  Pinned by `fichero-server/tests/unit/api/test_correct_a_line.py`.
- `source.reading.equal-alternatives` — **[OK]** (#4934; pinned by `tests/unit/models/test_counting_and_working_pass.py::TestStrictProject::test_three_peoples_readings_coexist_and_nothing_counts_until_one_is_chosen`) several readings of one kind can stand as equally
  valid, apart from a machine's ranked guesses.
- `source.reading.chosen-is-worked-out` — **[OK]** (#4934; pinned by `tests/unit/models/test_counting_and_working_pass.py::TestALiveHumanChoiceWinsInAnyProject::test_a_superseded_choice_is_history_not_a_vote`) "which reading counts" is worked out from recorded
  human choices, who made each reading, how recent it is and the project's rule; it is never a
  flag stored on a reading, so changing the project's rule rewrites nothing.
- `source.reading.chosen-follows-project-rule` — **[OK]** (#4934; pinned by `tests/unit/models/test_counting_and_working_pass.py::TestRelaxedProject::test_the_newest_of_several_peoples_readings_counts`) in a strict project only a person chooses the
  reading that counts; in a relaxed project the newest counts and a person's outranks a
  machine's; a new project is strict; the choice is recorded and changing it rewrites nothing.
- `source.reading.machine-ranked-by-measure` — **[PARTIAL]** (#5558; pinned by `tests/unit/check/test_which_reading_counts_after_the_tie.py`) *Built 2026-10-06: `resolve_counting` ranks machine readings (`readings._best_machines_first`) with what `segment_readings.ReadingMeasures` looks up where a kind has two or more machine readings: checked (the person's newest `check.verdict` on the reading is a confirm, or the reading was made from a page reading, `derived_from_artifact_id`, a person confirmed or marked reviewed, unless the reading's own newest verdict is a reject), then the reader's measured CER on this project (`evaluation.measured_here`: the newest evaluation on the model's card scored on this project's pages, the bake-off's own judgement; within one point of CER is a tie, as in the bake-off), then the newest. Only measured readers are compared; a score is never invented, and with no scores the newest counts as before. The page's text, segment lists, the PAGE export and the training set all read it through `counting_by_kind`. Not built: a cloud reader is never measured (the evaluation has no remote target yet, #5533), so between a cloud reading nobody checked and a newer measured re-read the date still decides.* among machines' readings, a checked one counts first, then the one whose reader measured better on this project, then the newest; the date only breaks ties. A person's reading still outranks every machine's.
- `source.reading.machine-is-labelled` — **[OK]** (#4934; pinned by `tests/unit/models/test_counting_and_working_pass.py::TestALiveHumanChoiceWinsInAnyProject::test_choosing_a_machines_reading_does_not_make_it_a_persons`) a machine's reading is always shown as a machine's,
  and in a strict project as unchosen; exports mark it machine-made.
- `source.reading.maker-set-by-engine` — **[OK]** (#4934; pinned by `tests/unit/api/test_segment_readings.py::TestReadingsAreWritten::test_the_maker_is_the_engines_answer_not_the_callers`) whether a person or a machine made a reading or a pass
  is the existing engine-set `ProvenanceKind` (the one claims use, → #4868, → #4869), not a new
  field, and is never claimed by the sender.
- `source.reading.stretch-names-its-reading` — **[OK]** (#4934; pinned by `tests/unit/api/test_document_derived_text.py::TestAStretchSurvivesTheReadingChanging::test_the_offsets_move_rather_than_being_kept`) a stretch of text names the exact reading it was
  measured on; when that reading is replaced it is carried over or reported unplaced.
- `source.reading.written-read-pair` — **[OK]** (#4934; pinned by `tests/unit/api/test_segment_readings.py::TestReadingsAreWritten::test_a_written_and_read_pair_is_joined_and_can_be_undone`) two readings can be joined as written and read, apart
  from error and correction.
- `source.reading.char-confidence-on-line` — **[OK]** (#4934; pinned by `tests/unit/api/test_segment_readings.py::TestPerCharacterDetailRidesOnTheLine::test_a_character_can_be_pointed_at_with_no_character_segment`) per-character positions and confidence ride on a
  line's reading without character segments existing.

Hands and ink
- `source.hand.record` — **[OK]** (→ #4935) a hand is a project record (name or label, date, place, style, notes)
  shared across sources. Engine side: `models/hands.py`, the audited `hand.create` / `hand.withdraw`, and
  `GET /api/hands/{id}/attributions` for everything in one hand across sources. Tested by
  `fichero-server/tests/unit/api/test_hands.py::test_a_hand_is_a_project_record_shared_across_sources`.
- `source.hand.attributed` — **[PARTIAL]** (#4935) a segment or campaign names its hand, with certainty and the
  author of the judgement; rival attributions coexist. **Segments: built** (`hand.attribute`, certainty 0–1,
  the judge as `created_by`; a second judgement never replaces the first --
  `test_hands.py::test_rival_attributions_stand_side_by_side`). **Campaigns: owed**, with campaigns.
  **From the file too (approved 2026-09-27):** an EpiDoc `<handShift new>` becomes, on import, a hand
  labelled with its edition ("m2 (p.cair.zen.4.59742)") and an attribution of each line it wrote,
  whose `source` says the file said so. A file's "m1" is its own first hand, so two papyri's "m1" stay
  two hands; merging them is a person's judgement (`test_hands.py::test_two_papyri_s_m1_are_two_hands`).
- `source.hand.not-provenance` — **[PARTIAL]** (#4935) the Inspector shows who wrote the ink and who made the record
  as two separate facts. **The engine keeps them apart** (the attribution names the hand; its `created_by` and
  `provenance_kind` name who judged -- `test_hands.py::test_the_hand_is_not_who_made_the_record`); the Inspector
  does not show either yet.
- `source.campaign.ordered` — **[PARTIAL]** (#4935) a source has ordered campaigns; segments belong to one; campaigns can
  share characters.
  **Built engine-side:** `campaign.create` (ordered by `sequence`), `campaign.assign`, which moves a segment into exactly one and undoes (`fichero-server/tests/unit/api/test_campaigns.py::test_campaigns_are_ordered_and_a_segment_belongs_to_one_moves_and_undoes`). Characters are shared by two campaigns' segments overlapping, not by one segment in two. **Missing:** the app shows none of it yet.
- `source.campaign.reading-says-which` — **[PARTIAL]** (#4935) a reading can say which campaigns it takes in.
  **Built engine-side:** `reading.take_in`; undo restores the earlier answer (`fichero-server/tests/unit/api/test_campaigns.py::test_a_reading_says_which_campaigns_it_takes_in_and_undo_restores_the_earlier_answer`). **Missing:** the app shows none of it yet.

Sureness and damage
- `source.sure.three-kinds` — **[GAP]** (#4935) machine confidence, scholarly certainty and the state of the page
  are separate fields, never combined.
- `source.sure.editorial-facts` — **[PARTIAL]** (#4935) unclear, lost, restored, supplied, superfluous, deleted and
  added are recorded as facts with extent, reason and author.
  **Built engine-side:** `editorial.record` / `withdraw` with extent, reason, place, certainty and author (`fichero-server/tests/unit/api/test_editorial_facts.py::test_a_fact_is_recorded_with_its_extent_reason_and_author_and_drawn_not_stored`, `fichero-server/tests/unit/api/test_editorial_facts.py::test_a_lost_stretch_with_no_text_is_recorded_by_its_extent`). **Missing:** the app; importers mapping a file's own marks (PAGE `unclear`, TEI `unclear`/`supplied`/`gap`).
  **From a file (2026-09-28, #5179):** `format.import` writes a file's marks as facts on the reading
  it made -- PAGE `unclear {offset;length}`; TEI `<unclear>`, `<supplied>` (lost -> restored,
  omitted -> supplied), `<gap>` (a position; illegible -> unclear with no span), `<surplus>`, `<add>`
  -- `external_import`, `source` "file: <name>", in the import's own action so its undo takes them;
  what cannot be a fact is named in `not_imported` (`fichero-server/tests/unit/api/test_marks_arrive_as_editorial_facts.py`, the Syriac PAGE page and the DDbDP
  papyri). `<del>`, ruled 2026-09-28 (diplomatic): the deleted letters stay IN the reading and a
  `deleted` fact spans them, drawn ⟦ ⟧ -- nested deletions nest -- so a `<subst>` reads both its
  added and its deleted letters, the struck ones marked
  (`fichero-server/tests/unit/api/test_marks_arrive_as_editorial_facts.py::test_deleted_letters_stay_in_the_reading_as_a_deletion_drawn_in_double_brackets`,
  `fichero-server/tests/unit/formats/test_tei.py::TestARealFileAnotherProjectWrote::test_deleted_text_stays_in_the_reading_as_does_added_text`).
  `<delSpan spanTo="#x">` (2026-10-01): a deleted fact on every line it runs through, from where it
  stands to where `x` stands (an `<lb>`, a block, any element with that id), the lines between
  deleted whole; one whose target the file never names, or that ends before it starts, is named
  in `not_imported`
  (`fichero-server/tests/unit/api/test_marks_arrive_as_editorial_facts.py::test_a_deletion_across_lines_is_a_deletion_on_every_line_it_runs_through`,
  on the TEI Consortium's own sample). Still owed: a screen.
- `source.sure.search-finds-what-stands` — **[OK]** (→ #5179, ruled 2026-09-28: "search must match the
  corrected word X alone") a search finds a line by the text that stands, with every `deleted`
  stretch left out, so a `<subst>` read diplomatically as "XY" (X added, Y struck) is found by X
  alone, in full text and fuzzy search alike. The deleted letters are still in the reading, still
  drawn ⟦ ⟧ in the Reader, and still found by a search for them. Applies to every deletion, not
  only an imported one.
  Built 2026-10-01: the page-text cache keeps the STANDING text (`Document.metadata.page_text_standing`,
  only when it differs) and refreshes it when a deletion is recorded or withdrawn; the search index
  holds it beside the page's passages (scope `standing`, no char span, so its excerpt has no
  highlight rather than a wrong one). Pinned by
  `fichero-server/tests/unit/api/test_search_finds_what_stands.py` (kept, withdrawn, absent, and a
  full-text search finding "Manor" on a page reading "M⟦m⟧anor" beside a page that says it plainly).
  Separate and not fixed here: full-text matching is case-sensitive while the index has a hit
  (#5307).
- `source.sure.brackets-are-drawn` — **[PARTIAL]** (#4935) editorial signs are produced from those facts on display
  and export; they are never stored in a reading's text.
  **Built engine-side:** `editorial/leiden.py` draws the signs when read and never changes the text (`fichero-server/tests/unit/models/test_leiden.py::test_nested_facts_draw_inside_out_and_the_text_is_never_changed`, `fichero-server/tests/unit/models/test_leiden.py::test_a_lost_stretch_with_no_text_is_a_gap_of_its_extent`). **Missing:** the app, and exports.
  **Imported marks draw (2026-09-28, #5179):** the Syriac page's whole-line `unclear` draws an
  under-dot on each of its 12 code points, and a papyrus's mid-line `<gap quantity="13">` draws
  `[--- 13 ---]` where it stands; the stored reading carries no sign (`fichero-server/tests/unit/api/test_marks_arrive_as_editorial_facts.py`).
  **TEI export (2026-10-01, #5179):** the live facts on the reading written are drawn as the
  elements an import reads them from -- `unclear`, `supplied` (lost / omitted), `gap`, `surplus`,
  `del`, `add` -- nested where they nest; one that crosses another's edge is written plain and
  named in the loss report. A page imported, exported and imported again carries the same facts over
  the same letters (`test_marks_arrive_as_editorial_facts.py::test_the_facts_go_back_out_as_tei_and_come_back_the_same`,
  the four DDbDP papyri and the Syriac PAGE page). **PAGE export (2026-10-01):** `unclear` facts
  are written as `custom` `unclear {offset;length}` from the library, replacing the marks kept from
  import, so a withdrawn mark is not written back; the kinds PAGE has no `custom` form for are named
  in the loss report (`::test_a_page_xml_export_writes_the_unclear_facts_as_they_stand_now`).
  Still missing: ALTO (no standard place for these marks), and the app.
Letterforms
- `source.letterform.chain` — **[PARTIAL]** (#4935) a character segment can name its character, its allograph and
  its scribe's form.
  **Built engine-side:** `letterform.describe` names character, allograph and hand (`fichero-server/tests/unit/api/test_letterforms.py::test_a_mark_names_its_chain_and_features_and_is_gathered_across_hands`). **Missing:** the app shows none of it yet.
- `source.letterform.features` — **[PARTIAL]** (#4935) a character segment can carry components and features from
  open lists.
  **Built engine-side:** components and features from open lists; describing again supersedes and undoes (`fichero-server/tests/unit/api/test_letterforms.py::test_describing_a_mark_again_supersedes_and_undo_and_redo_swap_them_back`). **Missing:** the app shows none of it yet.
- `source.letterform.compare` — **[PARTIAL]** (#4935) marks of the same character can be gathered and compared
  across hands and sources.
  **Built engine-side:** `GET /api/letterforms` gathers by character, allograph or hand across sources (`fichero-server/tests/unit/api/test_letterforms.py::test_a_mark_names_its_chain_and_features_and_is_gathered_across_hands`). **Missing:** the app shows none of it yet.

Dates
- `source.date.on-segment` — **[GAP]** (#4936) a date can hang on any segment, not only on a document.
- `source.date.three-parts` — **[GAP]** (#4936) a date keeps its wording, its parts in a named calendar, and a
  range of days on the common count, separately.
- `source.date.open-calendars` — **[GAP]** (#4936) calendars come from an open list a project can extend.
- `source.date.conversion-names-its-choices` — **[GAP]** (#4936) an interpretation names the rule, the choices
  (correlation, month reckoning, start of year, reign), its author and certainty; rival
  interpretations coexist.
- `source.date.unconvertible-is-kept` — **[GAP]** (#4936) a date in a calendar with no conversion is stored,
  shown and sortable within that calendar, and absent from the common timeline.
- `source.date.cycles-and-partials` — **[GAP]** (#4936) a recurring or partial date is a set of possible ranges.
- `source.date.one-timeline` — **[GAP]** (#4936) sorting, search and the timeline use the common count across
  calendars.

Marks and descriptions
- `source.mark.any-level` — **[GAP]** (#4937) notes, highlights, checks and tags go on any segment, using the same
  annotation records a document uses (owner: `ui/reading-markup-annotations.md`).
- `source.mark.authored-sets` — **[GAP]** (#4937) marks live in named, authored sets that can be shown apart or
  together.
- `source.mark.many-segments` — **[GAP]** (#4937) one mark can cover several separate segments, or a stretch of
  a reading.
- `source.picture.described` — **[GAP]** (#4937) a non-text segment has descriptions and classifications as
  readings, with authors; one is chosen.

## Test matrix

To be filled at approval. Until then, the real files that hands, campaigns and editorial facts are
tested on:

- **Until the EpiDoc editions are wired in, the TEI Consortium's transcription test file
  (`fichero-server/tests/unit/formats/fixtures/tei_consortium_testtranscr.xml`) is the only real `@hand`
  in the fixtures.** One file, one project's idea of hands.
- **Four DDbDP papyri** (EpiDoc, CC BY 3.0, vendored 2026-09-27; rows in
  `fichero-server/tests/unit/formats/fixtures/corpus/CORPUS.md`, files `ddbdp_greek-papyrus_*.tei.xml`):
  `<handShift new>` (up to three hands a papyrus), `<unclear>`, `<supplied reason="lost">`, `<gap>`,
  `<del>`, `<add>` and `<choice><reg>/<orig>`. They are what `source.hand.*`, `source.campaign.*` and
  `source.sure.editorial-facts` are to be built against. They already found one defect: the TEI reader
  joins both sides of a `<choice>` into one word (`test_tei.py::TestAChoiceIsNotTwoWordsRunTogether`,
  strict xfail, #5130).

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
