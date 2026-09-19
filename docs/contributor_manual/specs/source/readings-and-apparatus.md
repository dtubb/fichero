# Source Model — Readings and the scholar's apparatus — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — part of the "How Fichero represents a source" section: that one patch of ink
> can carry several readings, which one counts, and how hands, ink layers, damage and a
> researcher's own notes are recorded.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Behaviour ids below have **no tags yet**; everything
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

- its **text** (which may include declared glyphs: see `languages-scripts-glyphs.md`);
- its **kind**: *as written* (letter for letter), *expanded* (abbreviations opened),
  *normalised* (spelling regularised), *as read aloud* (the qere; the Japanese reading of a
  Chinese text), *transliteration*, *translation*, *description* (what a picture shows),
  *coordinate* (for a map control point). A library can add kinds;
- **how normalised it is**, as a named level. Levels cannot be reliably converted into each
  other, so the level is recorded, never assumed;
- its **language and script**;
- **what it was read from**: which image of the page, and, for a reading made from another
  reading (a translation, a normalisation), which one;
- its **author**: a person, or a model and run;
- **how sure the machine was**, if a machine made it (for the whole reading and, where the
  recogniser gives it, for each character, with the character positions along the line, kept
  on the reading without making character segments);
- **the guideline it follows**, if any (a transcription convention);
- when it was made.

Readings are never edited in place. A correction is a new reading (or a revision of a human
one) that names what it corrects.

### Several readings can all be right

An undotted Arabic word that can honestly be read three ways has three readings of the same
kind, side by side, each with the scholar's certainty. This is different from a machine's
ranked guesses. The model holds both, and does not mix them up.

### Which reading counts

For each kind, one reading is **the chosen one**: what the Reader shows, what search indexes,
what export writes. A person can choose it. If nobody has, the rule in the foundation's open
questions decides. The choice is itself recorded, with who and when, and changing it rewrites
nothing.

### Written and read

Some ink has two true forms: the abbreviation and its expansion; the word as written and the
word to be read aloud; the Chinese sentence and its reading in Japanese. These are a **pair**
of readings joined as *written* and *read*, not an error and its correction. Corrections
exist too (the scribe wrote it wrong; the editor emends), and are marked as corrections.

### Hands

A **hand** is who put the ink on the page: a named scribe, or "hand B", with a date or period,
a place, a script style, and notes. A hand is a record in the library, shared across sources,
so "everything in hand B" can be asked. A segment, or an ink layer of a segment, can name its
hand, with certainty and the author of that judgement. Several scholars can disagree.

A hand is not provenance. Provenance says who made the *record* (a model, a person, a
workflow run). Both are kept, separately, always.

### Ink layers

One patch of page can carry several **campaigns of writing**: the main ink; the rubric; vowel
marks added a century later; reading-marks pressed in with a stylus; the under-text of a
palimpsest; a modern librarian's pencil. An ink layer has a name, an order (what lies over
what), and optionally a hand and a date. Segments belong to an ink layer. Two ink layers can
share the same characters (the consonants and their later vowels), and a reading can say
which ink layers it takes in.

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

Notes, highlights, stars and tags go on any segment at any level, exactly as they go on a
document: the same note, star and tag, not a second kind. In addition:

- marks live in **named sets with an author**, so two researchers' annotations of one source
  can overlap, disagree and be shown separately or together;
- one mark can cover **several segments** that are not next to each other;
- a mark can point at a stretch of a reading as well as at a segment.

### Descriptions of pictures

A picture, seal, stamp, diagram or map segment has readings of kind *description* (what it
shows; alt text) and may have **classifications** (a seal; a map; music; a portrait), each
with its author and, if a machine made it, its confidence. A description is a reading like
any other: several can exist, one is chosen, none is overwritten.

## Behaviors (ids proposed; untagged until approval)

Readings
- `source.reading.set` — a segment can have many readings; adding one never changes another.
- `source.reading.kinds` — a reading has a kind from an extendable list (as written, expanded,
  normalised, as read aloud, transliteration, translation, description, coordinate).
- `source.reading.level-recorded` — every reading says how normalised it is; the level is
  never inferred or silently converted.
- `source.reading.read-from` — a reading names the image it was read from, and the reading it
  was made from if it has one.
- `source.reading.author-and-guideline` — a reading names its author (person, or model and
  run) and any guideline it follows.
- `source.reading.corrections-are-new` — a correction is a new reading that names what it
  corrects.
- `source.reading.equal-alternatives` — several readings of one kind can stand as equally
  valid, apart from a machine's ranked guesses.
- `source.reading.chosen` — for each kind one reading is the chosen one; the choice is
  recorded and changing it rewrites nothing.
- `source.reading.written-read-pair` — two readings can be joined as written and read, apart
  from error and correction.
- `source.reading.char-confidence-on-line` — per-character positions and confidence ride on a
  line's reading without character segments existing.

Hands and ink
- `source.hand.record` — a hand is a library record (name or label, date, place, style, notes)
  shared across sources.
- `source.hand.attributed` — a segment or ink layer names its hand, with certainty and the
  author of the judgement; rival attributions coexist.
- `source.hand.not-provenance` — who wrote the ink and who made the record are separate and
  both always shown.
- `source.ink.layers` — a source has ordered ink layers; segments belong to one; layers can
  share characters.
- `source.ink.reading-says-which` — a reading can say which ink layers it takes in.

Sureness and damage
- `source.sure.three-kinds` — machine confidence, scholarly certainty and the state of the page
  are separate fields, never combined.
- `source.sure.editorial-facts` — unclear, lost, restored, supplied, superfluous, deleted and
  added are recorded as facts with extent, reason and author.
- `source.sure.brackets-are-drawn` — editorial signs are produced from those facts on display
  and export; they are never stored in a reading's text.

Letterforms
- `source.letterform.chain` — a character segment can be described as character, allograph,
  scribe's form and mark, with components and features from open lists.
- `source.letterform.compare` — marks of the same character can be gathered and compared
  across hands and sources.

Marks and descriptions
- `source.mark.any-level` — notes, highlights, stars and tags go on any segment, using the same
  records a document uses.
- `source.mark.authored-sets` — marks live in named, authored sets that can be shown apart or
  together.
- `source.mark.many-segments` — one mark can cover several separate segments, or a stretch of
  a reading.
- `source.picture.described` — a non-text segment has descriptions and classifications as
  readings, with authors; one is chosen.

## Test matrix

To be filled at approval.

## Open questions

See `source-model.md`. The ones that belong here: which reading counts when nobody has
chosen; how many normalisation levels, and their names.
