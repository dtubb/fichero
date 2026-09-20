# Source Model — how a source is represented — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — the user manual needs a "How Fichero represents a source" section, written for
> a researcher: a source is addressable from a group of pages down to a single stroke; every
> reading, translation, note and claim points at the exact place it came from; and the whole
> thing can leave as standard XML and come back.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — third pass, 2026-09-19. This is the FOUNDATION of the
> source model: the intent, the rulings, the words, and the map of the other files. Nothing is
> approved. Behaviour ids are in the slices, untagged until approval.**
> Tags (when behaviours arrive): **[OK]** built and tested · **[PARTIAL]** built, partly proven
> · **[GAP]** intended, never built · **[BROKEN]** code contradicts the rule.
>
> The name "source model" follows the maintainer's wording (the source is the page; a segment
> is everything on it). **One milestone for the whole set** (ruled 2026-09-19): every file in
> this folder's new set declares `Milestone: source-model` (GitHub milestone 322). That is
> deliberate; do not "fix" it to one milestone for each file.
> Under "The design", what the maintainer has ruled is listed first ("Ruled"); the rest is
> PROPOSED until ruled.

## Intent (the design)

Everything Fichero knows comes from somewhere on a source. A transcription, a translation, a
note, a workflow result, a knowledge-graph claim or entity: each one must be able to point at
the exact place it came from. Not just "this page", and not just "this run of characters in a
text editor", but the ink itself, as finely as the work needs.

This is more fundamental than the knowledge graph. The knowledge graph, transcription,
workflows, search and export all stand on it. So it gets its own spec area, and one model.
Every claim in the knowledge graph points at a segment.

The goal is to represent a page properly, once, so that Fichero is truly useful for:

- **under-resourced languages and scripts**, including ones with poor or no model support, no
  settled script, or no place in Unicode;
- **writing in any direction**: left-to-right, right-to-left, vertical, mixed on one page or in
  one line, and writing that follows a curve;
- **annotation**: glosses, interlinear notes, marginalia, commentary that answers commentary,
  by several authors over several centuries on the same page.

The maintainer does not want to decide, case by case, what a palaeographer of tenth-century
Spain needs versus one of early Arabic or of Aramaic. The model must be general enough that
each of them finds what they need already there. The worked examples in `source-survey.md`
are the test.

## The files

| File | What it holds |
|---|---|
| `source-model.md` | this file: intent, rulings, the words, what exists today, the rulings of 2026-09-19 and what is still open |
| `source-survey.md` | the evidence: standards, worked examples from philology, the field's tools, other document models, sources |
| `segments-and-geometry.md` | identity, shape, images, the ladder, passes, reading orders, links, maps, versions, storage |
| `readings-and-apparatus.md` | readings, written and read, hands, campaigns, the three kinds of "sure", letterforms, the researcher's marks |
| `languages-scripts-signs.md` | language, script, encoding, the cascade, direction, declared signs, sign lists, fonts, input |
| `segment-editor.md` | the native editor in the Source view, the Segments pane, the Pencil, the performance trial, accessibility |
| `formats-and-training.md` | every format in and out, validation, loss reports, the training loop, measuring a model |
| `models-chains-and-projects.md` | one card for every model, jobs with typed inputs and outputs, chains as workflows, how a result was made, projects and onboarding, finding models, the synced folder |
| `rights-and-access.md` | rights, consent, community labels, restriction, redaction, removal (raised by review; not yet discussed) |

**How to read the set.** This file first: it gives the whole shape. Then, for depth, in this
order: Segments and geometry; Readings and apparatus; Languages, scripts and signs; The
segment editor; Formats and training; Models, chains and projects; Rights and access. The
survey is the evidence: dip into it. The three older files in this folder
(`segment-representations.md`, `historical-text-normalization.md`,
`archival-data-model-plan.md`) are the earlier work; where they differ from this set, this
set wins.

## The design

### Ruled (maintainer, 2026-09-19)

- **All of it, done properly, from the start.** The whole scholar's apparatus is in the model
  from the beginning: hands, campaigns, certainty and damage, written-versus-read, named
  reading orders, typed links, declared signs. Not a core now and the rest later.
- **Engine and app together.** Everything the model can hold can be got into Fichero, seen in
  Fichero, and edited in Fichero. A thing stored but not visible is not done.
- **Fichero has its own model**, richer than any one standard. The standards are ways in and
  out, not the model.
- **Every format goes both ways.** The XML formats, the columnar format, Kraken's formats and
  YOLO's are all import *and* export.
- **Open to what we do not know yet.** An Indigenous script nobody has encoded, an ancient
  language with no glyphs in any font, a practice no standard describes: the model must be
  able to hold it and the app must be able to show it, without waiting for a new version of
  Fichero.

- **Build on what is there, and go deep.** The existing anchor, readings, images-per-page and
  region editing are the base; this design develops and expands them. It does not start again.
  The purpose of this spec is to describe the whole thing properly first. The order of
  building is decided afterwards, from the finished spec.
- **Two known shortfalls the design must close.** The Source view's editor cannot yet handle what
  this model describes. And Fichero cannot yet hand out, or take in, the picture of one
  segment (a sign, a word, a line) the way Kraken training needs.
- **A researcher's own marks go on any segment.** Notes, highlights, stars and tags, and a
  segment's place in a reading order, work at every level of the ladder, the same way they
  work on a whole document.

- **The words.** The **source** is the page (and the group of pages it belongs to). A
  **segment** is everything on it: every region, line, word, character, stroke, picture, note
  and gloss. Things in Fichero point at segments; segments belong to a source.
- **The editor is native.** Segments are edited in a SwiftUI editor in the Source view, so that one
  editor works on the Mac, the iPad and the iPhone, feels like a Mac app, and takes the Apple
  Pencil. SVG is an export format, and a web editor is not the plan. The field's web tools are
  surveyed for their ideas, not their code.

- **It reaches the rest of Fichero.** Embeddings, the knowledge graph, content, the Reader and
  workflows all work on segments (see "What stands on segments"). The Reader must be able to
  show any script, language and reading direction.
- **Models are described one way.** Every model Fichero can use (vision-language models, Apple
  Vision, Kraken's baseline and reading models, layout detectors, spaCy pipelines, embedding
  models) is described in one consistent way, the same in the app, over MCP and on the command
  line: what it does, what it takes in, what it gives out, which languages, scripts and
  periods it suits. Fichero can also look for good models where the field keeps them.
- **Steps chain, and the chain is visible.** One model's output feeds the next (Kraken finds
  the baselines; Apple Vision or a local model reads each line; another corrects it). How any
  reading or pass came to be, step by step, can always be seen, and the chain is offered
  through workflows and the workflow bar.
- **A project sets itself up.** A **project** is what Fichero has called a library (the new
  name is decided; the app has not been renamed yet). Language and models have been one
  setting for the whole app. Now each project (palaeography here, twenty-first-century notes
  there) has its own settings window and its own onboarding, with a default chain and best
  practice chosen from its languages, scripts and period.
- **The Preview becomes the Source view.** Also decided, also not yet carried through the app.
  This set uses the new names. Code paths and older specs still say Library and Preview.
- **A synced folder.** A project can be tied to a folder. Its outputs (the XML and the rest)
  are written there and kept up to date as the work goes on.

(The last four are specified in `models-chains-and-projects.md`.)

### Open to what we do not know yet

How the "open to what we do not know yet" ruling is met:

- **Every vocabulary is open.** Segment kinds, link types, reading kinds, directions, ink
  passes, damage reasons: each ships with a standard default list and a project can add its
  own terms. A term is data, not code.
- **A sign is never required to be a character.** A declared sign needs only a name and a
  picture cut from a real page. A whole script can be built up this way, sign by sign, from
  the sources themselves, and transcribed, searched, compared and exported.
- **Nothing unrecognised is thrown away.** An import that meets something the model has no
  field for keeps it, attached to the segment, labelled with where it came from, and writes it
  back on export.
- **What can be stored can be shown.** A reading made of declared signs shows their pictures
  in line. A direction the Reader cannot lay out as text is shown on the image, in place.

### The model in one page (proposed until ruled; detail in the slices)

```
collection  >  codex unit  >  quire  >  leaf  >  page (recto, verso)  >  region
            >  line or column  >  word  >  character  >  stroke
```

A **group of pages** is any set of pages taken together: a codex unit, a quire, an **opening**
(two facing pages), a letter, a case file. (The same ladder, with its detail, is in
`segments-and-geometry.md`.)

Every level, and every picture, seal, table, mark and map symbol, is a **segment**: one
primitive with a kind. A segment has:

- a **lasting id**: the one thing Fichero lacks today, and what everything else hangs from;
- a **shape** (point, line or area; a curved baseline for writing) on a **named image** of the
  page;
- a place in the **ladder**, in a **logical unit** (a letter, an entry), in a **pass**, and in
  one or more **named reading orders**;
- **typed links** to other segments, to any depth;
- **language, script and direction**, inherited from above unless set;
- a set of **readings** (as written, expanded, normalised, as read aloud, translation,
  description), each with its author; one chosen;
- a **hand** and an **campaign**; the **state of the page** there; the scholar's
  **certainty**; the machine's **confidence**: three separate things;
- **signs** that need not be characters;
- the researcher's **notes, highlights, stars and tags**;
- the **statements** of the knowledge graph that rest on it;
- its own **versions**;
- its **picture**, cut to its shape, on request.

### The words (one meaning each)

| Word | Means | Replaces |
|---|---|---|
| **project** | one research undertaking with its own file, settings and onboarding | "library" (the Library pane's own name is an open question) |
| **Source view** | the pane that shows a source's image and, with a segment focus, edits its segments | "Preview" |
| **source** | the page, the group of pages it belongs to, or a recording | |
| **segment** | anything on a source, at any level, with a lasting id | the older "a segment is one anchor" |
| **pass** | one authored set of segments over a source: a model run, a person's layout, an import. The **working pass** is the one the Reader, search and export use; in a strict project only a person makes a pass the working pass | "layer", in its first sense |
| **campaign** | one campaign of writing on the page: main ink, rubric, later vowels, under-text | "ink layer" |
| **reading** | what someone or something says a segment reads: text, translation, description | the older plan's "transcription", and its "edition" (now a reading's **kind** and **level**) |
| **mark set** | one researcher's notes, highlights, stars and tags | |
| **worked-out things** | pictures, vectors, search entries, word-level analysis, made from segments and readings | the older spec's "representations" |
| **profile** | a named, shareable set-up for a kind of project ("Spanish palaeography"): languages, scripts, chain, models, guideline. The older plan's "Profile" is this same thing | |
| **projection** | a cut-down copy made for one purpose (an export, a training set, the synced folder) that can always be made again from the project | |
| **match**, **forwarding note** | how identity is followed between passes, and after merge, split or delete | |

The word **layer** is retired for sets of segments and for ink. It keeps its ordinary meaning
elsewhere (the audited action layer; a PDF's text layer; PageXML's own z-layers).

Behaviour ids in this set begin `source.`. The ids beginning `segment.` belong to the first
slice (`segment-representations.md`) and stay as they are.

### What stands on segments

The point of doing this properly is that everything else in Fichero gets better footing:

- **Content and the Reader.** A page's text is worked out from its segments, a reading order
  and the chosen readings. The Reader shows it in the right direction, with glosses and notes
  in their places, and every word can lead back to its ink.
- **Search and embeddings.** A search result lands on a **segment**, not just a page. Text
  vectors are made from readings; picture vectors from segment pictures. So "find this word",
  "find passages like this one", "find signs that look like this one" and "find pages laid
  out like this" are all the same kind of question at different levels. Every vector names
  the segment, reading, model and version it came from. Background work stays throttled.
- **The knowledge graph.** A mention, a claim and an entity's evidence point at segments.
  Extraction runs over segments, so it knows each passage's language and script, can leave
  out page furniture, and can treat a gloss as a gloss. Clicking a sentence in the readable
  paragraph shows the very words on the page. A place named on a map ties to the place
  entity. A hand can be an entity (a scribe is a person). Merging or re-transcribing does not
  break a claim's evidence.
- **Workflows.** A tool takes segments in and gives passes and readings out. "Run on the
  selection" can mean these three lines. Machine output always arrives as a new pass or a new
  reading, never over a person's work.
- **Language tools.** Normalising, dating, name-matching, translating and transliterating
  (`historical-text-normalization.md`) work on a reading of a segment and produce another
  reading, with the language and script known from the cascade.
- **Export and training.** See `formats-and-training.md`.

How embeddings, extraction and workflows store their results today has not been read for this
pass; it must be before these are tagged.

### One store, many uses

The same stored segments serve every use. No use gets its own copy:

- the **Source view** draws and edits them;
- the **Reader** shows their readings, in the right direction, order and font;
- the **Inspector** shows one segment: readings, versions, hand, links, statements;
- an **agent** (MCP) and the **command line** read and write them;
- **training** takes them out as crops plus readings;
- **export** writes them as standard files.

Moving around is the same everywhere: up to the parent, down to the children, next and
previous in a reading order, across a link.

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
  node, and a geometry result names the image it was measured on (once for the whole result,
  not for each box). The overlay refuses to draw boxes over an image they were not measured
  on. An image has no checksum or physical scale of its own yet.
- **The anchor has limits** the design must lift: one rectangle (which must have width and
  height), one closed polygon; no point, open path, baseline, several shapes or time span;
  no id of its own. Box records accept no extra fields, so nothing unrecognised can ride on
  them today.
- **Kraken already returns a baseline and a polygon per line**
  (`fichero_server/llm/kraken_runtime.py`). The PDF importer keeps every word's rectangle from
  a PDF's text layer (`media/ocr_geometry.py`).
- **The Source view already edits regions a little**: select, move, draw and name a new region,
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
  the Source view. Language is recorded per document only; script only on a reading. The detector
  knows English and Spanish.
- **No merge or split** in the Source view.
- **No PageXML, ALTO, TEI, MEI, SVG or YOLO** import or export. The Parquet export carries
  documents, entities and claims, and no geometry at all.
- **Kraken is inference only.** No training code. And it is not yet run automatically at
  import (importer spec, #4822).
- **No hands, campaigns, certainty or damage, typed links between segments, named reading
  orders, or declared signs.**

An earlier ruling stands and fits: language and other attributes are to **cascade** from app
to project to folder to page to region to line to word to character, with an override at any
level (recorded in `historical-text-normalization.md` as a ratified future direction). This
design is where that cascade lives.

## How the existing specs fit under this one

This spec is the one home for the shared ideas. The others keep their own work and point
here. (They moved into this folder from `specs/kg/` on 2026-09-19; milestones and behaviour ids
are unchanged.)

- `archival-data-model-plan.md` — the staged plan. Its primitive (the segment), its four
  slots and its delivery rule move here; it stays as the roadmap.
- `segment-representations.md` — the first slice: read a segment's crop and text, in the
  Inspector, over MCP and CLI, exported.
- `historical-text-normalization.md` — the text side: normalisation, dates, name variants
  across scripts, language detection, translation, transliteration.
- `ui/reader-overlay-frame-identity.md` and `ui/preview-surface.md` — already own "a box is
  only valid against the image it was measured on", and the Source view / Reader / Inspector split.

## The delivery rule (stated once, here; a gate, not a behaviour)

A capability is done only across the whole spine: **engine → app → agent (MCP) and command
line → tested → exportable.** Anything less is not done.

## Behaviors

The foundation has two of its own. Everything else is in the slices.

- `source.one-store` — only one engine call returns a segment's shape, and only one returns
  its picture; the Source view, Reader, Inspector, agents, training and export all use them,
  and the app keeps no second store of segments.
- `source.builds-on-the-anchor` — segments are addressed through the one shared anchor type;
  no second addressing scheme is introduced.

Where the promises in "What stands on segments" are pinned: search landing on a segment and
vectors, `source.derived.recomputable` (segments); claims resting on segments,
`source.statement.on-segment` and `source.statement.both-ways` (segments); workflows taking
segments and giving passes, `source.chain.segments-to-any-reader` and
`source.chain.output-never-overwrites` (models); open lists, `source.segment.open-kinds`,
`source.reading.kinds`, `source.date.open-calendars`, `source.link.typed`.

None is tagged yet: tags need issues, issues need the milestone, and the milestone is made at
approval.

## Plain-word glossary

- **Allograph** — a recognised way of writing a letter (two-storey *a*, single-storey *a*).
- **Ductus** — the order and direction of the strokes that make a letter.
- **Ketiv / qere** — in the Hebrew Bible, the word as written and the word to be read aloud.
- **Palimpsest** — a page scraped and written over; the older text often shows only under
  special light.
- **Bidirectional** — text that runs both ways in one line (Arabic with numerals).
- **BCP 47, ISO 15924, Glottolog** — the standard lists of language tags, script codes, and
  the world's languages and dialects.
- **SegmOnto** — the field's shared list of names for kinds of region and line.
- **HTR** — handwritten text recognition. **HTR-United** — a shared catalogue of training
  sets and a standard way to describe one.
- **Arrow / Parquet, "columnar"** — table-shaped data files that training tools read quickly.
- **Projection** — a cut-down copy made for one purpose, which can always be made again.
- **Quire, leaf, recto, verso** — a quire is a gathering of folded sheets sewn together; a leaf
  is one of its sheets; recto and verso are a leaf's front and back.
- **Rubric** — a heading or instruction written in red.
- **Ground truth** — pages a person has fully corrected, trusted enough to teach or to test a
  model. **Character error rate** — how many characters in a hundred a model gets wrong.
- **Model card** — the one description Fichero keeps of a model. **Licence class** — open,
  non-commercial, gated, or special terms. **Role default** — a stand-in name such as "small
  model" that a project fills in.
- **Prototype** — a pattern a thing can be made from and inherit its settings from (as in
  Tinderbox). A project profile is one.
- **Julian Day Number** — one running count of days, used to put dates from any calendar on
  one timeline. **EDTF** — a standard way to write uncertain and approximate dates.
  **PeriodO** — a shared list of named periods with their date ranges.
- **CARE** — principles for Indigenous data (collective benefit, authority to control,
  responsibility, ethics). **TK labels** — Traditional Knowledge labels a community applies
  to say how its material may be used.

## Rulings of 2026-09-19 (second round), and what is still open

The maintainer answered the set's open questions one by one on 2026-09-19. Paraphrased:

1. **Identity.** An id never moves. "This new line is that old line" is a separate match
   record. Merge, split and delete leave forwarding notes.
2. **Existing projects.** Opening a page writes nothing. The first edit writes that page's
   segments once, undoably.
3. **The words.** *Pass* and *campaign* replace the two kinds of "layer". *Profile* has one
   meaning. What the Library pane is called once a library is a project is **left for the
   app-wide rename spec**.
4. **What counts as the record is a project's own rule.** A project is either *strict* (only a
   person chooses the reading that counts and makes a pass the working pass; machine work is
   labelled until then) or *relaxed* (the newest reading counts, and a person's always
   outranks a machine's). **A new project starts strict.** A profile can set either.
5. **Rights and access are in this set.** Owners and editors can restrict and redact. Only the
   owner can purge.
6. **No list of what was exported** is kept. Following up a removal outside Fichero is the
   researcher's own job.
7. **Recordings are in this set**: segments can be stretches of time.
8. **Several named reading orders, plus typed links** kept for cross-references.
9. **Automatic work is allowed after a first yes** for each project. What it makes follows the
   project's rule in 4.
10. **A folder inside a project can carry its own settings**, through the cascade, set in the
    Inspector. No second settings window.
11. **Levels of normalisation.** Three sensible defaults (as written, expanded, normalised),
    and the list is open: a project can define its own.
12. **A sign with no character is a declared sign** (a name and a picture from a real page,
    optionally a number in a sign list, a private-use code, a font).
13. **Languages.** Glottolog is the source the maintainer had in mind, beside standard language
    tags. Native Land Digital and FirstVoices are wanted too, and the list of sources is open.
14. **Fonts.** Fichero ships a few and a project can add its own; and there should be **a good,
    easy way to find fonts for a script and add them**, as there is for models.
15. **Openings and millimetres:** yes to both.
16. **Onboarding starts with sample pages.** Fichero proposes what the project is; then a
    profile, or the questions, or both, to correct it.
17. **Models from outside.** Kraken's repository and Hugging Face at first, the list open.
    Copyleft models are downloaded on request, not bundled.
18. **A Segments pane.** The Library gets you to a page. Getting to the segments themselves, to
    move, edit and reorder them, with their readings beside them, wants a surface of its own.
    There may be more than one such view. **Its design is open** (see below).
19. **Formats.** PageXML, TEI and ALTO are all built first, with YOLO's text labels. They sit
    on **one general mapping system** that makes adding another format easy, and **every
    export is validated**.
20. **Recipes are files of their own.** A best-practice chain is a shareable file that makes a
    workflow when it is applied. What runs is still a workflow: one way of running, two ways
    of arriving at it.
21. **Settled by the spec writer, and the maintainer can overturn any of them:** the area is
    the "source model"; one milestone for the whole set, with the guardrail exception
    recorded; a claim keeps a copy of its anchor beside the segment id; Parquet through the
    existing export path; fine-tuning inside Fichero becomes its own later spec (Kraken
    training); the synced folder has a fixed layout that Fichero chooses; "smooth" in the
    editor trial means sixty frames a second with twenty thousand shapes on the oldest
    supported iPhone.

### Still open

1. **The Segments pane.** What it shows and does: a list, a strip or a grid of segment
   pictures with their readings; reordering by dragging; moving segments between regions and
   passes; editing a reading in place or in the Reader beside it. How it stays one code path
   with the Library's listing and the Source view's editor. This needs its own design pass
   with the maintainer.
2. **The Library pane's name** once a library is a project (for the rename spec).
3. **Who may see restricted material among editors**: every editor, or only those a rights
   record names?
4. **The order of building.** Decided after the spec is whole (ruled). What depends on what:
   segment records with ids and passes; the anchor's new shapes; matches and forwarding
   notes; versions for each segment; readings on segments; the cascade and direction; rights;
   citation; structure and links; the editor (after its trial) and the Segments pane; the
   apparatus; the general format mapping, then PageXML, ALTO, TEI and YOLO on it; training and
   measuring; models, chains, recipes and projects alongside; recordings from early on. The
   smallest honest first slice: one real page, its existing Kraken lines read as segments
   without writing; reshape one line and split one line as undoable actions; the same segment
   identical from engine, MCP, command line and app; PageXML out and back in as a second
   pass with a loss report; corrected lines out as straightened line pictures with readings.
