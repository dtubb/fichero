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
always outranks a machine's. Either way a machine reading is always *shown* as a machine's. Whether a reading was made by a person or a machine is set by the engine from how it
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
- `source.reading.set` — **[GAP]** (#4934) a segment can have many readings; adding one never changes another.
- `source.reading.kinds` — **[GAP]** (#4934) a reading has a kind from an extendable list whose shipped defaults
  are: as written, expanded, normalised, as read aloud, transliteration, translation,
  description, coordinate, music, drawing.
- `source.reading.level-recorded` — **[GAP]** (#4934) every reading says how normalised it is; the level is
  never inferred or silently converted.
- `source.reading.read-from` — **[GAP]** (#4934) a reading names the image it was read from, and the reading it
  was made from if it has one.
- `source.reading.author-and-guideline` — **[GAP]** (#4934) a reading names its author (person, or model and
  run) and any guideline it follows.
- `source.reading.corrections-are-new` — **[GAP]** (#4934) a correction is a new reading that names what it
  corrects.
- `source.reading.equal-alternatives` — **[GAP]** (#4934) several readings of one kind can stand as equally
  valid, apart from a machine's ranked guesses.
- `source.reading.chosen-is-worked-out` — **[GAP]** (#4934) "which reading counts" is worked out from recorded
  human choices, who made each reading, how recent it is and the project's rule; it is never a
  flag stored on a reading, so changing the project's rule rewrites nothing.
- `source.reading.chosen-follows-project-rule` — **[GAP]** (#4934) in a strict project only a person chooses the
  reading that counts; in a relaxed project the newest counts and a person's outranks a
  machine's; a new project is strict; the choice is recorded and changing it rewrites nothing.
- `source.reading.machine-is-labelled` — **[GAP]** (#4934) a machine's reading is always shown as a machine's,
  and in a strict project as unchosen; exports mark it machine-made.
- `source.reading.maker-set-by-engine` — **[GAP]** (#4934) whether a person or a machine made a reading or a pass
  is the existing engine-set `ProvenanceKind` (the one claims use, → #4868, → #4869), not a new
  field, and is never claimed by the sender.
- `source.reading.stretch-names-its-reading` — **[GAP]** (#4934) a stretch of text names the exact reading it was
  measured on; when that reading is replaced it is carried over or reported unplaced.
- `source.reading.written-read-pair` — **[GAP]** (#4934) two readings can be joined as written and read, apart
  from error and correction.
- `source.reading.char-confidence-on-line` — **[GAP]** (#4934) per-character positions and confidence ride on a
  line's reading without character segments existing.

Hands and ink
- `source.hand.record` — **[GAP]** (#4935) a hand is a project record (name or label, date, place, style, notes)
  shared across sources.
- `source.hand.attributed` — **[GAP]** (#4935) a segment or campaign names its hand, with certainty and the
  author of the judgement; rival attributions coexist.
- `source.hand.not-provenance` — **[GAP]** (#4935) the Inspector shows who wrote the ink and who made the record
  as two separate facts.
- `source.campaign.ordered` — **[GAP]** (#4935) a source has ordered campaigns; segments belong to one; campaigns can
  share characters.
- `source.campaign.reading-says-which` — **[GAP]** (#4935) a reading can say which campaigns it takes in.

Sureness and damage
- `source.sure.three-kinds` — **[GAP]** (#4935) machine confidence, scholarly certainty and the state of the page
  are separate fields, never combined.
- `source.sure.editorial-facts` — **[GAP]** (#4935) unclear, lost, restored, supplied, superfluous, deleted and
  added are recorded as facts with extent, reason and author.
- `source.sure.brackets-are-drawn` — **[GAP]** (#4935) editorial signs are produced from those facts on display
  and export; they are never stored in a reading's text.

Letterforms
- `source.letterform.chain` — **[GAP]** (#4935) a character segment can name its character, its allograph and
  its scribe's form.
- `source.letterform.features` — **[GAP]** (#4935) a character segment can carry components and features from
  open lists.
- `source.letterform.compare` — **[GAP]** (#4935) marks of the same character can be gathered and compared
  across hands and sources.

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

To be filled at approval.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
