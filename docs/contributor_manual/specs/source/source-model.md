# Source Model — how a source is represented — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — the user manual needs a "How Fichero represents a source" section, written for
> a researcher: a source is addressable from a group of pages down to a single stroke; every
> reading, translation, note and claim points at the exact place it came from; and the whole
> thing can leave as standard XML and come back.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — first capture of the maintainer's intent,
> 2026-09-19. Nothing here is approved. No behaviour ids yet: they are written once the intent
> below is ruled, and once the milestone exists.**
> Tags (when behaviours arrive): **[OK]** built and tested · **[PARTIAL]** built, partly proven
> · **[GAP]** intended, never built · **[BROKEN]** code contradicts the rule.
>
> The folder name `source/` and the name "source model" are PROVISIONAL (see Open questions).

## Intent (the design)

Everything Fichero knows comes from somewhere on a source. A transcription, a translation, a
note, a workflow result, a knowledge-graph claim or entity: each one must be able to point at
the exact place it came from. Not just "this page", and not just "this run of characters in a
text editor", but the ink itself, as finely as the work needs.

This is more fundamental than the knowledge graph. The knowledge graph, transcription,
workflows, search and export all stand on it. So it gets its own spec area, and one model.

The goal is to represent a page properly, once, so that Fichero is truly useful for:

- **under-resourced languages and scripts**, including ones with poor or no model support;
- **writing in any direction**: left-to-right, right-to-left, vertical, and mixed on one page;
- **annotation**: glosses, marginalia, interlinear notes, commentary that answers commentary.

### One ladder, every level addressable

A source is addressable at every level of one ladder:

```
group of pages  >  page  >  region  >  line or column  >  word  >  character  >  stroke
```

- A **group of pages** can be a document, a gathering, a letter and its reply, a legal case
  spread over several documents.
- A **region** is any area of a page: a text block, a margin, a gloss, an illustration, a
  stave of music, a map inset.
- A **line or column** carries its own writing direction. A line may be bidirectional.
- A **character** may be a Latin letter, a Chinese or Korean character, or a sign with no
  Unicode code point at all.
- Any level can be skipped. A page may have regions and lines but no words yet. Finer levels
  are added later without disturbing coarser ones.

Every level is the same kind of thing: a **segment**. One primitive, not seven.

### What every segment carries

At every level, a segment can carry:

- **Location** — where it is on the page. A **polygon**, not only a box. A line also has its
  baseline. A box is just the simplest polygon.
- **Direction and reading order** — which way the writing runs, and where this segment sits in
  the order of reading. A page may have more than one reading order (the main text; the
  commentary around it).
- **Language and script** — per segment, inherited from above unless overridden. One page can
  hold several languages and several scripts. Language, script and encoding are three separate
  facts (see "Language, script, encoding and fonts" below).
- **Readings** — many transcriptions of the same ink (a model's, another model's, a person's
  correction), each kept, none overwritten. One of them counts as the transcription.
- **Translations** — many, each tied to the reading it translates.
- **Statements** — knowledge-graph claims and entities attach to a segment at any level, and it
  is easy to go both ways: from a segment to what is said about it, from a statement to its ink.
- **A description** — a segment that is a picture, a diagram, a seal or a stamp carries a
  description of what it shows (alt text), with the same provenance as any reading.
- **Links** — to other segments (this gloss comments on that word; this marginal note answers
  that marginal note), to entities and claims, and to outside authorities.
- **Versions and provenance** — who or what made it, when, from what, and why. Append-only.
- **Its image** — the crop of just this segment, easy to get at any level.

### Language, script, encoding and fonts

Three separate facts, never collapsed into one "language" field:

- **Language** — identified from a proper registry that covers under-resourced and Indigenous
  languages, not only the major ones. (The staged plan already names the candidates:
  Glottolog, CLDR, and the loove coverage tiers. Which registry is the authority is an open
  question below.)
- **Script** — the writing system (ISO 15924). One language may be written in several scripts;
  one script serves many languages. A Japanese page holds Chinese-origin characters and two
  syllabaries at once.
- **Encoding** — which Unicode characters, if any. Some scripts have only part of what they need
  in Unicode. Some have none. Some languages have no settled script at all. The model must not
  assume a code point exists.

And one practical need: **fonts**. A script may need a special font to display at all. The font
a reading needs is recorded with it, so the Reader and an export can show it properly.

Because all of this is on the segment, two sources can be put **side by side and compared by
character**: a Japanese page beside a Chinese one, the same sign in two hands.

### Layers

A page holds several **layers** of segments at once: the layout a model proposed, the layout a
person corrected, a layer of glosses, a layer of illustrations. Layers can be shown, hidden and
compared. They do not overwrite each other.

### Edited on the page

Segments are edited directly on the image, in the Preview (the source pane), and nowhere else.
Full editing, not a viewer with a few handles:

- draw a new segment (box or polygon); move it; reshape it point by point;
- **merge** segments, **split** one, **combine** lines into a region, **delete**;
- change a segment's level, layer, reading order, direction, language or script;
- work on many regions and several layers at once.

Every edit is one audited, reversible action. Nothing is rewritten by batch.

### One store, many uses

The same stored segments serve every use. There is no second copy for any of them:

- the **Preview** draws and edits them;
- the **Reader** shows their readings, in the right direction and font;
- the **Inspector** shows one segment's readings, versions and statements;
- an **agent** (MCP) and the **command line** read and write them;
- **training** takes them out as crops plus readings;
- **export** writes them as standard files.

### Hard cases the model must handle without special pleading

These are the test of the design. If one of them needs a special case, the model is wrong.

- A medieval page with a main text, **interlinear glosses** above the words, and
  **marginalia** around it.
- **Commentary in conversation**: margin notes that answer other margin notes, back and forth,
  in the manner of a Talmud page.
- A page mixing a **right-to-left** script with a left-to-right one, inside one line.
- **Vertical** text (Chinese, Korean, Japanese, Mongolian), where the "line" is a column.
- A script with **no Unicode encoding**: the segment is anchored to the image and still
  transcribable, searchable by shape, and exportable.
- A knowledge-graph **claim tied to a single character or word**, not just to a page.
- A page with **pictures** on it: each picture is a segment, with a description, and can be
  pulled out on its own.
- **Music** on a page (staves, neumes), and **maps** (a region of a map is a segment).

### Easy to move around in

The ladder is also a way to navigate: up to the parent, down to the children, to the next and
previous segment in reading order, and across a link (from a gloss to the word it glosses).
The same moves work in the app, for an agent over MCP, and on the command line.

### Standards in and out, validated

The model must be able to hold everything these formats can say, import them, and export
them, **with validation against each format's schema** (an export that does not validate is a
failed export, reported as such):

- **PageXML** and **ALTO XML** — layout, lines, words, glyphs, polygons, reading order.
- **TEI XML** — editions, zones and surfaces, glosses, apparatus, correspondence.
- **MEI** — music encoding.
- **Object-detection training formats** (the YOLO family) — regions and classes for training a
  layout detector.
- **SVG** and **PDF** — a page you can look at: the image with its segments and readings laid
  over it (SVG), or a searchable PDF with the text in place. Export only.
- Others as needed. A new format is a new mapping, not a new model.

### A columnar format for training

Segments, their images and their readings also export to, and import from, a columnar
(Arrow / Parquet) dataset, so a corpus can be sent for fine-tuning.

The loop this enables: read a few pages with a large model (a vision-language model), correct
them by hand, export the word- or character-level segments with their crops and readings, and
use that to fine-tune a small recogniser (Kraken) for that hand or script, and a small layout
detector (the YOLO family) for that kind of page. Then run the small models on the rest,
locally.

## What exists today (checked on disk, 2026-09-19)

- VERIFIED: the Kraken segmenter already returns, for each line, a **baseline and a polygon**,
  not just a box (`fichero-server/src/fichero_server/llm/kraken_runtime.py`, the line records
  built around lines 430–436 and 572–581).
- VERIFIED by search: the engine source has **no ALTO or PageXML** import or export code.
- VERIFIED by search: the engine source has **no stored writing direction**; "reading order"
  appears only as a free-text answer in the layout tool's prompt
  (`workflows/tools/layout.py`) and as a geometry re-sort in `workflows/tools/vision_base.py`.
- NOT YET CHECKED: how segments are stored today, what the app's overlay reads, what the
  Parquet export already carries, and how a claim's source pointer is stored. These are read
  before any behaviour below is tagged.

## Prior art (we adopt, we do not invent)

- **W3C Web Annotation** and **Media Fragments** — how to point at part of a thing (a polygon
  on an image, a span of text, a span of time). This is the pointer.
- **IIIF** — pages as canvases, regions by coordinates, crops by URL. This is how a segment's
  image is fetched.
- **PageXML / ALTO** — the layout ladder (region, line, word, glyph), polygons, baselines,
  reading order. This is the geometry.
- **TEI** — surfaces and zones, glosses and additions, editions, apparatus. This is the
  scholarly layer.
- **MEI** — the same for music.
- **Unicode bidirectional algorithm, CLDR, ISO 15924** — direction and script.
- **Kraken / eScriptorium / Transkribus** — existing practice for baselines, polygons, training
  from corrected ground truth.
- **Hugging Face `datasets` (Arrow / Parquet)** — the training-corpus convention.

## How the existing specs fit under this one

This spec becomes the one home for the shared ideas. The others keep their own work and point
here. (They still live in `specs/kg/` for now; they move into this folder in one late step.)

- `kg/archival-data-model-plan.md` — the staged plan. Its primitive (the segment), its four
  slots and its delivery contract move here; it stays as the roadmap.
- `kg/segment-representations.md` — the first slice: read a segment's crop and text, in the
  Inspector, over MCP and CLI, exported.
- `kg/historical-text-normalization.md` — the text layer: normalization, dates, name variants
  across scripts, language detection, translation, transliteration.

## The delivery rule (unchanged, stated once here)

A capability is done only across the whole spine: **engine → app → agent (MCP) and command
line → tested → exportable.** Anything less is not done.

## Behaviors

None yet. They are written, with ids, tags and issues, once the intent above is ruled and the
milestone exists.

## Open questions for the creative director

1. **The name.** What is this area called: the source model, the page model, the archival
   model, or another word? (The folder is provisionally `source/`.)
2. **One segment kind or named levels?** Is every level just "a segment with a level", or do
   page, region, line, word and character each get their own name in the app?
3. **Reading order.** When a page has a main text and a commentary, is that two reading orders
   on one page, or one order plus links?
4. **Which reading counts.** When a segment has several readings, who decides which one is the
   transcription: the newest, the newest human one, or an explicit choice?
5. **No-Unicode scripts.** What does a researcher type for a sign that has no code point: a
   private label, a picture of the sign, or both?
6. **First format.** Which standard is imported and exported first: PageXML, ALTO or TEI?
7. **The columnar format.** Parquet written through the existing export path, or Arrow files
   directly? (The exporter spec already rules Parquet through DuckDB for library export.)
8. **The language authority.** Which registry names a language: Glottolog, ISO 639-3, the
   Indigenous-language source the maintainer has in mind (name it here), or several with one
   as the authority?
9. **Fonts.** Does Fichero ship fonts for some scripts, let a researcher add their own to a
   library, or both?
10. **The first slice.** What should a researcher be able to do first with this, in the next
   release?
