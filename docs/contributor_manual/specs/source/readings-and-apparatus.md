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
- its **kind**: *transcription*, *as read aloud* (the qere; the Japanese reading of a
  Chinese text), *transliteration*, *translation*, *description* (what a picture shows),
  *coordinate* (for a map control point), *music* (the notes or neumes of a music segment,
  in the field's encoding), *drawing* (a diagram, a map outline or a letterform as lines that can be scaled and edited:
  an SVG; the SVG kind and the Convert-to-SVG tool that exist today are this kind). A project can add kinds;
- **how normalised it is**, as a named **level** (ruled 2026-10-10). Levels are levels, not kinds:
  an expanded transcription is still a transcription, read further from the ink. Five ship:
  - *graphemic*: letter for letter, letterforms told apart (long s, r rotunda);
  - *as written*: the letters, each abbreviation kept as the scribe wrote it;
  - *expanded*: abbreviations opened (*dha* is *dicha*);
  - *regularised*: u/v, i/j and long s regularised, spelling otherwise kept (this is where the
    normalization spec's planned second text field goes: one reading at level *regularised*, not a
    second field);
  - *modernised*: spelling and punctuation made modern.

  The list is checked like the kinds list and open like it: a project can add its own as part of its
  guideline, and a level outside the list is refused, naming the list. An older spelling is the level
  it means, never a new one: *normalised* (the third level that shipped before 2026-10-10) is
  *regularised*, and *as-written* (the spelling recipes and the setup sheet send) is *as written*.
  Levels cannot be reliably converted into each other, so the level is recorded, never assumed;
  a reading with no level says so.

  The kind *normalized text* that shipped before levels were checked is a transcription at a level
  (*regularised*), and its rows read as that (`source.reading.normalized-text-is-a-level`). An OCR
  clean-up is not a level: it is a correction of the transcription as written.

  > **TEI's `<choice>` is two readings, not normalisation prose** (noted 2026-09-27, for whoever
  > builds TEI import or the reading editor next). `<choice><orig>vnto</orig><reg>unto</reg></choice>`
  > and its siblings (`<sic>`/`<corr>`, `<abbr>`/`<expan>`) are ONE segment carrying TWO readings of
  > different levels — *as written* and *regularised*, or *as written* and *expanded* — whose
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

For each kind **at each level**, one reading can be **the chosen one**: what the Reader shows first, what
export writes. Readings compete only with readings of the same kind at the same level (ruled
2026-10-10): a person's expanded reading of a line never replaces the line as written, and a
person's correction as written never retires an expanded reading. A reading with no level competes
at *as written*. Where one answer per kind is asked for (the page's text, segment lists, export, a
training set), it is the answer at *as written*, or, when the kind has no reading there, at the
first level it has. How it comes to be chosen is **the project's rule** (ruled 2026-09-19). In a
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
this reading, who, when; the level is the chosen reading's, so choosing at one level leaves a choice
at another standing). Everything else is worked out when asked. So switching a project
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

### Where the readers disagree (#5665)

A fourth thing, not one of those three: **agreement** between readers. Read a page with several readers
(Kraken models, Apple Vision, MLX vision models; or one model sampled several times at temperature, the
Mattingly method of 5 runs at 0.7) and the words they disagree on are where correction should go first.
It is agreement, never accuracy: with no checked reference, it says how far readers differ, not who is
right (the comparison route's rule, `api/routes/document/compare_readings.py`).

Before comparing, every reading is brought to one convention, the line **as written** in the CATMuS
sense: abbreviations left unexpanded, spelling and scribal slips kept, u/v and i/j folded, diacritics
decomposed (NFD). Otherwise the comparison shows that one reader expands and another does not, not doubt.
Per line, the medoid reading (the one most like the others) is the reference; each other reading is
aligned to it character by character, and each word of the reference scores the share of readers that
gave exactly that word. The person sees it on the page, word by word: plain where the readers agree,
yellow where some differ, red where most do; a word's variants and who gave each; the page's and each
line's figure; and the next doubtful word to correct. The disagreements a person resolves are the
corrections worth training on.

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
  are: transcription, as read aloud, transliteration, translation, description, coordinate, music,
  drawing. *As written*, *expanded* and *normalised* are levels, not kinds (`source.reading.levels`).
- `source.reading.level-recorded` — **[OK]** (#4934; pinned by `tests/unit/models/test_reading_kinds_and_choices.py::TestTheGrownRecord::test_level_is_never_inferred`) every reading says how normalised it is; the level is
  never inferred or silently converted.
- `source.reading.levels` — **[OK]** (ruled 2026-10-10; pinned by `tests/unit/api/test_reading_levels.py::TestFiveLevelsShip::test_an_unknown_level_is_refused_on_write_and_the_list_is_named`) five levels ship, seeded into the library's
  levels list when it opens (`libraryreadinglevels`, as the kinds are): graphemic, as written, expanded,
  regularised, modernised. A write naming a level outside the list is refused, naming the list; a
  project can add a level. An older spelling is stored as the level it means, at the engine's boundary:
  `as-written` is `as_written`, `normalised` is `regularised` (and a stored `normalised` row reads back as
  `regularised`, never rewritten). Also pinned by
  `tests/unit/api/test_reading_levels.py::TestOldSpellingsAreTheLevelsTheyMean` and
  `::TestFiveLevelsShip::test_the_five_levels_are_seeded_when_a_library_opens`.
- `source.reading.counts-per-level` — **[OK]** (ruled 2026-10-10; pinned by `tests/unit/api/test_reading_levels.py::TestWhichReadingCountsIsPerKindAndLevel::test_a_persons_expanded_reading_does_not_replace_the_line_as_written`) which reading counts is worked
  out per kind AND level (`segment_readings.counting_by_kind_and_level`): a person's expanded reading of
  a line never replaces the line as written, so the page's text, export and the Kraken training set keep
  `dha`. A reading with no level competes at as written. One answer per kind (`counting_by_kind`, what
  the readings list's `counting`, the page's text, segment lists and export read) is the as-written one,
  else the kind's first level. A choice supersedes only the choices at its own level, and a write's
  compare-and-set compares against the reading counting at the level written. Also pinned by
  `::test_choosing_an_expanded_reading_leaves_the_as_written_choice_standing`,
  `::test_writing_an_expanded_reading_is_not_stale_against_the_as_written_one` and
  `::test_a_persons_as_written_correction_still_counts_over_the_files`. Not built: the readings list
  reports one counting answer per kind; a per-level answer on the wire needs a contract change.
- `source.reading.normalized-text-is-a-level` — **[OK]** (#5653; pinned by `tests/unit/api/test_normalized_text_is_a_level.py::TestOldRowsReadAsATranscriptionAtALevel::test_it_counts_at_its_level_beside_the_line_as_written_never_over_it`) the kind `normalized_text` is a
  transcription at level regularised. A row stored under it reads as kind transcription, level
  regularised (its own level kept when it recorded one) wherever readings are listed, counted and
  exported, and the row is never rewritten: one mapping, `readings.canonical_reading_kind_and_level`,
  applied as the reading (`ContentRepresentation`), a choice (`ReadingChoice`) and the readings list's
  item are built. It counts at its level, beside the line as written and never over it. A write under the
  old kind is stored as a transcription at that level; a choice under it is a choice of a transcription.
  A filter that still names it (the readings list's `kind`, whose counting answer is keyed by the kind
  asked for; `counting_texts`; the page's text; the PAGE export's `reading_kind`) is answered with the
  transcription at level regularised, so older callers find what they found; the PAGE export also takes
  a level of the kind (`page_from_library(reading_level=...)`). The writers: the Modernización preset
  writes a transcription at level *modernised* (its prompt asks for modern spelling, accents and
  punctuation, beyond u/v and i/j), its run's artifact typed `modernised`, never `transcription`; a saved
  Analyze step that still names `normalized_text` writes at *regularised*; Clean text writes a
  correction of the transcription as written (kind transcription, level as written), derived from the
  node's as-written reading it cleans when the node has one, beside it. A row updated for another reason
  (a choice superseded) is saved in the new shape, which means the same. Also pinned by
  `tests/unit/api/test_normalized_text_is_a_level.py` (the filter, the PAGE export, writes and choices
  under the old kind) and `tests/unit/workflows/test_text_outputs_are_readings.py::test_clean_text_writes_a_correction_of_the_transcription_as_written`,
  `::test_a_historical_preset_saves_a_reading_of_its_kind`,
  `::test_a_saved_analyze_step_that_still_names_normalized_text_writes_a_transcription_at_a_level`.
- `source.reading.abbreviation-markup-parsed` — **[PARTIAL]** (#5651; pinned by `tests/unit/api/test_names_read_expanded_text.py::test_no_markup_reaches_spacy`) a corpus's abbreviation markup in a
  line's text (`dha$.dicha`, `Parq.$^l$.Parroquial`, `$ant:Miguel`, `le:$-`; PAGE `custom` `abbrev
  {offset; length; expansion}`) is read into the line as written (markup gone, abbreviation kept:
  `dha`) and expanded (`dicha`) by `formats/abbreviation_markup.py`. Names and statements (the NLP draft
  at import, the extract-names workflow) are read from each line's expanded reading where one counts,
  else from the text with its markup read; a page with no markup is read exactly as before. The Kraken
  training set holds every line as written, so `$` is never learnt as a letter. Also pinned by
  `tests/unit/formats/test_abbreviation_markup.py`,
  `tests/unit/api/test_names_read_expanded_text.py::test_a_lines_expanded_reading_is_what_names_are_read_from`
  and `tests/unit/training/test_kraken_training_set.py::test_the_set_does_not_learn_abbreviation_markup_as_text`.
  **The import (#5651, built 2026-10-12):** a PAGE import saves each line's abbreviations opened as its own
  reading at level `expanded`, from the inline markup or the line's `custom` abbrev tags, made from (and beside)
  the line as written, which still counts as the page's text; a line with nothing to open gets none. A training
  set, an evaluation, the reasons and the checks read each line as written (`reading_level="as_written"`).
  Pinned by `tests/unit/api/test_page_import_opens_abbreviations_5651.py`. **Search (#5651, built 2026-10-12):** the page's text
  (`page_content`) keeps its lines as the file had them, and what search reads beside it (the standing text,
  `page_text_cache.searched_text`, indexed and embedded with the page) has the abbreviations opened, so a search
  for `dicha` finds the page and no vector is made of markup; the derivation bump (15) re-derives each page
  once, a page with no markup gaining only the stamp. Pinned by
  `tests/unit/api/test_names_read_expanded_text.py::test_search_reads_the_page_with_its_abbreviations_opened`.
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
- `source.reading.kraken-line-is-its-own` — **[OK]** (#5500, 2026-10-11) a line Kraken reads carries
  its own reading and nothing else: the page's text is the read lines joined, and each line's reading is
  exactly its own slice of it, so no line shows its neighbour's words. A line Kraken finds but reads as
  empty (a ruled line on the paper) keeps its shape and has no reading and no place in the page's text
  (an empty line in the text shifted every slice after it by one line break). Each reading carries
  Kraken's confidence for the line (the mean of its characters'). `llm/kraken_runtime.recognize_to_geometry`.
  *Test:* `fichero-server/tests/unit/llm/test_kraken_line_reading_5500.py`.
- `source.reading.correct-a-line` — **[OK]** (#5499) correcting a line takes the segment and its new
  text, nothing more: `POST /api/segments/{segment_id}/correct` `{text}` (CLI `segments correct-line
  <segment_id> --text ...`, MCP `fichero_segments_correct_line`). It is one `representation.create`, the
  action every correction is, so it is audited and undone as one; the engine fills in the document, the
  reading it corrects (the one counting now, or the file's text a provisional reading still lives in)
  and the compare-and-set: when another reading counts than the one the caller read
  (`expected_counting_id`), it is refused with 409 and nothing is written. Who corrects is the caller,
  so a person's correction counts over a machine's reading. The `kind` defaults to `transcription`.
  Left: the bake-off counting a person's readings on a model's pass as ground truth (#4951).
  Pinned by `fichero-server/tests/unit/api/test_correct_a_line.py`. **App:** **Correct This Line…** on a
  line's menu in the Reader's Lines mode and the Segments and Order lists asks for the words (the reading
  that counts, filled in) and sends the line, the words and the reading shown as `expected_counting_id`
  (`SegmentService.correctLine`, `CorrectThisLine.swift`; `CorrectThisLineTests`); a refusal is said, never
  swallowed. Still owed: ⌘Z for it, which comes with the audited action (segment id plus text) the
  route's answer lacks an audit row for.
  **The answer is the reading (#5697):** a correction answers with the reading it made, without the
  line's outline (`source_anchor.polygon` and `shapes` empty): the correction did not change it, and the segment
  has it. An outline never keeps a point the same as the one before it, wherever an anchor is made or read.
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

Where the readers disagree (#5665; the engine half is worker C's, the app half built against the pinned shape)
- `source.disagree.route` — **[OK]** (#5665; built 2026-10-11, engine: `compare_readings.page_disagreement`; tested in
  `fichero-server/tests/unit/api/test_where_the_readers_disagree_5665.py`) `GET /api/documents/{page_id}/disagreement` answers, read-only:
  `{page_id, readers: [{id, label}], page_agreement, normalised_as, image_width, image_height,
  lines: [{segment_id, reference_reader, text, agreement,
  words: [{text, char_start, char_end, bbox, agreement, variants: [{text, readers}]}]}]}`.
  `image_width` / `image_height` are the pixel size of the image the boxes were measured on (amended
  2026-10-11 so the app scales `bbox` to whatever size it draws the page at; null when no word has a box).
  `readers` are the readings compared, one per reader or per sampled run (`id` stable for the page, `label`
  in words: "Kraken (CATMuS Medieval)", "Comma Qwen 0.8B, run 3"). Lines are in the page's reading order,
  each the reading of one line segment; `reference_reader` is its medoid reading, `text` that reading
  normalised. Words are the reference's words in order; `char_start` / `char_end` index `text`; `bbox` is
  `[x, y, width, height]` in the page image's pixels when the reading places the word, else null. A word's
  `agreement` is the share of readers whose aligned word is exactly its text (0–1; 1 is unanimous); its
  `variants` are every distinct aligned word, the reference's own included, most readers first, each with
  the reader ids that gave it (a reader with nothing aligned there gives ""). A line's `agreement` is the
  mean of its words'; `page_agreement` the mean over the page's words, null with no words. With fewer than
  two readings the answer is 200 with those readers, `lines` empty and `page_agreement` null (the app says
  so); an unknown page is 404. It never says accuracy (`source.disagree.agreement-not-accuracy`). The answer also
  carries `image_width` and `image_height`, the pixel size of the image the boxes are in (null when unknown). The
  readings compared are a line's machine transcriptions as written (a person's reading is a correction, not a
  reader); a reader is a model and the run it read under; a line read by fewer than two is left out. A word has a
  box when the reference reader read the line's word segments one for one.
- `source.disagree.normalised-first` — **[OK]** (#5665; the policy `catmus-as-written` in `transcription_accuracy`,
  also offered by the comparison route; tested as above) every reading is brought to one convention before it
  is compared, the line as written in the CATMuS sense (abbreviations unexpanded, slips kept, u/v and i/j
  folded, NFD), through the existing normalisation policies of `transcription_accuracy`; `normalised_as`
  names the convention compared at.
- `source.disagree.medoid-aligned` — **[OK]** (#5665; `compare_readings.medoid`, `aligned_words`; tested as above) per line, the reading with the least summed edit
  distance to the others is the reference; each other reading is aligned to it character by character
  (the comparison route's alignment, extended from two readings to N) and its words read off that alignment.
- `source.disagree.recipe-step` — **[OK]** (#5665; built 2026-10-11: the job in `recipes/jobs.py`, the Read stage,
  `start.disagreement_runs`: each run is `Read Lines (Kraken lines, vision model)` on the working pass's lines, its
  model the step's, else the recipe's line reader, at `temperature` through the transcribe tool; `readers` in its
  settings read once each; tested in `fichero-server/tests/unit/recipes/test_find_where_readers_disagree_step_5665.py`) "Find where the readers disagree" is a recipe step (job
  `find-where-readers-disagree`, stage Read): it reads the project's pages with the readers the step names, or
  one reader sampled N times at a temperature (5 at 0.7 by default), keeps every reading as a reading of the
  line (`source.reading.set`; none counts over another by being compared), and works out the disagreement.
- `source.disagree.built-in-with-two-readers` — **[OK]** (#5812, #5816; `start.disagreement_runs`; tested in
  `fichero-server/tests/unit/recipes/test_disagree_needs_no_model_5812.py`) when the plan already has two or more readers of the
  lines (a line reader and a Correct step, or two `readers` pinned on the step), "Find where the readers disagree" needs
  no model and has nothing to run: the disagreement is the line-by-line alignment of the readings the plan makes
  (`source.disagree.medoid-aligned`), worked out when a page is opened (`source.disagree.route` is read-only and keeps
  nothing; Review does not need it stored). The plan lists it under `built_in` (`{step, sentence}`: "built in: worked out
  when you open a page, from the readers above; there is nothing to run"), never under `skipped`, and Ready shows it under
  "Built in" in the plain style of any line (owner ruling: built in is never a warning; Swift test `RecipeRunVisibleTests`,
  `testReady_listsABuiltInStepAsBuiltIn_neverAmongTheSkipped`). No model is searched for, asked for, or warned about.
- `source.disagree.built-in-needs-second-reader` — **[PARTIAL]** (#5812 residue, owner blocker 2026-10-19; engine built, Ready row needs compile) the step is Fichero's own algorithm over the readers' readings, so the plan marks it `built_in` with no model: never "Fichero has no model for it yet", never Choose a model…, and Remove from Plan always works. It joins only when ticked. With two readers in the plan it says which (`compares`, "Compares Kraken with Apple Vision"); with one reader that can be sampled (a vision model) it keeps sampling it (`source.disagree.recipe-step`); with one that cannot (Kraken) it says `needs` "needs a second reader: tick one in Read" and Start skips it with that sentence, never blocking the plan. The Ready row reads `built_in`, `compares` and `needs` (not yet: Swift). *Test:* `fichero-server/tests/unit/recipes/test_disagree_needs_no_model_5812.py`. (Not yet written: the other built-in steps, #5812: sweep for the same wording.)
- `source.disagree.one-reader-says-which-to-add` — **[OK]** (#5812; same tests) with one reader in the plan the step
  cannot compare anything unless that reader is sampled. A vision reader is sampled (`source.disagree.recipe-step`); a reader
  that cannot be (Kraken) is not a reason to choose a model for THIS step: the line names the reader to add ("add a second
  reader, such as a Correct step or a second pinned reader") and offers vision readers only, never a text-model search.
- `source.recipe.every-job-declares-needs-a-model` — **[OK]** (#5812; `recipes/jobs.py` `Job.needs_a_model`, the one source `start.plan_start`
  reads in place of its former `_NO_MODEL_JOBS`; tested in `fichero-server/tests/unit/recipes/test_every_job_declares_a_model_need_5812.py`)
  each registered job says whether it needs a model, yes or no; a job registered without the answer is refused. A "no" job
  never gets a model row, a "has no model" skip, or a finder.
- `source.find.no-finder-for-no-model-jobs` — **[GAP]** (#5812) the Ready page and Set Up show no "Choose a model" row or
  finder for a job that needs none (the engine side is `source.recipe.every-job-declares-needs-a-model`; the pure-Swift check
  of the Ready rows is not written).
- `source.recipe.optional-steps-wait-to-be-asked` — **[OK]** (#5812, owner ruling 2026-10-19; `assemble._correct_left_off`, `assemble.assemble`;
  tested in `fichero-server/tests/unit/recipes/test_optional_steps_wait_to_be_asked_5812.py`) an optional step joins the plan
  only when the person ticks it or says yes: Correct (the Read page's "Have a second model check the reading?" or the step
  ticked), Find where the readers disagree (ticked), and cloud and training until asked. The answer drives the plan, never the plan
  the answer: an unanswered or unticked question gives a plan with no Correct and no disagree step, so no download is queued for
  either; a corrector already at hand does not put Correct in. Ready still says what turning it on would cost.
- `source.disagree.agreement-not-accuracy` — **[PARTIAL]** (#5665; the route's fields say agreement only; a checked
  line is not yet scored as accuracy) the figure is labelled agreement everywhere
  (route, lens, Inspector) unless a person checked the line, as `compare_readings` labels its score.
- `source.disagree.lens` — **[PARTIAL]** (#5665) the Reader's lens "Where the Readers Disagree" shows the page's
  lines, each word tinted by its agreement: plain at 1 (unanimous), yellow from 0.6 up to 1, red below 0.6;
  the page's figure, the readers compared and the convention head it, labelled agreement. **Built
  2026-10-11 (app):** `ReaderLens.disagreement`, `ReaderDisagreementView`, the tint `DisagreementTint`; read
  through `ReadingDisagreementStore`, whose source is the route through the generated client
  (`ReadingDisagreementStore.engine`; a refusal in the engine's words).
  Pinned by `fichero/Tests/Unit/general/Models/ReadingDisagreementTests.swift`. **Built 2026-10-11 (app):** a
  page whose words have boxes is drawn with each word's tint at its `bbox`, scaled from `image_width` /
  `image_height` (else the image's own size) to the size it is drawn at, the same tint mapping, a click
  opening the word's popover (`DisagreementOverlay`); a line with a word that has no box is listed as text
  below the page, as before. Wiring pinned by `fichero/Tests/Unit/general/Models/DisagreementWiringTests.swift`.
- `source.disagree.popover` — **[PARTIAL]** (#5665) clicking a word lists its variants, most readers first,
  each with the readers that gave it by label and how many of how many. **Built 2026-10-11 (app):**
  `DisagreementWordPopover`, its rows from `ReadingDisagreement.variantRows`; pinned as above.
- `source.disagree.inspector` — **[PARTIAL]** (#5665) the Inspector shows the page's agreement and each line's,
  as percentages labelled agreement, for a page read by two readers or more. **Built 2026-10-11 (app):**
  `ReadingAgreementInspectorSection`; pinned as above.
- `source.disagree.next-doubtful` — **[PARTIAL]** (#5665) Page › Next Doubtful Word (⌃⌘G; the Read menu became Page, #5652) and Previous Doubtful
  Word (⇧⌃⌘G) move the selection to the next or previous word below unanimous, in reading order (line by
  line, word by word), wrapping at the page's end; with none, they are disabled. **Built 2026-10-11 (app):**
  `ReadingDisagreement.doubtful(after:)` / `(before:)` and the Read menu's buttons; pinned as above.
- `source.disagree.fewer-than-two` — **[PARTIAL]** (#5665) with fewer than two readings the lens says so in one
  line and offers Read with Another Model…, which opens Set Up at the Read stage, where its model is chosen, and
  Find Where the Readers Disagree, which adds the step `find-where-readers-disagree` to the project's plan (the
  project's saved setup read first, the engine's plan saved only once it holds the step, else the engine's words)
  and opens Set Up on it for Start. **Built 2026-10-11 (app):** `RecipeSetupStore.addStep(job:)`; pinned by
  `fichero/Tests/Unit/general/Models/DisagreementWiringTests.swift`.

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
- `source.date.feast-days` — **[PARTIAL]** (#5542) a date written as a feast ("dia de San Juan de 1791", "Easter 1700",
  "Michaelmas 1650") is worked out onto the common count: a fixed feast on its day of the year, a movable feast as days
  after Easter (the computus, Gregorian, or the Julian Easter when the source kept the Julian calendar), and the answer
  keeps its reasoning (the rule, Easter's day, the calendar). The table is a data file (`recipes/seed/feast-days.yaml`:
  a name in any language is one more row, nothing named in code). A name that can mean two feasts ("San Juan": the
  Baptist, or the Evangelist) takes the commoner, names the other as an alternative and lowers the confidence; a name the
  table does not hold gives no date. Tests: `tests/unit/workflows/test_feast_days_5542.py`
  (`test_a_movable_feast_is_days_after_easter_in_the_calendar_of_the_source_5542`,
  `test_a_fixed_feast_is_its_day_and_keeps_its_reasoning_5542`,
  `test_a_name_that_can_mean_two_feasts_names_the_other_and_is_less_sure_5542`,
  `test_a_name_in_another_language_is_a_row_of_the_table_5542`,
  `test_a_feast_the_table_does_not_hold_gives_no_date_5542`, `test_the_table_is_sound_5542`). Owed: a page whose
  heading is a feast (`find_page_date` reads numeric and month headings only); regional calendars and the year's start
  at Easter or Lady Day (a January feast in a year that began in March is taken in the year written); the saints' days
  of a diocese; a row per language for the rest of the world's calendars.

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
