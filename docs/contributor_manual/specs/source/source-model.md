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

### Every output comes into the page (ruled 2026-10-05, #5467; proposal below awaits the maintainer)

**The ruling.** A page has one canonical model: its segments (region, line, word, letter, each
the child of the one above) and what stands on them. Every artifact and output is brought into
that model and tied back to its segments; none stays a loose file the page cannot use. The Source
view, the Segments list and the Reader read that one page; focusing an artifact shows that
artifact's pass within it, and all three follow together.

**What each producer writes today (audit, read on disk 2026-10-05).** Five kinds of result:
(1) a pass of segments, (2) readings on existing segments, (3) statements or names anchored to
the page, (4) a loose artifact, (5) nothing kept.

| Producer | Writes | Gap | Issue |
|---|---|---|---|
| File import (PAGE, ALTO, hOCR, TEI, plain, YOLO, IIIF) | 1 + 2, full hierarchy, letters from PAGE Glyph | TEI names do not become names | — |
| Line finding (Kraken, Apple, VLM boxes) | 1; Kraken's lines nested in its regions (#5487, 2026-10-06), the others flat | no nesting for Apple and VLM boxes | #5489 |
| Reading lines (Kraken reader, line reader) | 2, readings on the working pass's lines (#5487, 2026-10-06); 1 + 2 only on a page with no lines | none | — |
| Reading a page (LLM Transcribe) | 4, page text; tied onto the lines by the `tie-text-to-lines` job, queued after every page reading on a page with lines (#5444, #5558, 2026-10-06) | the cluster reader drops Kraken's regions; older tie passes stay | #5558 |
| Correcting (Paleographer Review) | 4, page-level, overwrites page text | corrections never become readings on lines | #5486 |
| Checking | 2, verdicts and corrections on segments | none: the model for the rest | — |
| Names | 3, tied to the document only | spans discarded; no mention on a segment | #5488 |
| Statements | 3, page text offsets and an optional rect | no segment anchor | #4932 |
| Conversion of results (#5222) | 1 + 2, flat | no `parent_segment_id`; no letter level | #5489 |
| Translation, dates, places, catalogue, tables, speech | 4 (no recipe card for 17 jobs) | loose artifacts | #5490 |
| DOCX, Markdown, slip box, Fichero 1.0 | 4, page text | no pass | #5222 |

**The proposal (for the maintainer to rule).**
- *Text comes in on lines.* Any page-level text (an LLM reading, a correction, a DOCX draft, a
  legacy transcription) is tied to the working pass's lines by one converter (`checking/tie_text.py`),
  run automatically after the step that made it, and written as readings on those lines. The page
  text is then derived from the lines, never stored beside them.
- *One line pass per page, read many times.* Finding lines makes the pass; reading, correcting and
  checking add readings to its segments; they never make a second line pass.
- *Nesting at conversion.* A converted result nests by containment (word in line in region), keeps
  the regions a model found, and has a letter level where the model gives letters.
- *Names and statements stand on segments.* A name found is a mention: a segment and a stretch of
  its reading (character offsets). A statement rests on the mentions it joins.
- *Every other output names its anchor before it is built.* Translation is a reading of kind
  translation on a line; a date or a place is a mention; a table row is its cells' segments; speech
  is a time segment. A kind of output with no anchor is not built until it has one.

Not built: every row with an issue above. The order proposed: #5487 and #5444 (one line pass,
text onto lines; built 2026-10-06 for the readers and the tie, see `source.model.one-line-pass`), then
#5486, then #5489, then #5488 and #4932, then #5490.

### Extracted data, integrated (review 2026-10-07)

**What the maintainer saw (paraphrased).** What Fichero pulls out of a source (a diary's entries and
their dates, names of people, places and things, statements, quotations, tables, catalogue fields,
the attributes of a judgment such as its court, judge, parties, date and ruling, and the kinds and
groups Find the Documents proposes) does not yet belong to the archive model, the page model or the
Preview. It sits beside them. The ruling above (#5467) already says where it must go: into the one
page, tied to its segments, so a person can see it where it came from, correct it there and cite it.
He widened the review the same day to every output of every shipped workflow, and to the question of
what level of the archive a workflow can run on.

Read on disk 2026-10-07 in the `harden` worktree (paths under `fichero-server/src/fichero_server/`
unless they start `fichero/`). The overlay inventory in `ui/layers-on-the-source.md` ("What each
layer is anchored to today") is the companion of this table and is not repeated.

#### Each kind of extracted data today

Columns: **stored as** (the record); **tied to** (the finest place it points at); **Preview** (drawn on
the page as a layer); **Inspector** (shown with its source); **corrected** (by a person, audited and
undoable, in place); **exported** (in the record stream, PAGE/ALTO/TEI, IIIF/W3C); **searched**;
**views** (timeline, table, map).

| Data | Stored as | Tied to | Preview | Inspector | Corrected | Exported | Searched | Views |
|---|---|---|---|---|---|---|---|---|
| Page date (Work Out Dates) | `Document.date_original/date_jdn/date_jdn_end/date_meta` (`workflows/tools/date_extract.py:457-461`) **and** a `dates` artifact with the same record (`:502-510`) | the document; the heading's words are kept in `date_meta["heading"]` (`histdate.py:969`), not its line | no | Info tab, from the columns | yes, `document.set_date` (audited; `api/routes/document/documents.py:3156`), and a later run records a conflict, not an overwrite (`date_extract.py:386-456`) | **no**: the record stream's document row has no date (`export_service.py:139-156`) | filter and sort by `date_jdn` (`api/routes/search/core.py:765`) | dataset grid; time view |
| Diary entry and its date | a child `Document` with `node_kind="entry"`, its own **copy** of the text (`page_content=body`), `attributes={"date": iso}`, `metadata.date_text`, a rectangle `region_in_parent` (`workflows/tools/diary_entries.py:580-604`) | a rectangle unioned from the page's boxes, `bbox_basis` noted; not the lines it covers; no `date_jdn` on the entry | the region, as a box | as a node | name, text and region as a node; the date only as a raw attribute | as a document, without the date | as a document | the entry's date is not on the time view's axis (it reads `date_jdn`) |
| Dated line items on account pages (#5559) | nothing: the page is ruled not an entry and left undated (`histdate.py:1296`) | — | — | — | — | — | — | — |
| Names (people, places, organisations, events, keywords) | `KnowledgeEntity` with `source_document_ids` (`models/knowledge.py:866`) **and** per-section artifacts (`people`, `places`, `rivers`… `workflows/tools/extractors.py:1212`, `:1255`, `:1520`, `:1541`) | the document, and a mention (a supporting source on the entity) at each place the page text writes the name, with its line and reading when the page is tied (#5488) | no (#1659) | entity inspector, "appears in" pages; the per-segment read lists the names on the line (`GET /api/segments/{id}/statements`) | `entity.update` (audited) on the entity; the artifact copy is untouched | entities as rows with document ids only (`export_service.py:161-181`); not as `persName`/`placeName` in TEI | `people:X` / `places:X` / `organizations:X` / `events:X` read the entity and its mentions (#5597; `api/routes/search/core.py` `_entity_scope_results`); `keywords:`, `dates:` and the unscoped bridge still read artifact JSON | networks, from entities |
| Places with coordinates | a `geo` artifact **and** `metadata["geo_points"]` on the document (`workflows/tools/geo_extract.py:41-46`) **and**, separately, `place_values` on entities and claims (`workflows/tools/_entity_writer.py:1050-1068`) | the document | no | as an artifact | `artifact.update` on the artifact only | no | no | map reads `geo_points` |
| Statements (claims) | `KnowledgeClaim`, character offsets into the page text the extractor saw and an optional rectangle with an unstated space (`workflows/tools/extractors.py:2728-2757`, `:2735-2746`) | a page-text span and, when the page is tied, the line its words start on with that line's reading (#4932, #5488) | no | statements section on a segment (`fichero/fichero/Views/Inspector/Source/InspectorStatementsSection.swift`), for claims on a tied page; the claim inspector shows the excerpt | `claim.patch`, `claim.transition` (audited) | record stream without offsets, anchor or time (`export_service.py:198-214`); site export as text; no W3C annotation (`api/routes/ingest/iiif.py:158-209` serves annotations only) | yes, as claims | readable paragraph; time view from `time_start` |
| Quotations | a claim (speaker, "said", the quote as object) **and** a `quotes` artifact (`workflows/tools/extractors.py:420-449`) | the quoted words' offsets in the page text, and the line they start on with its reading when the page is tied (#5598); the speaker a mention on the name's span | no | as a claim | as a claim | as a claim | as a claim | — |
| Catalogue fields (Archival Summary) | `catalogue.narrative`, `catalogue.timeline`, `catalogue.keywords`, `catalogue.chunk` artifacts on a folder chosen by a heuristic (`workflows/tools/catalogue.py:289-348`, `:786-804`), and the narrative **written into the folder's `page_content`** (`:829`); the fields are rebuilt from claims each run (`:1028-1148`) | the folder; no field cites a page | no | as artifacts | `artifact.update`; a corrected artifact survives a re-run (`:713-751`) | site export prints artifacts as text (`export_service.py:938-944`) | artifact search | the catalogue timeline is a markdown artifact, not the time view |
| Tables (Extract Table, Extract Accounts) | a `table` artifact (`workflows/tools/table_extract.py:33`) | the document; no cell names its line or region (#5490) | no | as an artifact | `artifact.update` | as text | artifact search | not the table view |
| Translation, modernisation, regest | `translation` artifacts (`workflows/tools/text_translate.py:54`, `translate.py:25`); the historical presets (`paleo_translate_english`, `paleo_modernizacion`, `paleo_regesto`) run `analyze` and land as an **`analysis`** artifact plus `metadata["analysis"]` (`workflows/tools/analyze.py:31-36`) | the document; a line can hold a translation reading but no tool writes one (#3325) | the document translation in the immersive view only (`layers.translation.document-artifacts-still-shown`) | as artifacts | `artifact.update` | as text | translation artifacts searched | — |
| Kinds and attributes (Find the Documents, prototypes) | `Document.prototype_key` and `attributes`, a plain dictionary (`models/__init__.py:308`, `:323-329`); only the diary tool sets them (`diary_entries.py:591-592`); `classify` writes a `classification` artifact and never a prototype (`workflows/tools/classify.py:32`) | the node; an attribute value cites nothing | no | effective attributes (`documents.py:1250-1281`) | through the node's attributes | **no**: the record stream omits `attributes` and `prototype_key` | no | dataset grid columns |
| Groups of documents (Find the Documents, Group Same Documents) | group nodes (#5303); proposals are not stored yet (#5550) | pages, by membership | canvas | as nodes | Group / Ungroup (audited) | as the tree | as nodes | canvas |

**Every other shipped output.** The 58 default workflows (`resources/default_workflows/`) and their
tools reach the page model in one of five ways:

| Reaches the page as | Workflows (tool) |
|---|---|
| a pass of segments, readings on lines | Detect Regions (Kraken, VLM, Apple), Read Lines Kraken + Vision, Transcribe Kraken / HTR, Backfill Text Geometry (`detect_regions`, `merge_geometry`), Recombine Segments |
| page text, then tied to lines (#5444) | every Transcribe preset, Capture–OCR–Transcribe, Transcribe Auto-detect (`transcribe`, `update_page_content=True`, `workflows/tools/transcribe.py:42`) |
| page text over the top, never tied | Paleographer Review, Review Pipeline, Economy HTR (`transcribe_review`, `economy_htr`; #5486) |
| nodes (children of the page or folder) | Split Diary Entries (entry nodes), Split Pages, Split Images, Split Chapters, Segment Images, Group Same Documents |
| document fields | Work Out Dates (date columns), Extract Geo (`geo_points`) |
| KG rows tied to the document | Catalogue stages 2–5, NER per page, Extract Events Timeline |
| a document-level artifact only | Archival Summary, Extract Table, Extract Accounts CSV, Translate / DeepL / Translate Review, Translate Reviewed Transcription, Translate to English (Historical), Modernización, Regesto, Clean Up Text, Describe Visual, Convert to Markdown / HTML / SVG, Transcribe Auto-detect's script class |
| image renditions (correctly: an image is the output) | Prepare / Enhance / Fuzzy-clean / Remove Background / Rotate images |

So the onboarding operator's remark holds: outside reading and line finding, results land as
artifacts on a document, not on the page.

**What level a workflow can run on.** A run takes a typed selection of three kinds only, `documents`,
`folder` and `collection` (`workflows/selection.py:31-45`, `api/routes/workflow_execution/schemas.py:60`).
A region promoted to a node (a diary entry, a drawn crop) runs as a document and gets its own pixels
(`media/region_crops.py:1-15`). Nothing else does: no selection of segments (these three lines, a word,
a sign), no group of documents as a case (it runs as a folder), no character. Inside a run, a node is
given a page image or a region node's crop (`files`), or the page's text (`text`, `page_content`); only
the line readers take each line's crop (`llm/working_lines.py`). No node is given a segment's reading,
and an artifact can only name a document (`Artifact.document_id`, `models/__init__.py:800`), so a
result cannot attach below the document even when it was made from a line.

#### The problems, ranked

1. **A fact has several homes, and they disagree after a correction.** A page's date is in the
   document's columns, in a `dates` artifact, and for a diary also in the entry's `attributes.date`
   and `metadata.date_text`, the catalogue's `dates` section and its `catalogue.timeline` artifact
   (`date_extract.py:457-510`, `diary_entries.py:592-597`, `catalogue.py:1110-1119`, `:1478-1531`).
   A name is an entity and a row in a `people` artifact (`extractors.py:1212` and `:3052`); a place is
   an entity's `place_values`, a `geo` artifact and `metadata.geo_points`. Correcting the entity leaves
   the artifact; and search's `people:` scope reads the artifact (`search/core.py:611-634`), so a
   corrected name is still found under its old spelling.
2. **Names and statements float free of the page.** Names keep only the document
   (`extract_entities_only.py:423-425`); statements keep offsets into page text that a later reading
   changes (`extractors.py:2752-2757`); the per-segment read exists and finds nothing because no writer
   names a segment (`segment_readings.py:1730-1772`). Quotations are anchored by their surrounding
   sentence, not the quoted words.
3. **Text-shaped outputs are not readings.** A translation, a modernisation and a regest are
   artifacts; the three historical presets even file a translation as `analysis` (`analyze.py:32`), so
   nothing that looks for a translation finds it. #3325 has the reading kind and no writer.
4. **Attributes cite nothing.** `Document.attributes` is a plain dictionary; a judgment's judge,
   parties and date (Istmina) or a catalogue field could be filled, but not tied to the words that say
   so, and the catalogue writes its narrative over the folder's own text (`catalogue.py:829`).
5. **Nothing extracted is drawn on the page.** The Preview draws boxes, regions, marks and inline text
   (`layers.preview.draws-today`); names, statements, dates, entries' headings and table cells have no
   layer (#1659, #5418), so the Inspector cannot lead from a fact to its ink or back.
6. **Export drops what was extracted.** The record stream's document row has no date, attributes or
   prototype; claims leave without offsets, anchor or time; entities without mentions
   (`export_service.py:139-214`). TEI does not write `persName`, `placeName` or `date` in the lines;
   W3C annotations are made for a person's marks only.
7. **Diary entries copy the page.** An entry holds its own copy of the text and a rectangle; it is not
   the set of lines it covers, so a corrected line does not reach the entry and the entry's date is
   not on the timeline (`diary_entries.py:580-604`). Account pages' dated items are dropped (#5559).
8. **A run cannot be aimed below the document, and its output cannot attach there.** Three selection
   kinds (`selection.py:31-45`); `Artifact` names a document only.
9. **Machine writes to document fields are plain saves.** Work Out Dates saves the columns with
   `db.save` (`date_extract.py:490`), so the date a run set is undone only by a person's own edit,
   not by taking the run back (`safety/run-take-back.md`).

#### The target

Every extracted fact is **one typed record**, tied to the **segment span** it came from (a segment
and a stretch of one of its readings, or a set of segments), **shown as a layer** on the page,
**corrected in place** through one audited, undoable action, and **read by every view and export**
from that one record. Anything else (a document's date column, an entry's date, a catalogue's
people list, a map point, a grid cell) is worked out from it, never stored beside it. The record
kinds are the ones the model already has: a **reading** (text about a segment: transcription,
translation, normalisation, regest), a **mention** (a name or a date at a span), a **statement**
(resting on mentions), a **logical unit** (an entry, a document inside a document, a table row: a
named set of segments), and an **attribute value** (a field of a prototype, whose value cites a
mention or a span). A run can be aimed at any level of the ladder, and its output attaches at the
level it was made for.

#### Behaviours

- `source.extract.one-fact-one-home` — **[BROKEN]** (#5467; #5597) a fact is stored once; a
  document's date, an entry's date, a catalogue's lists, map points and per-section artifacts are
  read from the mentions, statements and attribute values, never written beside them. Today a date has
  up to six homes and a name two (problem 1).
- `source.extract.names-as-mentions` — **[OK]** (#5488, #4932) a name found is a mention: a segment,
  a reading and a character span, joined to its entity; a spaCy span is kept, a model's name is found
  in the reading and tied the same way, and an unfound name is kept as unanchored and says so.
  *Built (#5488): each place the page text writes the name is a supporting source on the entity with
  its span (`extractors.write_mentions`); through the tie seam (`tie_text.line_spans`, `line_anchor`)
  it names the line it is on and the reading the tie gave that line, and is read as a mention by
  `GET /api/segments/{id}/statements`. spaCy's spans are kept, every occurrence (`EntitySpan.occurrences`,
  cut to the name where a person's span ran on into a descriptor) and its aliases'; a language model's
  name and aliases are found as written, whole words, exactly (`extractors.name_spans`), never loosely.
  A page not tied keeps the span with no line, and a rerun after the tie names the line in place of a
  second mention. A name not written on the page is kept unanchored with `mention_unanchored_reason`.
  Writers: Extract Entities (`extract_entities_only`, spaCy and model paths) and every writer through
  `_write_kg_rows` (the section extractors, Extract All, Extract Statements, KG Writer). Pinned by
  `fichero-server/tests/unit/workflows/test_names_as_mentions.py` (4 tests). Not built: the NLP draft
  at import (`importers/nlp_draft.py`) passes no page text to the writer, so its names stay on the
  document.*
- `source.extract.statements-on-segments` — **[PARTIAL]** (#4932) *Built: the read from a segment
  (`GET /api/segments/{id}/statements`) and the Inspector section; every claim written through
  `_write_kg_rows` whose words are found on the page (exactly or by the closest real span) fills
  `segment_id`, `representation_id` and the span within that reading on its anchor, the line its words
  start on, when the page is tied (#5488; pinned by `test_names_as_mentions.py::
  test_a_statement_rests_on_the_line_its_words_start_on`). Not built: a statement spanning several
  lines names only the first; a statement resting on the mentions it joins (no link from claim to
  mention rows).* A statement rests on the mentions it joins and on the segment span of its evidence.
- `source.extract.quotes-on-their-words` — **[OK]** (#5598) a quotation is a span on the
  quoted words themselves, with its speaker as a mention; the surrounding sentence is context, not
  the anchor. *Built (#5598): the quotes writer (`extractors._anchor_quotation`, the quotes section of
  Extract Quotes and Extract All) anchors the claim on the quoted words' span in the page text (the
  sentence first, then the page, then the closest real span, labelled `quote_anchor: fuzzy`); words
  not on the page leave the quotation unanchored with `quote_unanchored_reason`, never on the
  sentence, which is kept as `quote_context`. Through the tie seam (`tie_text.line_spans`) the anchor
  names the line the words start on and the reading measured, with every line covered in
  `quote_lines`. The speaker is the model's name only (no "X said" guess); where the attributing
  sentence writes it, it is a supporting source on the entity on its span and line, read as a mention
  by `GET /api/segments/{id}/statements`. Pinned by `fichero-server/tests/unit/workflows/
  test_quotes_on_their_words.py` (4 tests). The `quotes` artifact beside the claim is
  `one-fact-one-home`'s (#5597).*
- `source.extract.date-on-its-heading` — **[PARTIAL]** (#5518, #5557) *Built: a page's date is read
  from its heading, recorded with its status and conflicts. Not built: the heading as a date mention
  on its line.* The page's date is a date mention on the heading's line, and the document's date
  columns are worked out from it.
- `source.extract.date-run-taken-back` — **[PARTIAL]** (#5597) a run's writes to a document's date
  are recorded under the run and undone when the run is taken back, as its readings are. *Built:
  Work Out Dates writes a page's four date columns only through the audited, undoable
  `document.write_extracted_date` action under the run's id (`date_extract._write_date`); undoing
  those rows (`POST /api/actions/audit/{id}/undo`, newest first) puts each page's previous date
  back, an empty one included. A person's date wins: the run never changes its columns (a
  disagreement is recorded beside it, and taken back with the run), a machine write that would
  replace it is kept and says so, and a date a person (or a later run) set after the run is kept
  when the run is taken back. Redo puts the run's date back. Tests:
  `fichero-server/tests/unit/workflows/test_date_run_taken_back_5597.py` (the shipped preset through
  the real runner; the person's date and the take-back through the routes). Left: the run's `dates`
  artifacts are still saved bare and stay after a take-back; taking a whole run back as one step
  is #5245.*
- `source.extract.entries-are-units` — **[PARTIAL]** (#5467; #5601) *Built: entry nodes with a
  date, a region and a prototype. Built (#5601): on a page tied to its lines, the one splitter
  (`diary_entries.split_pages_into_entries`) records the lines each entry covers, in order
  (`metadata.lines`, the tied lines under the entry's span of the tied page reading), and the
  documents routes (`GET /api/documents/{id}` and `/children`) read the entry's text from those lines'
  counting readings, so a correction on a line is the entry's text without a re-run; a page not tied
  keeps the copied text and the entry says it is not on lines (`metadata.text_from`); a re-run matches
  the entries and updates their lines. Pinned by `fichero-server/tests/unit/workflows/
  test_entries_over_lines_5601.py` (2 tests). Not built: the date as the mention on the heading, the
  entry as its own unit row (it is still a child node with a stored text snapshot that search and
  export read), a line shared by two entries split at the heading, and entries split before the tie
  (they gain lines only when re-run).* An entry is a logical unit over the lines it covers; its text is
  read from those lines, its date is the mention on its heading, and it sits on the timeline.
- `source.extract.account-lines-are-rows` — **[GAP]** (#5559, #5490) the dated items of an account
  page become table rows on their lines, each date a mention.
- `source.extract.tables-on-cells` — **[GAP]** (#5490) a table is a logical unit; each row and cell
  names its segments; the table view and the CSV are read from it.
- `source.extract.text-outputs-are-readings` — **[PARTIAL]** (#3325, #5490; #5599 for the
  `analysis` presets) *Built (#5599): a tool's save config names the kind of reading its output is
  (`LLMToolConfig.reading_kind`), and the one artifact save writes that reading on the node it was
  made from (`representation.create`, derived from the run's artifact, under the run). Translate,
  Translate Text and Translate Review write a `translation` reading; the three historical presets name
  theirs on the Analyze step (`translation`, `normalized_text`, and a new seeded kind `regest`), file
  their artifact under that kind instead of `analysis`, and no longer copy it into
  `metadata["analysis"]`. The same seam for the other text tools: Describe and Caption write a
  `description` reading of the page; Summarize, Summarize File, Summarize Folder and Summarize
  Collection a `description` reading of what they summarise; Clean Up Text a `normalized_text`
  reading; Rewrite a `paraphrase` reading (a new seeded kind), or a `translation` when it names a
  target language; AI Convert a `markdown`, `html` or `svg` reading (LaTeX and CSV have no kind and
  stay the artifact). A read the read guard flags writes no reading. Pinned by
  `fichero-server/tests/unit/workflows/test_text_outputs_are_readings.py` (each preset and each tool
  through the real runner, read back through `GET /api/content-representations/document/{id}`). Not
  built: the reading on the page's lines rather than on the page (#3325); the run's artifact is still
  saved beside it as its record. Not readings, left in the guard's baseline with their reason: Scene
  (a classification, an attribute), Diagram (a parsed structure), Questions (generated questions), and
  Import Artifacts (it copies the page's own imported text, which is already the page's text).* A
  translation, modernisation or regest is a reading of its kind on the lines (or on the page when it
  has no lines), never an artifact; the historical presets stop filing a translation as `analysis`.
- `source.extract.places-one-home` — **[BROKEN]** (#5597) a place's coordinates live on its
  entity; a document's map points are worked out from its place mentions; the `geo` artifact and
  `metadata.geo_points` are retired.
- `source.extract.attributes-cite` — **[PARTIAL]** (#5365, #5550; #5600) a prototype attribute's
  value (a judgment's judge, parties, date, ruling; a catalogue field) is a typed value that cites
  the mention or span it was read from; a person's value cites nothing and outranks a machine's.
  *Built (#5600): each attribute key (and the node's kind, key `prototype`) records who set it in
  `Document.metadata.attribute_sources` (`workflows/attribute_sources.py`): a person's `{"by":
  "person"}`, set by `PUT /api/documents/{id}` for every attribute it adds, changes or removes and
  by `PUT /api/documents/{id}/prototype`; a run's `{"by": "machine", "tool", "step", "run_id",
  "artifact_id", "provider", "model", "said", "cites"}`. A run writes a key only when a machine set
  it or it is empty and unclaimed, so a person's value (or one from before) is never overwritten.
  Scene writes its answer as page attributes (`scene`, `scene_<field>`) citing its run, through the
  tool seam `LLMToolConfig.attribute_key`. Pinned by `fichero-server/tests/unit/workflows/
  test_attributes_cite.py` (the real runner, read back through `GET /api/documents/{id}` and
  `/effective-attributes`). Not built: no writer yet cites a mention, segment or span (`cites` is
  empty: Extract, a judgment's fields, the catalogue's fields, keywords, sentiment, tags), the sources
  are not on the effective-attributes response or the Inspector, and the other page judgments
  (quality, style, safety, colours, language) still write only their artifact.*
- `source.extract.kinds-proposed-as-prototypes` — **[PARTIAL]** (#5550; #5600) a document's kind,
  whether from Find the Documents or `classify`, is a proposed prototype on the node, accepted by a
  person, not a `classification` artifact. **Ruled by the maintainer 2026-10-08: a run's kind is
  proposed for the person to accept, not assigned.** *Built (#5600): `classify` records its answer
  as a proposed kind on the node (`metadata.proposed_attributes.prototype`, shown by `GET
  /api/documents/{id}`: the prototype key, the model's label, `state: proposed`, and its evidence —
  the run, its record (artifact) and what the model said); nothing is assigned and no prototype is
  made until a person answers. `POST /api/documents/{id}/proposed-kind/accept` assigns it through
  the audited `document.assign_prototype` (the prototype made through `classification.create` when
  the project has none of that name), its source the run with `accepted_by` the person, so no later
  run proposes over it; `POST /api/documents/{id}/proposed-kind/reject` (the audited
  `document.reject_proposed_kind`) keeps it marked `rejected`, and the same kind is not proposed
  again. Each answer is undone as one (`/api/actions/audit/{id}/undo` puts the proposal back). A
  later run's proposal replaces one nobody answered, never a kind a person chose; a person choosing
  another kind sets the proposal aside. The artifact stays as the run's record. Pinned by
  `fichero-server/tests/unit/workflows/test_attributes_cite.py` (the real classify run with a stub
  model, and the routes). Not built: the app's Accept / Reject in the Inspector; Find the Documents'
  kinds keep their own proposal (`finddocs.*`); `classify_text` and `classify_script` still write
  only their artifact.*
- `source.extract.catalogue-never-overwrites-text` — **[OK]** (#5365; #5599) the catalogue's
  narrative is a reading of kind description on the folder, never written into its `page_content`.
  *Built (#5599): `catalogue.py` writes the narrative through the one reading writer, derived from
  the `catalogue.narrative` artifact; a re-run retracts the machine description it replaces, so the
  folder is described once. Pinned by `fichero-server/tests/unit/workflows/
  test_text_outputs_are_readings.py` (the shipped Catalogue preset through the real runner). Libraries
  whose folders already hold an earlier run's narrative as their text are not rewritten.*
- `source.extract.shown-as-layers` — **[GAP]** (#1659, #5418) names, statements, quotations, dates,
  entries and table cells each have a layer in the Preview, drawn on their segments, with the empty
  case said.
- `source.extract.inspector-leads-to-ink` — **[PARTIAL]** (#4932) *Built: the statements section on
  a segment.* Selecting any extracted fact shows its source span and selects it on the page; selecting
  a segment lists every fact resting on it.
- `source.extract.corrected-in-place` — **[PARTIAL]** (#4834; #5602) *Built: `claim.patch`,
  `entity.update`, `document.set_date`, `artifact.update` are audited.* A person corrects a fact from
  its mark on the page or from the Inspector, through the one action for its record, and every view
  shows the correction at once because none holds a copy.
- `source.extract.search-reads-the-record` — **[PARTIAL]** (#5597) *Built: `people:`, `places:`,
  `organizations:` and `events:` read the entities (name and aliases, accent-blind; a merged-away entity
  is its survivor; a rejected or suppressed entity is not found) and reach the documents through the
  entity's mentions and source documents, each hit naming the entity (`metadata.entity_id`) and the
  segments its mentions sit on (`metadata.segment_ids`); the artifact copy is not read for these scopes
  (`api/routes/search/core.py` `_entity_scope_results`; tests
  `tests/unit/search/test_search_reads_the_record.py`). Not yet: `dates:` and `keywords:` still read
  their artifacts (no entity home until `one-fact-one-home`); the unscoped name bridge and "did you
  mean" still read artifacts; a hit is a document with its segments, not a segment result.* A scoped
  search (`people:`, `places:`…) reads entities and mentions and lands on the segment, not on artifact
  JSON and a page.
- `source.extract.exported` — **[PARTIAL]** (#5490; #5603) the record stream carries dates,
  prototypes, attributes with their citations, mentions with their spans, and claims with their
  anchors; TEI writes names and dates inline in the lines; W3C/IIIF writes mentions and statements as
  annotations with segment and text selectors. *Built (#5603): one reader per record in
  `export_service` (`record_mentions`, `claim_record_columns`, `document_record_columns`,
  `anchor_columns`) that the stream, TEI and the annotation page all use. The stream (JSON Lines and
  Parquet, now with `mentions.parquet`) gives each document its date columns (`date_original`,
  `date_jdn`/`_end`, status, display, precision, source), its `prototype`, `attribute_values` with who set
  each (`metadata.attribute_sources`: by, tool, run, model, cites) and its own readings by kind (not a
  line's); each mention its entity, span in the page text, line (`segment_id`), reading (`reading_id`),
  span in that reading, unanchored reason and the run that found it; each claim the same anchor columns,
  its date (`date_text`, `date_normalized`, time scope), quotation kind, speaker, provider and model.
  TEI (`page_export._record_on_lines`, `formats/tei.RECORD_MARKS`) writes a mention as
  `persName`/`placeName`/`orgName` (other types `rs type`) with `@ref="fichero:entity:<id>"`, and a date
  claim's words as `<date when>` inside its statement's span, only on the reading the span was measured
  on (or one with the same words there); a line written as words or rival readings says so in the loss
  report. `GET /api/documents/{id}/annotations.jsonld` adds each anchored mention (`identifying`, body the
  entity) and each claim on the page (`describing`, its date as a `tagging` body), the target the line
  with `TextPositionSelector` + `TextQuoteSelector` (and the reading), else the page with the words, the
  `creator` the run's model (`Software`, `fichero:run:<id>`). Pinned by
  `fichero-server/tests/unit/core/test_export_reads_the_record.py` (4 tests, through
  `POST /api/export/parquet`, `GET /api/documents/{id}/export/tei` and the annotation page). Not built:
  the IIIF manifest's own annotation lists, entity records naming their mentions in RDF, names on a line
  held as words, attribute values citing a span (no writer cites one yet, `attributes-cite`), and dates
  as mentions (`date-on-its-heading`): a document's date is exported from its columns.*
- `source.extract.views-read-the-record` — **[PARTIAL]** (#5603) the time view, the map, the
  table view and the dataset grid read the same records (date mentions, place entities, logical units,
  attribute values); the catalogue's markdown timeline is retired into the time view. *Not changed by
  #5603's first slice: the time view already reads the document's date columns (the one place a
  document's date lives today), and the map reads `metadata.geo_points`, a copy; moving it onto place
  entities is `places-one-home` (#5597), not a few lines.*
- `source.extract.run-on-any-level` — **[PARTIAL]** (#4949; #5604) *Built: documents, a folder,
  a collection, a region node with its own crop; a `group` selection (its member documents in the
  group's own order); and a `segments` selection at any level, each segment resolved by the files
  source (`sources.segment_work_units`) to its picture cut by the one cutter
  (`media/segment_pictures.py`) and its counting reading. Only the readers wired to a segment
  (`tool_outputs.SEGMENT_READERS`: Transcribe, Handwriting, Caption, Describe) run on one; any other
  step is refused before the run in words ("Classify runs on pages, not on a line"), never run on the
  whole page. Pinned by `fichero-server/tests/unit/workflows/test_run_on_any_level_5604.py`. Not built:
  a logical unit as a selection; text steps (translate, clean) on a segment's reading; the segment's
  outline mask and straightening for a reader.* A run's selection can also be a set of segments
  at any level (regions, lines, words, signs), a group of documents (a case), or a logical unit; the
  server resolves it, and each node is given what it needs for that level: the segment's picture cut
  to its shape, its chosen reading, or both (`source.chain.segments-to-any-reader`).
- `source.extract.outputs-attach-at-their-level` — **[PARTIAL]** (#5490; #5604) *Built: a reader
  run on a segment writes what it read as a reading ON that segment (a transcription, or the step's
  reading kind such as a description), never the page's text; the run's artifact stays on the page as
  `segment.<type>` with no boxes, so nothing that takes a page's transcription from its artifacts
  takes a line's (`llm_base._write_segment_reading`; pinned by
  `fichero-server/tests/unit/workflows/test_run_on_any_level_5604.py`). Not built: mentions and
  statements found on a segment run (the extractors are not wired to a segment).* A
  result made from a
  segment attaches to that segment (a reading, a mention); one made from a document or group attaches
  there (an attribute value, a description reading); `Artifact` is kept as the record of a run, not as
  the home of what it found.
- `source.extract.every-output-declares-its-anchor` — **[PARTIAL]** (#5490; #5596) *Built: every
  registered tool (144) declares what it writes and where it attaches in
  `workflows/tool_outputs.py`, stamped on `ToolDef` and served read-only as `writes` / `anchors_at`
  on `GET /api/workflows/tools`; `scripts/check_tool_outputs_declared.py` fails an undeclared tool
  and an artifact-only tool missing from its baseline (34 known gaps after #5599, each naming its slice), pinned
  by `fichero-server/tests/unit/scripts/test_check_tool_outputs_declared.py`. Not built: the
  table above generated from the declarations.* Every registered tool declares which record kinds
  it writes (pass, reading, mention, statement, unit, attribute, node, rendition); a guard fails a
  tool that writes only a document artifact without a recorded reason, and the table above is
  generated from the declarations.

#### Build order (slices, ranked)

1. **Declare every output** (`every-output-declares-its-anchor`): registry metadata and the guard,
   with today's artifact-only tools listed as known gaps. Cheap, and it turns this review into a
   checked list.
2. **Names and statements on segments** (`names-as-mentions`, `statements-on-segments`,
   `quotes-on-their-words`; #5488, #4932): keep spans, resolve them through the page's working lines
   (the tie seam, `checking/tie_text.py`), write segment and reading on each anchor.
3. **One home for each fact** (`one-fact-one-home`, `search-reads-the-record`, `places-one-home`,
   `date-on-its-heading`, `date-run-taken-back`): date mentions on headings with the columns derived;
   per-section artifacts and `geo_points` derived or retired; scoped search on entities.
4. **Text outputs as readings** (`text-outputs-are-readings`, `catalogue-never-overwrites-text`;
   #3325): translation, modernisation, regest and catalogue narrative become readings; the `analysis`
   misfiling ends.
5. **Layers and the Inspector** (`shown-as-layers`, `inspector-leads-to-ink`, `corrected-in-place`;
   #1659, #5418): needs 2 and 3.
6. **Attributes that cite** (`attributes-cite`, `kinds-proposed-as-prototypes`; #5365, #5550): the
   judgment's fields for Istmina, the catalogue's fields, Find the Documents' kinds.
7. **Units over segments** (`entries-are-units`, `account-lines-are-rows`, `tables-on-cells`; #5559,
   #5490): entries, inserted documents (`finddocs.inserts-are-ranges`) and table rows as logical units.
8. **Run on any level, attach at that level** (`run-on-any-level`, `outputs-attach-at-their-level`;
   #4949): a `segments` and a `group` selection kind, node inputs by level.
9. **Export and views** (`exported`, `views-read-the-record`; #5490): the record stream, TEI inline
   names and dates, W3C annotations, the time view and map on the one record.

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
idempotently, safe to run twice, nothing rewritten); the **data** is converted a whole project
at once, in the background, by the running app's engine, after a snapshot, a page at a time
(ruled 2026-09-20, replacing "on each page's first edit"; an edit to a page not yet reached
converts that page there and then); every existing artifact, claim and highlight
stays resolvable; each slice that changes stored shape has a test that opens a library made
before the change.

### Slice 1 — one way to read a source's segments (engine only; writes nothing)

One engine call returns the segments of a source, whether they still live in today's block
of boxes or, later, in segment records. The caller cannot tell which. Because it writes
nothing, it cannot harm a library.

- **Behaviours:** `source.seam.read-either-store`, `source.seam.provisional-ids-refused`,
  `source.segment.names-its-image`, the "opening writes nothing" half of
  `source.store.edit-converts-its-page-first` (was `…ids-on-first-edit`), and the engine half of
  `source.one-store`.
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

### Slice 6 — converting one page (built; the unit of the whole-project conversion)

One action converts one page's boxes into segment records, with or without an edit; undo takes
back the edit and keeps the records. By the ruling of 2026-09-20 this is no longer how a
project is converted; it **survives** as two things: the action the whole-project conversion
runs once for each page, and the way an edit to a page not yet reached converts it at once.
Nothing built for it is thrown away. The rules are in `segments-and-geometry.md` ("Converting
one page: the rules"). Behaviours: `source.store.edit-converts-its-page-first`,
`source.store.never-converted-by-a-migration`, `source.store.one-page-per-conversion`,
`source.store.undo-first-edit-keeps-conversion` (and four more added 2026-09-20; see the
build notes for slice 6).

### Then, in dependency order

7. Shapes beyond the rectangle on `SourceAnchor` (point, open path, several shapes, curved
   baseline), the derived box, polygon crops and straightened line pictures.
8. Readings on segments: `ContentRepresentation` gains a segment id; the list of kinds opens;
   "which counts" is worked out, never stored as a flag. **Ruled 2026-09-20 to come before any
   whole-project conversion**, so that a page's words live on its segments and deleting a
   transcription keeps working.
8b. **Converting a whole project** (ruled 2026-09-20): started by itself when a project opens,
   in the background, by the running app's engine, after a snapshot that has been read back
   and checked; a page at a time with slice 6's action; safe to stop, start and repeat; refused
   when the disk is short; a report for each project. Rules and behaviours
   (`source.convert.*`) in `segments-and-geometry.md`; build notes in
   `build-notes-readings-cascade-orders.md`. **Nothing of slices 6 to 8b reaches the app until
   the whole programme is done.**
9. The cascade (language, script, direction), extending `language_policy.resolve_language`,
   answering with where each value came from.
10. Reading orders, flows and typed links.
11. The format model and its harness (validate, loss report, round trip); then PageXML; then
    ALTO; then YOLO labels. TEI after those, with its own reader and writer.
12. The editor's performance trial: a hard gate. The numbers were ruled and the METHOD was
    not, which is how a gate becomes an argument; `segment-editor.md`'s "Slice 12: the speed
    trial, and how it is measured" now states the fixture, the machines, the run count, what
    counts as idle and what the result is compared with (`source.perf.*`).
13. The editor: one overlay, one input seam, every edit an action.
13b. Editing a page by its text (direction given 2026-09-20; design in `segment-editor.md`,
    `source.textedit.*`): the lines' readings as editable text beside a linked Source view;
    Return splits, Backspace joins, typing is a new reading, whole lines move in the reading
    order. Needs 8, 10, 12 and 13. Recommended home: the Reader; the choice is open.
14. Hands, campaigns, certainty and damage, letterforms, declared signs: independent of each
    other, any order, after 8.
15. Recordings; maps and control points; the canvas: self-contained, any time after 7.

**Ruled 2026-09-27** on the four items that had waited on the maintainer:
- **Rights records: go ahead.** They sit beside the permissions that already exist, and belong with
  slice 14.
- **A Segments pane: go ahead.** It sits beside the ruling that there is no browser pane kind, and
  belongs with slice 13 (the editor), after the speed trial (12).
- **Recipes beside the shipped default workflows: go ahead.** They belong to the workflow system,
  not this programme, so they are noted here and not built in it.
- **An action's audited record holding a researcher's own words: NOT approved, and ruled out.** The
  record sits inside the tamper-evident chain, which a purge could not then reach. A researcher's
  words live in readings and notes, which can be withdrawn and purged, and never in an audit row.

**Slice order after 11 and #5132** (ruled 2026-09-27): **12** (the speed trial, a hard gate on the
editor's UI) → **13** → **13b** → **14** → **15** (maps) → **8b** (whole-project conversion), and
8b only after the maintainer has tested.

**Build milestones proposed** (the spec set stays on `source-model`, 322): *source-model:
identity and storage* (slices 1 to 6); *source-model: shapes and readings* (7 to 10, 14);
*source-model: formats* (11), with *TEI* apart; *source-model: the segment editor* (12, 13);
*models, chains and projects*; *the synced folder*; *training and measuring*; *recordings*;
*rights and access*.

## Behaviors

The foundation has two of its own. Everything else is in the slices.

- `source.one-store` — **[OK]** (#4919; engine half pinned by `tests/unit/api/test_segments_route.py::TestReadEitherStore::test_one_provisional_segment_per_box_rect_for_rect`, app half by `fichero/Tests/Unit/general/Models/SegmentMappingTests.swift` (52 passing)) only one engine call returns a segment's shape, and only one returns
  its picture; the Source view, Reader, Inspector, agents, training and export all use them,
  and the app keeps no second store of segments.
- `source.builds-on-the-anchor` — **[OK]** (#4925 closed; `test_readings_across_split_and_merge.py::TestTheAnchorCanNameWhatItPointsAt`) a segment's place is a `SourceAnchor`, and the other three
  ways of saying "where" (`OCRGeometryBox`'s own box, `AgentNoteSourceAnchor`, and any new
  one) are retired onto it, slice by slice; no new addressing scheme is introduced. This is a
  migration, the largest in the programme, and each slice that retires one says so.

- `source.model.one-line-pass` — **[PARTIAL]** (#5487, #5444; ruled 2026-10-05, #5467) *Built
  (2026-10-06): a reader of lines (`read-a-line`: a Kraken reader, or a vision model reading line by line)
  reads the lines of the page's working pass (`llm/working_lines.py`: the first pass in the working-pass
  ranking with shapes and live lines), on their own outlines and baselines (a line with none is read
  along three quarters of its box), and writes each line's words as a reading on that line
  (`representation.create` under the run, `workflow`, derived from the reader's page artifact, which
  keeps the page text and no geometry, marked `read_onto_pass`); lines are found only on a page with
  none. Kraken's regions are kept: its lines carry their region (`parent_box_index`) and conversion
  nests them (`parent_segment_id`). The tie (`source.job.tie-text-to-lines`) writes onto the same lines.
  A recipe's read step counts as done on a page whose lines carry its model's readings, and the
  training set finds a teacher's readings on those lines. Pinned by
  `fichero-server/tests/unit/workflows/test_one_line_pass_read_many.py`. Not built: correcting (#5486)
  and the other producers in the table; nesting for Apple and VLM boxes (#5489); the cluster reader
  (`remote_read/runner.py`) still drops Kraken's regions.* Finding lines makes the page's one line pass;
  every reading after it adds readings to those lines and never makes a second line pass, and a model's
  regions stay the parents of the lines found in them.

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
   segments once, undoably. **Replaced on 2026-09-20** (see below): a whole project is
   converted at once in the background; the first-edit path stays as the unit and as the way
   an edit gets ahead.
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
    Inspector. No second settings window. **Ruled in direction 2026-09-20, detail open:** a
    project settings window holds the project-wide defaults; the Inspector edits the values of
    a project, a document and anything below; and every value shows where it came from. One
    resolver underneath both (the cascade's), so the two places can never disagree.
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

### Rulings of 2026-09-20

Paraphrased; each replaces or confirms what the set said before.

1. **How an existing project is converted: all at once, by itself, when it opens, after a
   snapshot.** This replaces ruling 2 of 2026-09-19 as the behaviour people will meet. The
   order is ruled too: readings on segments first (slice 8), then the whole-project
   conversion (8b), so deleting a transcription never stops working. Converting on first edit
   stays as the engine's mechanism meanwhile. None of it reaches the app until the programme
   is done; it is to be built steadily, not hurried.
2. **Every result with boxes becomes its own pass.** Confirmed.
3. **Undoing a page's first edit undoes the edit and keeps the records.** Confirmed.
4. **Deleting a converted result stays refused until readings are on segments.** Confirmed;
   the refusal ends with slice 8 (`source.convert.words-move-with-the-boxes`).
5. **Each audit record is split in two**: a chained part (who, what, when, ids, version
   numbers, a keyed fingerprint of any content) and a content part outside the chain that a
   purge can blank, leaving the chain checkable. The fingerprint is keyed with a random value
   kept in the content part and blanked with it (this set's condition, accepted). This answers
   the set's questions 8, 17 and 23, and removes one of the two blocks on purge in
   `rights-and-access.md`. The parked safety set proposed the same split; it stays parked.
6. **A deleted pass goes to the Trash; a single deleted segment does not** (it is undone, or
   restored from its own history).

### Agreed with the safety set, 2026-09-20 (undo, Trash, the record; branch `spec/undo-trash`, not merged; since PARKED)

Answers to that set's requests. Each is this set's position; where it is the maintainer's to
rule it says so, and the manager carries any difference to the maintainer as one list.

- **One rule for redo in the shared undo route** (a step is reversed through its own inverse
  when it has one): **agreed.** It is what `source.editor.redo-works` needs, and ids never
  moving makes "restore" the right redo of a delete. The rule is theirs to specify; segments
  are one user of it. Condition: each action moved onto the rule gets a do, undo, redo, undo
  test on rows, not status codes.
- **The version store is one shape**: **agreed on the rule, not on sharing a table.** The rule
  (a preimage saved for each version, numbers only go up, a restore writes a new version, a
  write names the version it expects) is the one to follow for notes, statements, entities and
  workflow definitions. `SegmentVersion` itself is typed to a segment's fields and is not a
  general table. Version rows are outside the record's chain, so a purge can reach them.
- **A deleted segment is "undo only", not a Trash item**: **agreed.** It is soft-deleted, still
  resolves through its forwarding note, and comes back by undo or from its own history in the
  editor. A deleted **pass** is a body of work a person might go looking for: **ruled
  2026-09-20, it goes to the Trash.**
- **Words in the record** (this set's questions 8, 17 and 23): the joint proposal, a chained
  part (who, what, when, ids, version numbers, a fingerprint) and a content part outside the
  hash that a purge can blank, was agreed as the proposal and **ruled 2026-09-20: adopted**, with
  this set's condition.
  It would unblock purge in `rights-and-access.md`. One condition from this set: the
  fingerprint must be keyed with a random value kept in the content part and blanked with it.
  A plain fingerprint of a short reason or a single word can be found by trying every likely
  word, so the chain would still give the words away.
- **Merge, split and carry take the expected version**: **agreed**, and so do their inverses.
  See "Owed after the redo reviews" in the identity and storage build notes.

### Still open

**No longer blocked on the maintainer: ruled 2026-09-27** (see the build order above). Rights
records and a Segments pane go ahead, and recipes go ahead in the workflow system. An audited
action record holding a researcher's words is ruled out.

1. **The Segments pane.** What it shows and does: a list, a strip or a grid of segment
   pictures with their readings; reordering by dragging; moving segments between regions and
   passes; editing a reading in place or in the Reader beside it. How it stays one code path
   with the Library's listing and the Source view's editor. **Approved 2026-09-27; built with
   slice 13.** Its design is part of that slice, and new shapes are escalated rather than
   assumed.
2. **Answered** (naming ruling 2026-10-03): Library becomes Project. **The Library pane's name** once a library is a project (for the rename spec).
3. **Answered** (maintainer 2026-10-04: rights = permissions enforce): Rights records are enforced through permissions. **Who may see restricted material among editors**: every editor, or only those a rights
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

## Future (ideas, not scheduled)
- (#4175) Audit whether the library DB reaches LanceDB through the DuckDB Lance extension and migrate if stable; structural, needs migration discipline.
- (#3311) Strategy seed (diplomatic vs normalized fields, historical dates); already folded as background into historical-text-normalization.md, remaining open questions are Future
- (#4637) Design-first brief for language/script/character-coverage tiers (loove, CLDR/Glottolog); owned by source/languages-scripts-signs.md and archival-data-model-plan.md, further work is Future
- (#4638) Design-first brief for edition kinds/methodologies/export formats; edition picker tracked in archival-data-model-plan.md (P4), full methodology model is Future

## Triaged from the backlog (2026-10-04)
- `source.store.every-model-registered` — **[GAP]** (#5055) every persisted model is in `Database._all_schema_models`, so a library open creates every table and index.
- `source.store.fresh-open-invariant` — **[GAP]** (#5056) a guard opens a real library and asserts every registered model's table and declared index exists.
- `source.certainty.damage-and-certainty-model` — **[GAP]** (#5097) slice 14's certainty and damage get behaviours: a scholar's certainty about a reading and physical damage on the page are two separate records.
