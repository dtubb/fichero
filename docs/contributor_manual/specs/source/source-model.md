# Source Model — how a source is represented — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — the user manual needs a "How Fichero represents a source" section, written for
> a researcher: a source is addressable from a group of pages down to a single stroke; every
> reading, translation, note and claim points at the exact place it came from; and the whole
> thing can leave as standard XML and come back.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — second pass, 2026-09-19: the maintainer's intent,
> plus a survey of the standards and of what working philologists record, plus a read of the
> code on disk. Nothing here is approved. No behaviour ids yet: they are written once the
> intent is ruled and the milestone exists.**
> Tags (when behaviours arrive): **[OK]** built and tested · **[PARTIAL]** built, partly proven
> · **[GAP]** intended, never built · **[BROKEN]** code contradicts the rule.
>
> The folder name `source/` and the name "source model" are PROVISIONAL (see Open questions).
> Everything under "The design" is PROPOSED until the maintainer rules it.

## Intent (the design)

Everything Fichero knows comes from somewhere on a source. A transcription, a translation, a
note, a workflow result, a knowledge-graph claim or entity: each one must be able to point at
the exact place it came from. Not just "this page", and not just "this run of characters in a
text editor", but the ink itself, as finely as the work needs.

This is more fundamental than the knowledge graph. The knowledge graph, transcription,
workflows, search and export all stand on it. So it gets its own spec area, and one model.
The segments described here are the sources the knowledge-graph layer points to.

The goal is to represent a page properly, once, so that Fichero is truly useful for:

- **under-resourced languages and scripts**, including ones with poor or no model support, no
  settled script, or no place in Unicode;
- **writing in any direction**: left-to-right, right-to-left, vertical, mixed on one page or in
  one line, and writing that follows a curve;
- **annotation**: glosses, interlinear notes, marginalia, commentary that answers commentary,
  by several authors over several centuries on the same page.

The maintainer does not want to decide, case by case, what a palaeographer of tenth-century
Spain needs versus one of early Arabic or of Aramaic. The model must be general enough that
each of them finds what they need already there. The worked examples below are the test.

## What the field already does (survey, 2026-09-19)

We adopt; we do not invent. This is what each standard can and cannot hold. It sets what our
model must carry, and tells us honestly what each export will lose. Sources are listed at the
end.

| | Holds well | Cannot hold |
|---|---|---|
| **PageXML** (2019 schema) | region > line > word > glyph; polygons; baselines; one reading order (nested groups); direction in four values (left-right, right-left, top-bottom, bottom-top); language and script at every level; several ranked readings per segment; region types (marginalia, footnote, catch-word…); picture, music, map, table regions | scribal hands; editorial marks (damage, restoration); more than one reading order; links richer than "link" or "join"; signs with no Unicode |
| **ALTO** (4.4, 2023) | block > line > string > glyph; polygons; baselines; language; direction and reading order (since 4.3); alternatives and confidence per word and character; tags; processing history | hands; editorial marks; typed links; several reading orders; signs with no Unicode |
| **TEI** (P5) | page surfaces and polygon zones linked to the text both ways; glosses and additions with their place (above, margin, interlinear); marks that reorder reading; scribal hands and changes of hand; editorial layers (abbreviation and expansion, original and regularised, error and correction); unclear, gap, supplied, damaged, deleted; critical apparatus; signs with no Unicode (a declared glyph with a picture); free links between anything | direction is only a style hint; geometry and reading order are weaker than PageXML |
| **MEI** (music) | page surfaces and zones linked to notes; neumes | polygons: its zones are rectangles |
| **W3C Web Annotation** + **IIIF** | pointing at anything: a rectangle, a polygon, a text span, a time span, one inside another; a note that replies to a note; granularity levels page, block, paragraph, line, word, glyph | it is a pointer, not a transcription model. IIIF image crops are rectangles only |
| **YOLO** (layout training) | plain text, not XML: one class and one box or polygon per object | everything else: no text, no hierarchy, no order |
| **Kraken** training | trains from ALTO, PageXML, or line image plus text; also a compiled Arrow dataset. Learns lines (baseline plus polygon) and typed regions; handles right-to-left and vertical | works at the **line**; it does not train on cut-out characters. It has no YOLO segmenter |

Three conclusions:

1. **No one format holds everything.** PageXML and ALTO are the geometry formats. TEI is the
   scholarly format. Our model must be richer than any of them, and each export is a
   projection that says plainly what it left out.
2. **The vocabulary for region and line types already exists**: SegmOnto (main zone, margin
   text zone, graphic zone, music zone, seal zone, stamp zone, damage zone, numbering zone…;
   default line, interlinear line, heading line, music line…). It is what Kraken and
   eScriptorium train on. We adopt it as the default, extensible.
3. **Language, script and encoding have registries**: BCP 47 tags for language, ISO 15924 for
   script — including codes for "unwritten", "undetermined", "not in Unicode", and
   private-use scripts — and Glottolog (open licence, covers dialects and under-resourced
   languages). Medievalists already share private-use characters through MUFI.

## What working philologists record (the worked examples)

These are the test of the design. If one of them needs a special case, the model is wrong.

1. **Tenth-century Spain — the San Millán glosses.** A Latin codex in Visigothic script. Later
   readers added glosses between the lines and in the margins, in Latin, in early Romance and
   in Basque. Some glosses are single letters written above the words to tell the reader what
   order to read the Latin in. There are abbreviations to expand, and music signs (neumes)
   nobody can now turn into pitches. *Needs:* glosses in another language than the text they
   gloss; a gloss tied to the word it glosses; **a second reading order** laid over the first;
   written form versus expanded form; a music segment with no transcription; several hands.
2. **Early Arabic.** The scribe wrote the bare letter shapes. Dots that tell letters apart, and
   vowel marks, were often added later, in another ink, by another hand. One undotted word can
   honestly be read several ways. Margins carry collation notes, reading certificates,
   ownership and endowment notes. Right-to-left text with left-to-right numerals inside it.
   *Needs:* **ink layers** over the same characters, each with its own hand and date; **several
   equally valid readings**, not one best guess; mixed direction inside a line; typed marginal
   notes.
3. **Aramaic, Syriac, Hebrew.** Papyri and potsherds with damage and gaps. Syriac in three
   scripts with two competing vowel systems. Incantation bowls with the text in a **spiral**.
   Palimpsests, where the under-text only shows under special light, so one page has
   **several images**. The Masoretic margin notes. And *ketiv / qere*: the word as written and
   the word as it is to be read, both correct. *Needs:* direction that follows a curved
   baseline; a reading tied to the image it was read from; damage and restoration recorded as
   facts (so the editor's brackets are drawn from the data, not typed into the text);
   **written versus read** as a pair.
4. **Japan and Korea reading Chinese.** A Chinese text with small marks added so it can be read
   aloud in Japanese: marks that reorder the words, marks that add endings, sometimes pressed
   in with a stylus, not inked. Korean has the same practice. Small pronunciation glosses
   beside characters. Vertical columns read right to left. Variant forms of one character.
   Seals. *Needs:* the second reading order again; a gloss subordinate to one character;
   vertical direction; **the identity of a character form** apart from its code point; a seal
   as a picture segment with text inside it.
5. **The Talmud page, the glossed Bible, glossed law.** A central text, with commentaries
   wrapped around it, each quoting the words it comments on, and later commentaries commenting
   on the commentaries. *Needs:* **typed links from segment to segment, to any depth** ("this
   comments on that", "this answers that").
6. **Writing that is not in lines.** Lines that alternate direction; text round a seal or coin;
   names following a coastline on a map; tables read across or down. *Needs:* direction per
   segment, including "follows the baseline".
7. **Pictures, seals, stamps, diagrams, maps on a page.** *Needs:* a segment that is not text,
   with a description of what it shows, that can be pulled out on its own.
8. **A claim about one word.** A knowledge-graph claim that rests on a single word, or a single
   character. *Needs:* the claim points at a segment, and survives the page being
   re-segmented or re-transcribed.

Things a palaeographer records that sit **above** the page — the quire, the ruling pattern,
the part of a codex made at one time — mean the ladder must reach above the page too.

## The design (proposed)

### One ladder, every level a segment

```
collection / codex unit  >  group of pages  >  page  >  region  >  line or column
                                                     >  word  >  character  >  stroke
```

- Every level is the same kind of thing: a **segment**, with a **kind**. One primitive.
- A segment that is not text is a peer of one that is: picture, music, seal, stamp, table,
  diagram, map, damage, blank.
- Any level can be skipped. Finer levels are added later without disturbing coarser ones.
- Kinds and types come from SegmOnto by default, and a project can add its own.
- **A segment has a lasting identity.** It keeps the same id when it is moved, reshaped,
  re-read or re-transcribed. This is the one capability everything else depends on, and it
  does not exist today (see "What exists today").

### What a segment carries

- **Where** — a polygon (a box is the simplest polygon); for a line, its baseline, which may
  curve; and **which image of the page** it was measured on. A page can have several images
  (original, enhanced, split, ultraviolet). Coordinates are fractions of that image, never raw
  pixels.
- **Direction** — left-to-right, right-to-left, top-to-bottom, bottom-to-top, alternating, or
  follows-the-baseline. Set per segment, inherited from above unless overridden.
- **Language, script, encoding** — three separate facts (below), inherited unless overridden.
- **Readings** — a set, not a string. Each reading has a kind (as written, expanded,
  normalised, as read aloud, translation, machine guess), a language and script, a certainty,
  who or what made it, and when. Several readings can be equally valid. One is marked as
  *the* transcription.
- **Written versus read** — a first-class pair, not a correction: the abbreviation and its
  expansion, the ketiv and the qere, the Chinese text and its Japanese reading.
- **Hand** — who wrote the ink: a named scribe or "hand B", with date and notes. This is
  separate from provenance, which is who made the *record* (a model, a person, a workflow).
- **Ink layer** — main ink, rubric, later vowel marks, stylus marks, under-text. Several layers
  can sit over the same characters, each with its own hand.
- **Certainty and damage** — recorded as facts (unclear, lost, restored by the editor, supplied,
  deleted by the scribe), with a reason and who judged it. Editorial brackets are drawn from
  these facts, never typed into the text.
- **Links** — typed, directional, from segment to segment, to any depth: glosses, expands,
  reorders, comments on, answers, quotes, continues, same as.
- **Statements** — knowledge-graph claims and entities attach to the segment's id, and it is
  easy to go both ways.
- **A description** — for a picture, seal, stamp or diagram: what it shows (alt text), with the
  same provenance as any reading.
- **Its image** — the crop of just this segment, cut to its polygon, available at every level.
- **Versions** — every change to any of the above is a new version of *that segment*. Nothing
  is overwritten. A segment's history can be read and restored on its own, without touching
  the rest of the page.

### Reading orders: more than one, and named

A page has one or more **named reading orders**, each a sequence of segments: the order as
written; the order the reading-marks impose; the order of a commentary. Each has its own
provenance and certainty. Reading orders answer "what comes next". Links answer "what is this
about". Examples 1 and 4 need the first; example 5 needs the second; a real page needs both.

### Language, script, encoding and fonts

Three separate facts, never collapsed into one "language" field:

- **Language** — a BCP 47 tag, with Glottolog behind it for under-resourced and Indigenous
  languages and for dialects. Private-use tags where no registry has the language.
- **Script** — ISO 15924, including its honest codes: unwritten, undetermined, not in Unicode,
  private use. One language can have several scripts; one page can have several of each.
- **Encoding** — which Unicode characters, if any. The model never assumes a code point exists.
  A sign with no code point is a **declared glyph**: a name, a picture cut from a real page,
  notes, and an optional private-use code (MUFI where it has one). Characters point at the
  declared glyph. Variant forms of one character are recorded the same way.

And **fonts**: the font a reading needs is recorded with it, so the Reader and an export can
show it.

Because all of this sits on the segment, two sources can be set **side by side and compared
by character**: a Japanese page beside a Chinese one; the same sign in two hands.

### Layers

A page holds several named **layers** of segments: the layout a model proposed, the layout a
person corrected, the glosses, the illustrations, each ink layer. Layers can be shown, hidden
and compared. They never overwrite each other.

### Edited on the page

Segments are edited directly on the image, in the Preview, and nowhere else. Full editing:

- draw a new segment (box or polygon); move it; reshape it point by point; redraw a baseline;
- **merge** segments, **split** one, **group** lines into a region, **delete**;
- change a segment's kind, layer, direction, language, script, hand, place in a reading order;
- draw a link from one segment to another;
- work on many segments and several layers at once.

Every edit is one audited, reversible action. Nothing is rewritten by batch.

### One store, many uses

The same stored segments serve every use. No use gets its own copy:

- the **Preview** draws and edits them;
- the **Reader** shows their readings, in the right direction, order and font;
- the **Inspector** shows one segment: readings, versions, hand, links, statements;
- an **agent** (MCP) and the **command line** read and write them;
- **training** takes them out as crops plus readings;
- **export** writes them as standard files.

Moving around is the same everywhere: up to the parent, down to the children, next and
previous in a reading order, across a link.

### Standards in and out, validated, honest about loss

- **In and out:** PageXML, ALTO, TEI, MEI. Every export is **validated against the format's
  schema**; one that does not validate is a failed export and says so.
- **Out only:** SVG (the image with polygons and text laid over it, in the right direction,
  with descriptions), searchable PDF (text in place, descriptions as alt text), YOLO-style
  training labels.
- **Every export reports what it could not carry** (for example: "PageXML: 2 reading orders
  reduced to 1; 14 hands dropped"). Nothing is lost silently.
- **Every import arrives as a new layer with its own provenance.** It never overwrites what is
  in the library.
- A new format is a new mapping, not a new model.

### Training: from a few corrected pages to a local model

Segments, crops and readings export to a columnar dataset (Arrow / Parquet, the Hugging Face
convention) and to the formats Kraken trains from.

The loop: a large vision model reads a few pages; a person corrects them on the page; Fichero
exports the corrected lines (crop, polygon, baseline, reading) and regions (polygon, type);
these fine-tune a small line recogniser (Kraken) for that hand or script, and a small layout
detector for that kind of page; the small models read the rest, locally.

Two facts from the survey shape this. Kraken learns from **lines**, not from cut-out
characters, so the unit of training is the corrected line. And a training set is a
**projection**: it keeps shape, type and text, and drops hands, links, order and certainty. It
is regenerated from the library whenever needed. It is never the record.

## What exists today (read on disk, 2026-09-19; VERIFIED unless marked)

Good foundations, which this design must grow from and not duplicate:

- **One anchor type already exists.** `SourceAnchor` (`fichero_server/models/anchors.py`) is
  used by annotations, OCR geometry, entity mentions, claim evidence and readings. It already
  has a polygon, a rectangle, which image it was measured on, a character span, a granularity
  word, and nesting (an anchor that refines another). Six older box fields were retired into
  it. The code warns against a second addressing scheme. **The segment model must be built on
  this, not beside it.**
- **Readings with provenance already exist.** `ContentRepresentation`
  (`fichero_server/models/__init__.py`) is an immutable, source-anchored transcription,
  translation or transliteration with language, script, producing tool and model, and a review
  state, with a revisions table for human edits.
- **Several images per page already exist.** `Rendition` records the alternative images of one
  node, and geometry names the image it was measured on. The overlay refuses to draw boxes
  over an image they were not measured on.
- **Kraken already returns a baseline and a polygon per line**
  (`fichero_server/llm/kraken_runtime.py`). The PDF importer keeps every word's rectangle from
  a PDF's text layer (`media/ocr_geometry.py`).
- **The Preview already edits regions a little**: select, move, draw and name a new region,
  delete, and rate lines (`Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift`).
- **A claim's pointer is already fine-grained**: a character span or a region, resolved through
  one seam (`Models/ClaimSourceRequest.swift`), which refuses to draw a guess.

What is missing:

- **No segment has a lasting identity.** A line or word box has no id. Boxes are addressed by
  their position in a list, or by character offsets. A re-run makes a whole new list. Nothing
  survives a re-run at the level of a line or word.
- **Geometry is one block of JSON per result**, not one record per segment. "All the lines on
  this page", or "this word's history", cannot be asked of the store.
- **Polygons are carried but not used.** Kraken's polygon rides along as extra data; crops are
  always rectangles; there is no polygon mask.
- **Versions exist at two levels that do not meet**: a whole result has a version; a reading
  has revisions. Neither is per segment. This design must join them, not add a third.
- **No direction anywhere.** No right-to-left or vertical handling in the engine, the Reader or
  the Preview. Language is recorded per document only; script only on a reading. The detector
  knows English and Spanish.
- **No merge or split** in the Preview.
- **No PageXML, ALTO, TEI, MEI, SVG or YOLO** import or export. The Parquet export carries
  documents, entities and claims, and no geometry at all.
- **Kraken is inference only.** No training code. And it is not yet run automatically at
  import (importer spec, #4822).
- **No hands, ink layers, certainty or damage, typed links between segments, named reading
  orders, or declared glyphs.**

An earlier ruling stands and fits: language and other attributes are to **cascade** from app
to library to folder to page to region to line to word to character, with an override at any
level (recorded in `kg/historical-text-normalization.md` as a ratified future direction). This
design is where that cascade lives.

## How the existing specs fit under this one

This spec is the one home for the shared ideas. The others keep their own work and point
here. (They still live in `specs/kg/` for now; they move into this folder in one late step.)

- `kg/archival-data-model-plan.md` — the staged plan. Its primitive (the segment), its four
  slots and its delivery rule move here; it stays as the roadmap.
- `kg/segment-representations.md` — the first slice: read a segment's crop and text, in the
  Inspector, over MCP and CLI, exported.
- `kg/historical-text-normalization.md` — the text layer: normalisation, dates, name variants
  across scripts, language detection, translation, transliteration.
- `ui/reader-overlay-frame-identity.md` and `ui/preview-surface.md` — already own "a box is
  only valid against the image it was measured on", and the Preview / Reader / Inspector split.

## The delivery rule (stated once, here)

A capability is done only across the whole spine: **engine → app → agent (MCP) and command
line → tested → exportable.** Anything less is not done.

## Behaviors

None yet. They are written, with ids, tags and issues, once the intent above is ruled and the
milestone exists.

## Open questions for the creative director

1. **The name.** What is this area called: the source model, the page model, the archival
   model, or another word? (The folder is provisionally `source/`.)
2. **Reading orders and links.** The survey says a page needs both: several named reading
   orders, and typed links between segments. Is that the ruling?
3. **Which reading counts.** When a segment has several readings, which one is the
   transcription: an explicit choice by a person, falling back to the newest human reading,
   then the newest machine reading? Or something else?
4. **How much of the scholar's apparatus is in scope now.** Hands, ink layers, damage and
   certainty, written-versus-read: are all of these in the model from the start (even if the
   app shows them later), or added one at a time?
5. **No-Unicode signs.** Is the declared glyph (a name, a picture, optional private-use code)
   the right answer for what a researcher "types" when there is no character to type?
6. **The language authority.** BCP 47 tags backed by Glottolog are proposed. Is there a
   particular Indigenous-language source the maintainer wants used as well? (Name it here.)
7. **Fonts.** Does Fichero ship fonts for some scripts, let a researcher add their own to a
   library, or both?
8. **First format.** Which standard is imported and exported first? PageXML is the closest fit
   to the geometry and is what Kraken trains from; TEI is what editors publish.
9. **The columnar format.** Parquet through the existing export path (the exporter spec rules
   Parquet through DuckDB for library export), or Arrow files directly?
10. **Existing libraries.** Real research libraries already hold geometry as lists without
    ids. They are never rewritten by batch. Do their segments get identities lazily (the first
    time a page is opened or edited), or only when the researcher asks?
11. **The first slice.** What should a researcher be able to do first with this, in the next
    release?

## Sources for the survey

- PageXML schema 2019-07-15: https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd
- ALTO 4.4: https://github.com/altoxml/schema
- TEI P5, manuscripts and facsimiles: https://tei-c.org/release/doc/tei-p5-doc/en/html/PH.html
- TEI P5, non-standard characters and glyphs: https://tei-c.org/release/doc/tei-p5-doc/en/html/WD.html
- MEI facsimiles: https://music-encoding.org/guidelines/dev/content/facsimilesrecordings.html
- W3C Web Annotation Data Model: https://www.w3.org/TR/annotation-model/
- IIIF Image API 3.0: https://iiif.io/api/image/3.0/ · Text Granularity: https://iiif.io/api/extension/text-granularity/
- YOLO segment labels: https://docs.ultralytics.com/datasets/segment/
- Kraken training (ketos): https://kraken.re/4.2.0/ketos.html
- SegmOnto: https://segmonto.github.io/
- ISO 15924 script codes: https://www.unicode.org/iso15924/iso15924-codes.html
- Glottolog: https://glottolog.org/meta/downloads
- SVG 2 text: https://www.w3.org/TR/SVG2/text.html
- San Millán glosses: https://en.wikipedia.org/wiki/Glosas_Emilianenses
- Leiden conventions: https://en.wikipedia.org/wiki/Leiden_Conventions

Not verified in this pass, and marked so: the details of tagged-PDF alt text against the PDF
standard; the current MUFI recommendation version; eScriptorium's internal data model; the
licences of Indigenous-language catalogues other than Glottolog.
