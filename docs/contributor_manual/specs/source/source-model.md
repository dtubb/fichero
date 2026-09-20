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
> approved. Behaviour ids are in the slices, each tagged [GAP] with its issue on milestone 322.**
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
| `synced-folder.md` | a project tied to a folder: outputs kept current (the exporter's continuous export), files taken in (a trigger for the one import path), conflicts shown |
| `build-notes-readings-cascade-orders.md` | engineering detail for build slices 8 to 10; not for the maintainer to read |
| `build-notes-shapes-and-anchor.md` | engineering detail for build slice 7, with the size of the anchor retirement; not for the maintainer to read |
| `build-notes-identity-and-storage.md` | engineering detail for build slices 2 to 6 and the app's first slice; not for the maintainer to read |
| `rights-and-access.md` | rights, consent, community labels, restriction, redaction, removal (in the set by ruling; how it meets the permissions that already exist is blocked on the maintainer) |

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

(Models, chains and projects are specified in `models-chains-and-projects.md`; the synced
folder in `synced-folder.md`; the Source view's editor in `segment-editor.md`.)

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
- a **hand** and a **campaign**; the **state of the page** there; the scholar's
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
| **profile** | a named, shareable set-up for a kind of project ("Spanish palaeography"): languages, scripts, chain, models, guideline | the older plan's per-document "Profile" hinge is retired: a project's profile, plus overrides lower in the cascade, does its job |
| **job** | one kind of work a model does, with what it takes and gives (find lines; read a line) | |
| **chain** | jobs in order; what runs is always a workflow | |
| **recipe** | a shareable file describing a best-practice chain, which makes a workflow when applied (ruled; how it meets the shipped default workflows is blocked on the maintainer) | |
| **sign** | the unit of a script; a **declared sign** is one with no Unicode character | "declared glyph" |
| **flow** | a named reading order over text that continues across a column, page or picture | |
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

How embeddings and workflows store their results today is summarised in
`models-chains-and-projects.md`; how extraction does has not been read, and must be before
those behaviours are tagged.

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

## What exists today (read on disk 2026-09-19; corrected the same night after an independent check of every claim against the code)

Citations are to `fichero-server/src/fichero_server/` (engine) and `fichero/fichero/` (app).

**The bases this design grows from.**

- **The audited action layer.** Every write goes through one registry
  (`actions/registry.py`): typed, audited, undoable (an action has an `invert`), with a
  tamper-evident audit chain (`actions/audit_chain.py`). Every segment, reading and rights
  write in this set is an action there. It is the base, not something this set adds.
- **The change stream** (`api/change_stream.py`) tells open windows what changed, by typed
  lists of ids (entities, claims, documents, artifacts…). **It has no segment ids.** Until it
  does, a segment edit could only arrive as "this whole page changed", which the rule against
  re-rendering a whole list forbids. Adding them is an early slice of its own.
- **Four ways of saying "where" exist today, not one**: `SourceAnchor` and `NodeRegion`
  (`models/anchors.py`), `OCRGeometryBox` (`media/ocr_geometry.py`) and
  `AgentNoteSourceAnchor` (`models/__init__.py`). `SourceAnchor` is used by annotations, entity
  mentions, claim evidence and readings; it has a rectangle, a polygon, the image it was
  measured on, a character span, a granularity word, nesting, and a **rotation** (a text
  angle). Six older box fields were retired into it. **OCR geometry does not use it**: a box
  carries its own `bbox`. So "segments are addressed through the one shared anchor" is a
  **retirement** of the other three, and it is the largest migration in this programme, not
  today's state.
- **`NodeRegion`** is how a node carries its place in its parent (a diary entry, a promoted
  region). "A segment that matters enough is a node" is this type. A segment must not become
  a parallel of it.
- **Readings with provenance**: `ContentRepresentation` (`models/__init__.py`) is an immutable,
  anchored transcription, translation, transliteration, or SVG, with language, script,
  producing tool and model, a review state, and a revisions table for human edits. **But
  nothing in the engine creates one today**: every transcription and translation a workflow
  makes is an `Artifact` row with its text in `content`. The record is the right shape and the
  data is elsewhere, so readings are reached through one read seam over both, and writers move
  one at a time (see `build-notes-readings-cascade-orders.md`, slice 8).
- **Several images per page**: `Rendition` records the alternative images of one node, with
  pixel size and a `frame_status`; a geometry result names the image it was measured on (once
  for the whole result, not for each box). The overlay refuses to draw boxes over an image
  they were not measured on. An image has no checksum or physical scale yet.
- **Kraken already returns a baseline and a polygon for each line**
  (`llm/kraken_runtime.py`), carried today in a box's free `metadata`. Box records refuse
  unknown *fields* but that `metadata` is the working precedent for "nothing unrecognised is
  thrown away".
- **The Source view already edits regions a little**: select, move, draw and name a new
  region, rate lines (`Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift`, Mac
  only), delete (`ZoomableImagePreviewMac+Regions.swift`), and promote a region to a node.
- **A claim's pointer is already fine-grained**: a character span or a region, resolved through
  one seam (`Models/ClaimSourceRequest.swift`), which refuses to draw a guess.
- **Permissions below the project exist.** Owner, editor and viewer, plus grant-and-deny
  overrides on a target and everything under it, enforced on every audited write and in
  search (`security/authz.py`). They stop at a document, not a word.
- **Language machinery exists**: the known / unknown / never-determined distinction
  (`llm/language_policy.py`); a four-tier measure of how well a model covers a script, with an
  honest "cannot tell" (`llm/script_coverage.py`, `llm/language_coverage.py`, served as
  language fit); model recommendation (`llm/model_recommendations.py`).
- **Prototype inheritance** (`models/node_prototypes.py`): parent to child, child overrides,
  raises on a cycle. Profiles and structured segments use this one system.
- **Pieces of the formats work ship already**: Parquet, IIIF, W3C annotation and RDF export
  through one record stream (`export_service.py`); a IIIF and W3C-annotation importer
  (`importers/iiif_import.py`); a Convert-to-SVG tool (a vision model redraws; it is not made
  from geometry); a table-extraction tool (`workflows/tools/table_extract.py`).
- **A generated command line.** The CLI is generated from the OpenAPI contract (about 700
  commands), so a new route gets its command for nothing. Nobody hand-writes segment commands.
- **Honest absence has four spellings already** (`RegionConfidence`, the geometry status keys,
  `language_meta`, `frame_status`). This set reuses them; it does not invent a fifth.

**What is missing.**

- **No segment has a lasting identity.** A box has no id; boxes are addressed by position in
  a list, or by character offsets. A re-run makes a whole new list.
- **Geometry is one block of JSON for each result** (`Artifact.ocr_geometry`), not one record
  for each segment. Every reader of that block is a place the migration must reach.
- **Polygons are carried but not used**: crops are always rectangles; there is no mask.
- **Versions exist at two levels that do not meet** (a whole result; a reading's revisions).
  Neither is per segment. This design joins them; it does not add a third.
- **No direction anywhere**; language is recorded for a document only, script only on a
  reading; the detector knows English and Spanish.
- **No merge or split** in the Source view; no segment editing on the iPad or iPhone.
- **No PageXML, ALTO, TEI, MEI, hOCR or YOLO** in or out. The Parquet export carries no
  geometry.
- **Kraken is inference only**, and is not yet run automatically at import (#4822).
- **No hands, campaigns, certainty or damage, typed links between segments, named reading
  orders, or declared signs.**
- **A second chaining mechanism ships** beside workflows (`execution/chaining.py`, with its own
  routes), so "a chain is a workflow" is also a migration.

An earlier ruling stands and fits: language and other attributes are to **cascade**, with an
override at any level. The one list of levels, used everywhere in this set:

```
app  >  project  >  folder  >  document (a group of pages)  >  page  >  region  >  line
     >  word  >  character
```

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

## Build order (2026-09-19; engine before app; each slice builds, tests and commits alone)

Rules for every slice: one typed, audited, undoable action for every write; pydantic models;
routes in the OpenAPI contract (the command line is generated from it, and the Swift client
too: no hand-written URLs); a change event for every write; stores update one item in place;
tests pin behaviour ids; **temporary libraries only**. How an existing library reaches the
new model: the **schema** arrives when a library opens (new empty tables and columns, added
idempotently, safe to run twice, nothing rewritten); the **data** converts one page at a time
on that page's first edit, as one undoable step; every existing artifact, claim and highlight
stays resolvable; each slice that changes stored shape has a test that opens a library made
before the change.

### Slice 1 — one way to read a source's segments (engine only; writes nothing)

One engine call returns the segments of a source, whether they still live in today's block
of boxes or, later, in segment records. The caller cannot tell which. Because it writes
nothing, it cannot harm a library.

- **Behaviours:** `source.seam.read-either-store`, `source.seam.provisional-ids-refused`,
  `source.segment.names-its-image`, the "opening writes nothing" half of
  `source.store.ids-on-first-edit`, and the engine half of `source.one-store`.
- **Route:** `GET /api/segments/document/{doc_id}` (a new router registered at `/api/segments`,
  in `api/routes/document/segments.py`, following `content_representations.py`). Query:
  `artifact_id` (optional: one result's boxes), `pass_id` (optional), `kind` (optional: region,
  line, word…). Response model `SegmentListResponse`.
- **Models** (new file `models/segments.py`, exported from `models/__init__.py`; read shapes
  only in this slice, nothing is saved):
  - `SegmentRead`: `id: str`; `provisional: bool`; `document_id: str`; `pass_id: str`;
    `kind: str` (the anchor's granularity words: region, line, word…); `kind_raw: str | None`;
    `anchor: SourceAnchor` (rect, polygon where the box's metadata carries one, `rendition_id`
    copied from the result onto every segment, `char_start` / `char_end`, `rotation`);
    `baseline: list[list[float]] | None` (normalised to the same image); `text: str | None`
    (the box's own text, as the result gave it); `confidence: float | None`;
    `source_artifact_id: str | None`; `box_index: int | None`.
  - `PassRead`: `id: str`; `provisional: bool`; `document_id: str`; `name: str`;
    `provenance_kind` (the existing `ProvenanceKind`, set by the engine); `provider: str |
    None`; `model: str | None`; `run_id: str | None`; `created_at`.
  - `SegmentListResponse`: `document_id`, `passes: list[PassRead]`, `segments:
    list[SegmentRead]`.
- **Ids from the old block are provisional.** A segment read from `Artifact.ocr_geometry` gets
  `legacy:<artifact_id>:<box_index>` and `provisional: true`; its pass gets
  `legacy:<artifact_id>`. One helper (`assert_not_provisional`) raises a typed error, and every
  later write path calls it, so a provisional id can never be stored in a claim, a mark or a
  reading.
- **Who made each segment.** `SegmentRead` carries `provenance_kind` (the existing
  `ProvenanceKind`, the one claims use; → #4868, → #4869), **set by the engine**: `human` when the
  box's own provider or source proves a person drew it (a person's marquee is written into
  whatever machine result is showing, so this is known box by box), otherwise the pass's kind.
  It is never supplied by a caller and never defaults to `human`. There is no separate
  "hand-drawn" flag: one vocabulary for who made a thing, at every level. **A pass can therefore
  be mixed**: a machine's layout with a person's segments in it. Test: a machine result with
  one hand-drawn box returns that segment as `human` and the rest as the pass's kind.
- **One bad box never fails the page.** Today's boxes may have zero width or height, and a
  stored polygon may run off its image or have too few points; the anchor refuses all of
  these. Such a box is **still returned as a segment**, with the rect (or the polygon) left
  unset and the reason in `metadata["geometry_problem"]`. Nothing is clamped or invented.
  The same holds for a **baseline** (it must be two points or more, every number finite and
  inside the image, or it is left unset and reported) and for a polygon or baseline that is
  present but **cannot be read at all** (no usable pixel frame; values that are not numbers):
  it is reported, never dropped in silence. A bad rectangle never costs a good polygon, and a
  bad polygon never costs a good rectangle. No number that is not a number ever reaches the
  response.
- **Read shapes that last.** `SegmentRead` also has `metadata: dict` (raw pixel values from a
  tool go here, never into the anchor). `PassRead` also has `source_artifact_id` and
  `artifact_type` (the app ranks passes by them), and its `created_at` is a date and time or
  nothing, never an empty string. Passes come back ordered by `(created_at, id)`, segments in
  box order within a pass.
- **Kraken's polygon and baseline** ride in a box's `metadata` today, in pixels. The seam
  returns them normalised to the named image. A box with no polygon returns none (never a
  polygon invented from its rectangle).
- **Tests** (pytest marker `source_model`, added to `pyproject.toml`): a page with boxes
  returns one provisional segment for each box, rect for rect; every segment names the
  result's image; reading twice writes nothing (row counts and the artifact's `updated_at`
  unchanged; no `segments` table appears); a Kraken line's polygon and baseline come back
  normalised; `assert_not_provisional` refuses a `legacy:` id; a document with no geometry
  returns an empty list, not an error; **the same ids and rects come back from the route, the
  MCP tool and the generated command** (the hard gate).
- **Who may read.** The route takes a document id, so it uses today's per-target access check
  as it stands (a deny on a document or a folder above it refuses the read). The known gap in
  that check (→ #4917: a document's deny does not reach ids that are not documents) does not
  touch this route, because it never takes a bare segment id. Tests include **a viewer who is
  denied the document being refused**.
- **MCP:** one tool, `fichero_segments`, wrapping the route. **CLI:** generated.

Engineering detail for slices 2 to 6 (models, columns, indexes, actions, events, refusals,
tests) is in `build-notes-identity-and-storage.md`.

### Slice 2 — the change stream learns segment ids

`emit_change` and `ChangeSpec` gain `segment_ids` (and `pass_ids`), beside the id lists they
already carry; the Swift `ChangeEvent` decodes them. Nothing emits them yet. Behaviour:
`source.events.segment-ids`. Without this every later segment edit would refresh a whole page.

### Slice 3 — the schema: `Segment` and `Pass` records

Pydantic models saved through the ordinary store (a table appears on first save; columns are
added on open). A segment belongs to **exactly one pass**. Indexes are written by hand in
`db/migrations/schema.py` and must serve 200,000 rows for one source: by document and pass;
by document, pass and kind; by parent; and a coarse tile key for reads by area. The box
around a shape is stored in four columns the engine alone writes. Behaviours:
`source.store.record-per-segment`, `source.store.bounded-reads`, `source.pass.named-authored`,
`source.pass.never-overwrites`, `source.segment.one-primitive`, `source.segment.open-kinds`,
`source.segment.lasting-id`, `source.segment.box-is-derived`. Tests include opening a library
made before the change, twice.

### Slice 4 — identity: matches, forwarding notes, a citable reference

`SegmentMatch` and forwarding records; one call that follows an old id to where that ink is
now. Forwarding is a graph with no loops: following it walks step by step, **raises** past a
depth of 64 (never truncates), and a merge whose target already forwards to the source is
refused with the reason. Behaviours: `source.segment.match-record`,
`source.segment.forwarding-notes`, `source.segment.carry-across-a-match`,
`source.segment.citable` (the reference resolves through the existing location resolver,
`/api/locations/resolve`, which gains a segment id; no second resolver).

### Slice 5 — versions for each segment, and refusing a stale edit

A version column; compare-and-set inside the transaction; a typed refusal that says what
changed. Behaviours: `source.segment.versioned-alone`, `source.segment.delete-is-undoable`,
`source.edit.stale-is-refused`.

### Slice 6 — first-edit conversion (do not start before slices 1 to 5 are in)

One action converts one page's boxes into segment records as part of the first edit, and its
inverse deletes exactly the records it made. The rules are in `segments-and-geometry.md`
("First-edit conversion: the rules"). Behaviours: `source.store.ids-on-first-edit`,
`source.store.no-batch-rewrite`, `source.store.one-page-per-conversion`,
`source.store.conversion-undo-leaves-nothing`.

### Then, in dependency order

7. Shapes beyond the rectangle on `SourceAnchor` (point, open path, several shapes, curved
   baseline), the derived box, polygon crops and straightened line pictures.
8. Readings on segments: `ContentRepresentation` gains a segment id; the list of kinds opens;
   "which counts" is worked out, never stored as a flag.
9. The cascade (language, script, direction), extending `language_policy.resolve_language`,
   answering with where each value came from.
10. Reading orders, flows and typed links.
11. The format model and its harness (validate, loss report, round trip); then PageXML; then
    ALTO; then YOLO labels. TEI after those, with its own reader and writer.
12. The editor's performance trial: a hard gate.
13. The editor: one overlay, one input seam, every edit an action.
14. Hands, campaigns, certainty and damage, letterforms, declared signs: independent of each
    other, any order, after 8.
15. Recordings; maps and control points; the canvas: self-contained, any time after 7.

**Not to be built until the maintainer rules** (each is written up in the morning file with
the reviewers' recommendation): recipes beside the shipped default workflows; a Segments pane
beside the ruling that there is no browser pane kind; rights records beside the permissions
that already exist; and whether an action's audited record may hold a researcher's words at
all (it sits inside the tamper-evident chain, which a purge could not then reach).

**Build milestones proposed** (the spec set stays on `source-model`, 322): *source-model:
identity and storage* (slices 1 to 6); *source-model: shapes and readings* (7 to 10, 14);
*source-model: formats* (11), with *TEI* apart; *source-model: the segment editor* (12, 13);
*models, chains and projects*; *the synced folder*; *training and measuring*; *recordings*;
*rights and access*.

## Behaviors

The foundation has two of its own. Everything else is in the slices.

- `source.one-store` — **[GAP]** (#4919) only one engine call returns a segment's shape, and only one returns
  its picture; the Source view, Reader, Inspector, agents, training and export all use them,
  and the app keeps no second store of segments.
- `source.builds-on-the-anchor` — **[GAP]** (#4925) a segment's place is a `SourceAnchor`, and the other three
  ways of saying "where" (`OCRGeometryBox`'s own box, `AgentNoteSourceAnchor`, and any new
  one) are retired onto it, slice by slice; no new addressing scheme is introduced. This is a
  migration, the largest in the programme, and each slice that retires one says so.

Where the promises in "What stands on segments" are pinned: search landing on a segment and
vectors, `source.derived.recomputable` (segments); claims resting on segments,
`source.statement.on-segment` and `source.statement.both-ways` (segments); workflows taking
segments and giving passes, `source.chain.segments-to-any-reader` and
`source.chain.output-never-overwrites` (models); open lists, `source.segment.open-kinds`,
`source.reading.kinds`, `source.date.open-calendars`, `source.link.typed`.

Every behaviour in the set is tagged **[GAP]** and cites one of 35 grouped issues on milestone
`source-model` (322), filed 2026-09-19: one issue for each coherent piece of work, not one for
each behaviour. Four of them are marked BLOCKED on the maintainer.

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

**Blocked on the maintainer** (found by review on the night of 2026-09-19; each is in the
morning file with the reviewers' recommendation; nothing is built on any of them):
recipes as files beside the fifty shipped default workflows; a Segments pane beside the ruling
that there is no browser kind of pane; rights records beside the permissions that already
exist; and whether an action's audited record may hold a researcher's words at all.

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
