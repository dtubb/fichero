# Source Model — Languages, scripts and signs — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — part of the "How Fichero represents a source" section: how to say what
> language and script a passage is in, how writing direction works, and how to work with a
> script or a sign that no computer knows yet.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Behaviour ids below have **no tags yet**; everything
> is design unless the foundation's "What exists today" says otherwise. (Today: language is
> recorded once per document; script only on a reading; no direction anywhere; the detector
> knows English and Spanish.)

## Intent

Fichero should be as useful for a language with ten speakers, a script nobody has encoded,
or a text written in a spiral, as it is for printed English. That means language, script,
direction and the identity of a sign are recorded honestly at every level, and that "the
computer has no character for this" never stops the work.

`historical-text-normalization.md` owns what is *done* with text (normalising, dating,
matching names across scripts, detecting language, translating). This slice owns how
language, script, direction and signs are *recorded*.

## The design

### Three facts, never one field

- **Language** — a BCP 47 tag, *and* a Glottolog code where there is one. They are two
  different systems: Glottolog (open licence; covers dialects and under-resourced and
  Indigenous languages) is not part of BCP 47, so the record holds both, and one spelling of
  each is kept for the whole project. Where no registry knows the language, a private tag
  made in the project, with a name and notes. "Unknown" and "not yet looked at"
  are different values, as they already are for a document's language today.
- **Script** — ISO 15924, including its honest codes: no writing; undetermined; and the
  private-use codes for a script a project declares itself.
- **Encoding** — whether, and how far, the signs have Unicode characters: fully, partly, or
  not at all. No registry records this; it is Fichero's own third fact. Never assumed.

One language can use several scripts. One page can hold several of each. A Japanese page
holds Chinese characters and two syllabaries at once.

### It cascades

Language, script and direction are set at any level and **inherited downward** until
overridden: app default, project, folder, group of pages, page, region, line, word,
character. A gloss in Basque inside a Latin page overrides for that gloss only. Every value
shown says where it came from ("from the page"; "set here"). This is the ratified cascade
already recorded in the normalization spec; this is where it lives.

A reading can also state its own language and script, which wins for that reading (a
translation is in another language than the ink).

### Direction

Direction is a property of a segment: left to right; right to left; top to bottom; bottom to
top; **alternating** (each line reverses); **follows the baseline** (a spiral, a seal, a
coastline). For columns and lines there is also the direction in which *they* succeed each
other (vertical columns running right to left). Mixed direction inside one line (Arabic with
numerals) follows the Unicode bidirectional rules, and the stored text is always in reading
order, never in display order.

The Reader lays text out in its direction. Where it cannot lay a direction out as running
text (a spiral), it shows the reading in reading order and shows the shape on the image.

### Signs without characters

A **sign** is the unit of a script. Most signs are Unicode characters. When one is not, it is
a **declared sign**, which needs only:

- a name or label;
- a picture, cut from a real segment on a real page.

and may have: notes; a sound or meaning; **references to sign lists** (the authority and the
number in its list: a catalogue of Maya glyphs, a cuneiform sign list, a project's own); a
private-use code point (MUFI's, where MUFI has one); a description of how it is built from
parts; a font that draws it.

A sign's identity can therefore be "number 561 in this catalogue" with no code point at all.
Unicode is one authority among several.

Declared signs live in a **sign list** owned by a project. A reading's text can mix ordinary
characters and declared signs. A whole unencoded script can be built up this way, sign by
sign, from its own sources: each new sign is declared from the page it was first met on, and
every later instance points to it. The list can be exported and shared, and is the evidence
needed for an encoding proposal.

**Variant forms** of an encoded character (the many forms of one Chinese character; a
long s) are recorded the same way: the character, plus which variant.

### What can be done with declared signs

Everything that can be done with characters: transcribe (pick from the list, or draw a box on
the page and say "this one again"); search (by sign, by catalogue number); compare (all
instances of one sign, side by side, across hands and sources); show (the sign's picture in
line in the Reader where no font has it); export (TEI's declared glyphs; elsewhere a
placeholder plus a report of what was substituted); train (a recogniser can learn declared
signs as classes).

### Fonts

The font a reading needs is recorded with it. A project can carry its own fonts for its
scripts. If a needed font is missing, Fichero says so and shows sign pictures or a fallback;
it never shows empty boxes without explanation.

### Input

Transcribing an unfamiliar script should not depend on the Mac having a keyboard for it: a
palette of the project's signs and of a script's characters, searchable by name and by
catalogue number, inserts into a reading.

### Side by side

Because language, script, signs and letterforms sit on segments, two sources can be compared
by character: a Japanese page beside a Chinese one; the same sign in two hands; every
instance of one abbreviation in a codex.

## Behaviors (ids proposed; untagged until approval)

Language and script
- `source.lang.three-facts` — language, script and encoding are recorded separately.
- `source.lang.registries` — language holds a BCP 47 tag and, separately, a Glottolog code;
  script is ISO 15924 including unwritten, undetermined and private-use; encoding (full, part,
  none) is recorded by Fichero.
- `source.lang.library-declared` — a project can declare a language or script no registry has.
- `source.lang.unknown-is-not-unexamined` — "unknown" and "not yet looked at" are different.
- `source.lang.cascade` — language and script inherit downward from app to character and can
  be overridden at any level (direction inherits the same way: see `source.dir.per-segment`).
- `source.lang.says-where-from` — a shown value says which level it came from.
- `source.lang.reading-overrides` — a reading's own language and script win for that reading.
- `source.lang.many-per-page` — one page can hold several languages and scripts at once.

Direction
- `source.dir.per-segment` — direction is set per segment: four straight directions,
  alternating, or follows the baseline; plus the direction in which lines or columns succeed.
- `source.dir.logical-order-stored` — stored text is in reading order; mixed direction in a
  line follows the Unicode bidirectional rules on display.
- `source.dir.reader-lays-out` — the Reader lays text out in its direction, and falls back to
  reading order plus the shape on the image where it cannot.

Signs
- `source.sign.declared` — a sign with no character can be declared with a name and a picture
  cut from a real page.
- `source.sign.list-authority` — a sign can be identified by an authority and a number in its
  list, with no code point.
- `source.sign.library-list` — declared signs live in a project's sign list, which can be
  exported and shared.
- `source.sign.in-readings` — a reading's text can mix characters and declared signs.
- `source.sign.variants` — a variant form of an encoded character is recorded as the character
  plus the variant.
- `source.sign.search-compare` — declared signs can be searched, and all instances of one
  gathered and compared.
- `source.sign.shown-as-picture` — where no font has a sign, its picture is shown in line.
- `source.sign.export-honest` — exports carry declared signs where the format can (TEI) and
  report substitutions where it cannot.

Fonts and input
- `source.font.recorded` — a reading records the font it needs; a project can carry fonts.
- `source.font.missing-is-said` — a missing font is reported; no unexplained empty boxes.
- `source.input.palette` — a searchable palette of a script's characters and the project's
  signs inserts into a reading.

Comparison
- `source.compare.by-character` — two sources can be set side by side and compared by
  character, sign or letterform.

## Test matrix

To be filled at approval.

## Open questions

See `source-model.md`. The ones that belong here: is there a particular Indigenous-language
source to use beside Glottolog; does Fichero ship fonts, or only let a project add them.
