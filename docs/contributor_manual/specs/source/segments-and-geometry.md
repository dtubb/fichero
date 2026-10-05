# Source Model — Segments and geometry — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — part of the "How Fichero represents a source" section: what a segment is, how
> segments nest, how they are ordered and linked, and how a page can have several images.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first (the rulings and the words are there). The evidence is in `source-survey.md`.
> Every behaviour below is tagged **[GAP]** with its issue. Unless "What exists today" in the foundation says
> otherwise, everything here is design, not built. Tags and issues are added when the spec is
> approved and the milestone exists.

## Intent

A source is a page and the group of pages it belongs to. A segment is anything on it. This
slice says what a segment *is*: its identity, its shape, its place in the ladder, in a reading
order, in a pass, and its links to other segments. Readings, hands and certainty are in
`readings-and-apparatus.md`; language and signs in `languages-scripts-signs.md`.

## The design

### Identity

A segment has an id that lasts, and **an id never moves**. A segment keeps its id when it is
reshaped, moved, re-read or re-typed.

When a page is segmented again (by a model, an import, another scholar), the new run arrives
as a **new pass** with new segments and new ids. Nothing existing is replaced or renumbered.
A person can then say "this new line is that old line". That writes a **match**: a small
record of its own, with who said so and how sure. Readings, marks and statements can then be
carried across the match onto the new segment, and the trail stays visible. **Carrying a reading or a mark
copies it; it never moves**: the original stays on the old segment, the copy is recorded as
carried across that match, and undoing the carry removes the copies. **A statement is never
copied**: a claim in the knowledge graph is carried by giving **the same claim** one more
place it rests on, so the graph never says a thing twice. A match can be many to many (one old line
became two); a reading is carried only across a one-to-one match, and Fichero says when it
did not carry. A machine may
*propose* matches; only a person accepts them.

When segments are **merged**, one id goes on and the others leave a **forwarding note**
("merged into X"). When one is **split**, its id stays on one part and a forwarding note says
where the rest went. When one is **deleted**, it leaves a forwarding note that says so, and
the delete can be undone. Forwarding notes are never removed. Following an old id to where
that ink is now is **one call** (the engine walks the notes), the same from the app, MCP and
the command line. Forwarding notes never form a loop: the walk raises if it passes 64 steps
(it never silently stops short), and a merge whose target already forwards to the source is
refused, with the reason. If the trail
ends at a delete, Fichero says "this was deleted, by whom, when", and never shows nothing.

**How this grows from what exists.** Today's shared anchor (`SourceAnchor`) stays the one way
to say *where*. A segment is a record with an id whose *place* is an anchor; today's
boxes-in-a-list become segments. Today that is **not** one scheme: a box in an OCR result
carries its own rectangle and does not use the anchor at all, and a note made by an agent has
a small anchor type of its own. Moving those onto the anchor is part of this work (see
`source.builds-on-the-anchor` in the foundation). A segment is also **not** a `NodeRegion`:
that type says where a whole *node* sits in its parent (a diary entry on its page); a segment
is one of many records on a page. They share the same way of writing a rectangle, and
nothing else. But the anchor as
built cannot yet say everything this design needs (read on disk, `models/anchors.py`: one
rectangle, which must have width and height; one polygon, which must be closed with three
points or more; no id; no baseline). **What the anchor must gain** (the point is built since:
#4925, `source.segment.shape-kinds`; its first user is the ground control point in
`maps-and-georeference.md`)**:** a point; an open path; a
baseline that can curve; more than one shape; a stretch of time. (It already has a text
angle: `rotation`. The rectangle's own rules stay as they are for rectangles; each new kind
of shape gets its own check.) Its
`granularity` word and a segment's **kind** are the same idea and become one list.

### A reference you can cite

Every segment has one stable reference that names the project, the source, the segment and
its pass. It can be pasted into a footnote, a note or another program; it opens the segment in
the app, and resolves over MCP and the command line. It is what W3C annotation and IIIF
export write. If the segment has been merged, split or deleted since, the reference follows
the forwarding notes.

### Shape

- A shape is a **point**, a **line** (open path), an **area** (closed polygon; a box is the
  simplest one), or a **stretch of time** in a recording (for video, an area *and* a stretch
  of time). A segment may have more than one shape when the ink really is in two places (a
  word broken across a line end is one segment with two shapes).
- A line of writing also has a **baseline**, which may curve, and may have a top line.
- The **box** around a shape is always worked out from the shape, never typed in.
- **Angles, said once.** A crooked scan is straightened by making a new, deskewed image of the
  page; that is an image, not a property of a shape. A shape's own **text angle** says the
  writing in it runs at an angle on that image (a note written sideways in a margin).
- Every shape names **the image (or recording) it was measured on**. Coordinates are fractions
  of that image, from the top-left. The image record carries its pixel size, a checksum, and,
  where known, its **physical scale** (so a letter's height can be given in millimetres).
  Today geometry names its image once for a whole result; an image has its pixel size and a
  `frame_status` (the engine's word on whether its frame can be trusted), and no checksum or
  scale. The checksum and scale are this design's additions to that one record, not a second
  record of image identity (`ui/reader-overlay-frame-identity.md` owns the frame rules).

### Several images of one page

A page can have many images: the original, an enhanced one, a split half, ultraviolet,
raking light. A shape drawn on one can be shown on another only when Fichero knows how the
two images line up (the same frame; a crop; a recorded transform). If it does not know, it
says so and does not guess. This is today's rule (`ui/reader-overlay-frame-identity.md`),
kept.

A reading may be tied to the image it was read from: "this under-text was read from the
ultraviolet image".

**Lining two images up.** Just as control points tie a map to the earth, **alignment points**
tie one image of a page to another (this spot on the ultraviolet image is this spot on the
ordinary one). A few of them let every shape cross over. They have authors and certainty.

**When a page is scanned again.** A new scan is a new image. Shapes stay on the image they
were measured on. They cross to the new scan only through an alignment. Until then Fichero
says plainly which passes still sit on the old image.

### Sound and moving pictures

A recording is a source too. Its segments are stretches of time: an interview, a speaker's
turn, a sentence, a word. Everything else is the same: kinds, passes, reading orders, links,
readings (a transcript is a reading; so is a translation), hands become **speakers**, marks,
statements. A reading of a page can name the recording it is read aloud in, and a stretch of
a recording can link to the line of the page being read. This matters most where a language
lives mainly in speech.

Objects in the round (an inscription with several faces, a seal matrix, images made under
moving light) are **not yet designed**. Each face photographed is a page today. A later slice
will say how faces and light positions relate.

### The ladder, and two kinds of structure

```
collection  >  codex unit  >  quire  >  leaf  >  page (recto, verso)  >  region
            >  line or column  >  word  >  character  >  stroke
```

A **group of pages** is any set of pages taken together: a codex unit, a quire, a letter, a
case file. An **opening** (the two facing pages seen at once) is a group of two pages. A shape drawn
across an opening belongs to the opening and is resolved onto each page it touches.

- Every level is a segment with a **kind**. Kinds come from a standard list (SegmOnto's zones
  and lines, plus word, character, stroke, and the non-text kinds: picture, music, seal, stamp,
  table, table cell, diagram, map, mark, damage, blank). A project can add its own. When a
  model supplied the kind, the model's own label is kept beside the tidy one.
- Any level can be missing. Finer levels can be added later.
- How the ladder is SEEN (a child drawn and listed as its parent's child, in its region's hue) is
  owned by `segment-editor.md`, "Box colour and the segment hierarchy" (ruled 2026-10-04, #5426).
- **Physical structure** is the ladder: what is where on the object (codex unit, quire, leaf,
  page, region…). **Logical structure** is what the text is: a letter, a chapter, a diary
  entry, a legal case across several documents. Both are trees over the same segments, and a
  segment can sit in both. A letter that starts on one page and ends on the next is one logical
  unit over two physical pages.
- **Membership and order are the structure; links are cross-references.** "This text
  continues" is said in exactly one way for each case. A word broken at a line end is *one
  segment with two shapes*. Text running on across a column, a page turn or round a picture is
  a **flow**, which is simply a named reading order over those segments. The link type
  *continues* is kept for two *different* things (a letter continued in another document).
- **Page furniture** (running heads, page numbers, catchwords, quire signatures) is marked as
  furniture, so a reading of the text can leave it out and an export can put it where the
  format wants it.

### A worked case that already half exists: a diary with three days to a page

The maintainer's own project holds printed diaries with three dated entries on each page.
Today a workflow ("Diary Entries") already turns each page into **entry nodes**: each entry is
a child of its page, made from a prototype (`diary_entry`), with its date as a structured
attribute. Checked in the running app on 2026-09-19, read-only, on four entries: the tie back
to the page **exists when the page had measured word boxes** (one entry from the September
run carries `region_in_parent`: a rectangle that is the union of its words' boxes, marked
measured, method `diary-entry-word-union:apple`), and is **honestly absent otherwise** (two
entries from the August run, and one with no text, carry no region, and say why:
`bbox_basis` is `no_page_dimensions` or `none`). The engine has computed an entry's region
from its line boxes since commit `1db6c2922` (2026-08-22); entries made before that lack one. So today an entry is a node with structured
data and, at best, a rectangle; it has no lasting segment id, no polygon, and its lines and
words are not its children.

In this model that is one thing, not two:

- the entry is a **region segment** on the page (its third of the page, as a polygon), with a
  lasting id;
- it is also a **logical unit** of kind *diary entry*, made from the prototype, so it carries
  the prototype's structured attributes (date, weather, places), each of which can point at
  the words it came from;
- the lines and words inside it are its children, so its text is worked out from them;
- it still appears in the Library as the node it is today. **A segment that matters enough is
  a node**: a region can be promoted to a node (today's region promotion already does this),
  and a node made by a workflow is given its region.

Turning "three days on a page" into "three records with dates" is then one instance of a
general pattern: **find the parts, give each part its structure, keep each part tied to its
ink**. The same pattern turns a table into rows, a register into entries, a letter book into
letters, a page of glosses into gloss-and-word pairs.

### Tables and forms

A table is a segment; its cells are segments with a row, a column, how many rows and columns
they span, and whether they are a header. A cell's text is ordinary lines and words inside it.
A table-extraction tool already ships (`workflows/tools/table_extract.py`) and gives rows and
columns as data; in this model its output becomes cell segments, so the data and the ink are
tied. So a table on a page (an account book, a census return, a register, a palaeographer's table
of letterforms) **becomes a real table**: its rows and columns can be read out as data, sent
to a spreadsheet, searched by column, and each row can feed the knowledge graph (one row of a
census is one household's claims), with every cell still pointing at its ink.
A form's "label" and "filled-in answer" are two segments joined by a typed link. Ticks,
crosses and cancellation marks are **mark** segments with a state.

### Passes

A pass is a named set of segments on a source, with an author (a person, a model run, an
import). Examples: a model's proposed layout; a person's corrected layout; a second
scholar's competing layout; an imported PageXML file; the glosses; the pictures. Passes can be
shown, hidden and compared. They never overwrite each other. Two people disagreeing about
where a line ends is two passes, both kept: disagreement is data.

A pass has a maker (a person, a model run, an import), and **so does every segment in it**, and
they can differ: a person who draws one region on top of a machine's layout adds a human
segment to a machine's pass. A pass can be mixed. What counts as the record is therefore never
decided by a pass's maker alone (see the working-pass rule below and the morning file).

A segment belongs to **exactly one pass**. The same ink in two passes is two segments and a
match. A run over five hundred pages makes five hundred passes (a pass is for one source);
they carry the run's id and name, and are shown grouped by run.

One pass is the **working pass** for a source: the one the Reader, search and export use
unless told otherwise. What may become the working pass follows **the project's rule** (ruled
2026-09-19). In a *strict* project, which is how every new project starts, only a person
makes a pass the working pass: a machine's pass (from a chain run automatically, an import,
the synced folder) is there to look at and compare. In a *relaxed* project the newest pass
counts, and a person's always outranks a machine's. **Before anyone has chosen**, in either
kind of project, the newest pass is what is shown, plainly labelled as a machine's and
unchosen, so a new project is never blank; "the working pass" means the chosen one, or the
newest if none is chosen. Where nobody has chosen, **which pass is shown** follows the rule the app already has (ruled
2026-09-03 after a drawn region vanished behind a newer machine run): a pass that a person
made, **or that carries any segment a person made**, comes first; then a file's own text
layer; then the newest machine pass. Curation persists and constrains the machine. That
settles which pass is shown and used; it does **not** turn that pass's machine-made segments
and readings into a person's: each still says who made it, and in a strict project each is
still labelled unchosen until a person chooses. Which pass is working is worked out from recorded human choices and
the project's rule; it is never a flag stored on a pass, so changing the rule rewrites
nothing.

### One pass from several (DRAFT 2026-10-01, #5232; waiting for rulings, not built)

The maintainer, 2026-09-28: a page holds several results (regions from detect regions, lines and
words from Apple Vision, a VLM's transcription), "so we need to be able to get them all to one".
Since #5222 every result is a pass, so the question is how a person **composes** one pass from the
parts of several.

**What already exists, and is reused rather than rebuilt:** a pass never overwrites another
(`source.pass.never-overwrites`); "this segment is that one" is a match a machine may propose and a
person accepts (`source.segment.match-record`); across an accepted one-to-one match, readings and
marks are COPIED, each copy recorded against its match (`source.segment.carry-across-a-match`); a
person chooses the working pass (`source.pass.working`); Combine/Join works within one pass
(#5115); Merge Geometry joins a transcription to measured boxes at the result level, before the
page model.

**The proposal (each step one audited action, each undone on its own):**

1. **Compose: a new pass, made by the person, from LAYERS of existing passes.** The person picks,
   per kind, which pass supplies it: regions from pass A, lines (with their words) from pass B.
   The composed pass gets NEW segments copying those shapes, each recording the segment it was
   copied from (a match, accepted, made by the person, at certainty 1), so the lineage is the
   match record that already exists and nothing new is invented for it. The source passes are
   untouched. Lines go into the region that holds them (by containment, the same rule a
   detection's lines use); a line no region holds has none.
2. **Text: from a third pass, through matches.** Matching a transcription's lines to the composed
   lines is proposed by the machine (same order and overlap, or same order and similar length when
   the transcription has no shapes) and confirmed by the person, as any match is. Accepting a match
   carries its readings across (`carry-across-a-match`); the person can accept all the confident
   ones at once and review the rest. A line with no accepted match has no reading from that pass,
   and the page says how many.
3. **Working:** the composed pass is a person's pass, so it is shown first under the rule above; a
   person may also choose it explicitly.

Undo: compose undoes as a pass delete (`segment.pass_delete`), a carry as its own undo; nothing in
a source pass changes, so nothing there needs undoing.

**For ruling:**
- Q1. A NEW composed pass (the sources kept, as proposed), or the chosen layers copied INTO one of
  the source passes? Recommendation: new; it is what `never-overwrites` already says.
- Q2. Layers by KIND (regions / lines / words), or by hand-picked segments too? Recommendation:
  by kind first; picking single segments is Combine/Join's job, and later.
- Q3. Text alignment: confirm each match, or "accept every confident one" in one step, with a
  threshold the person can see? Recommendation: the one step, showing the count accepted and the
  ones left to review.
- Q4. A transcription with NO shapes (a VLM's plain text): match its lines by order alone, or
  refuse until it has shapes? Recommendation: by order, proposed and never automatic, with the
  mismatch named (n lines against m).
- Q5. What the Making section shows: the composed pass with its sources listed under it.

Behaviours, all [GAP] until ruled, in the list below: `source.pass.compose-from-layers`,
`source.pass.compose-carries-text-through-matches`, `source.pass.compose-keeps-its-sources`.

### Reading orders

The ladder itself has no order: which line comes third is never a property of a parent and its
children. **Every order is a named reading order**, and one, *as written*, is made with each
pass. An order belongs to a pass (its segments are that pass's); the same name means the same
thing across passes. Positions are fractions, so moving one segment changes one record.

A source has one or more **named reading orders**. Each is a sequence of segments with an
author and a certainty: the order as written; the order that reading-marks impose; the order
of a commentary. An order can nest (regions in order, lines in order inside each). "Next" and
"previous" are always asked *of a named order*.

### Links

Fichero already has four kinds of link, each with its own list of types: between notes
(`NoteLink`), between things on a canvas (`SpatialConnection`, and `CanvasItem` of kind link),
and between predictions (`PredictionLink`). This design does not add a fifth. There is to be
**one typed-link record**; a link between segments is one; the others converge on it; a line
drawn on a canvas is that record with a position. (`ui/library-view-modes.md`, #3085, owns the
canvas half; routed.)

A link joins one segment to another (on the same source or a different one). It has a
**type**, a direction, an author and a certainty. The standard types: *glosses*, *comments on*,
*answers*, *quotes*, *expands*, *reorders*, *marks* (a footnote marker to its note),
*captions* (a caption to its picture), *labels* (a form label to its answer), *continues*,
*translates*, *same as*, *names* (a label on a map to the place). A project can add types.
Links can chain to any depth (a comment on a comment on the text).

### Maps and plans

An image can carry **control points**: a point segment whose reading is a coordinate on the
earth. A few of them georeference the sheet. After that, any segment on it can be asked for
its place in the world, the sheet can be laid over a modern map, and a place name on it can
be linked to the place in the knowledge graph. Control points have authors, certainty and
versions like any other segment.

**Specified in full in `maps-and-georeference.md`** (#5120), which refines the three `source.geo.*`
behaviours below into its own: control points, the transform worked out from them, an explicit
CRS on input with WGS 84 stored (#5124), gazetteers, places over time, and the geo formats. The
three below are umbrellas that cite those refinements. They are not independent behaviours.

### On the canvas

The Library's canvas and spatial views (owned by `ui/library-view-modes.md`) lay nodes out in
space. The source model adds what can be laid out: a source, a group of pages, a page, or
**any segment** can be put on a canvas as a card showing its picture and chosen reading. A
gloss can sit beside the word it glosses; twenty instances of one sign can be spread out and
sorted by hand; the pages of a dispersed codex can be put back in order. Links drawn between
cards on the canvas **are** the typed links of this model, not a separate kind of line, and a
group made on the canvas can be kept as a logical unit. It is the same segments in another
view: nothing is copied.

### Two ways to point

Something can point at a segment **by its id** (the normal way), or at **a stretch of a
reading's text** (characters 14 to 22 of this reading of this line). The second is needed for
things finer than the segments that exist yet (a name inside a line that has no word
segments). When word segments are later made, the pointer can be moved onto them. The text of
a page is always worked out from its segments and a reading order; it is never the master
copy.

### Two people at once

An edit names the version of the segment it was made against. If the segment has changed
since (someone else reshaped it; an iPad was offline), the edit is refused and Fichero shows
what changed. Edits are never silently merged or silently lost. Editing while out of reach of
the engine (an iPad offline) is **not supported: ruled 2026-09-20.** A device must be connected
to the engine to edit; out of reach, the editors are read-only and say why. A queue of stale
edits refused one by one is no way to work.

### What is worked out from a segment

Some things are computed from a segment and its readings and can always be computed again:
its picture; search entries; **vectors** for finding similar images or text; the **words and
grammar** of a reading (tokens, parts of speech, lemmas), which are stretches of a reading.
They are kept with the segment and the reading they came from, with the model and version
that made them, and are absent, not faked, when they have not been made. (This is what
`segment-representations.md` calls representations.)

### Statements

A knowledge-graph claim or entity mention points at a segment id (and, if needed, a stretch
of a reading), and **keeps a copy of its anchor beside the id** (ruled 2026-09-19), so its
evidence can still be shown if a segment is ever lost. Every claim that exists today has only
an anchor; it gains a segment id when its page converts (rules below), and until then the
anchor is its pointer. Because ids last, a claim survives the page being re-segmented or
re-transcribed. From a segment you can list what is said about it; from a statement you can
go to its ink.

### Versions

The first slice's spec (`segment-representations.md`) has its own version behaviours
(`segment.rep.versioned`, `segment.inspector.version-visible`). They are the same records seen
at the level of a representation; that spec keeps those ids, and this one does not repeat them.

Every change to a segment (shape, kind, pass, order, links) is a new version of *that
segment*, with who, when and why. A segment's history can be read, compared and restored by
itself. Deleting a segment is a version too, and can be undone. Nothing is rewritten by batch.

### Its picture

Any segment can be asked for its picture: the image cut to its shape (not just its box), at a
chosen size, with or without a margin, from a chosen image of the page. For a line, also
straightened along its baseline, which is what a recogniser wants. Pictures are made when
asked for and may be cached; they are never the record.

### What a tool is given (ruled 2026-09-26, #5026; design, not built)

A vision tool may be given the whole page, the page with its boxes, a region, a line, a word, or a
single character; that flexibility is the requirement. It needs **no new vocabulary**: those sizes
are exactly the words `granularity` (and a segment's kind) already is. So what a tool is given is
**a set of segments**, plus a choice of whether the picture comes too. Nothing named "scope" or
"size" exists in the design: anything that can be said as an anchor can be said as a scope,
including a stretch of characters inside one reading. A table-extraction tool today receives one
downscaled image and a prompt and nothing else, even when the page already has a corrected
reading and boxes; the boxes matter most for a table, since the x positions of the numbers cluster
into columns and the y positions into rows, which a model gets wrong from pixels alone.

The text it is given is the reading the working pass says (see "Passes"), one line per segment in
reading order, marked by who made it, in a compact form such as
`L07 | 0.12 0.41 0.18 0.03 | person | Quibdó`, not SVG (the picture already carries the picture).
What it returns is anchored: each result names the segment ids it was read from, so a table cell
can light up its ink. When the page has no reading or boxes yet, the tool runs on the picture
alone and says so in the run log.

### Storage (the one big change)

Today all the boxes of a result are one block of data. This design needs **one record per
segment**, so the store can answer "the lines of this page", "this word's history", "every
segment in this hand". **How an existing project gets there was ruled again on 2026-09-20,
and the new ruling replaces the one of 2026-09-19:** a whole project is converted at once, in
the background, started by itself when the project opens, after a snapshot. The words move
onto segments FIRST (readings on segments, slice 8), and only then is the whole-project
conversion built, so that deleting a transcription keeps working. Converting one page as part
of its first edit (built as slice 6) stays as the engine's mechanism: it is the unit the
whole-project conversion runs for each page, and the way an edit gets ahead of it. Nothing of
this reaches the app until the whole programme is done.

### Converting a whole project: the rules (ruled 2026-09-20; design, not built)

- **It starts by itself when a project opens, and never holds the opening up.** The project
  opens and is fully usable at once; conversion runs behind it.
- **Only the running app's engine converts.** Never a migration at open (a migration still
  only adds empty tables and columns), never a script, never a second engine started for the
  job, never the command line acting on the file itself. One writer, the one that already has
  the project open.
- **Snapshot first, and proved restorable.** Before the first page converts, the engine takes a
  snapshot of the project through the snapshot code that already exists
  (`db/storage_snapshots.py`), and checks it can be read back (it opens, and its row counts
  equal the project's). No snapshot, or one that fails the check: no conversion, and the
  report says why. That snapshot is kept out of the ordinary "keep the last N" tidy-up until
  the conversion has finished and a person has seen the report.
- **Refused when the disk is short.** The engine works out what the snapshot and the new
  records need, with room to spare; if the disk cannot hold it, nothing starts, nothing is
  half done, the report says how much is needed, and it tries again at the next open.
- **The machine stays usable.** Background priority through the helper that already exists
  (`core/background_compute.py`), one page at a time, pauses between pages, gives way at once
  to anything a person is doing. Never a whole project in one transaction.
- **A page at a time, each page all or nothing.** Each page is one audited action (the slice
  6 action with no edit), in one transaction: all of that page's results become passes, or
  none do. A page that cannot convert is recorded with its reason and skipped; it does not stop
  the others, and it still reads, from its block, exactly as before.
- **It can be stopped and started, and running it twice changes nothing.** Quit the app in
  the middle and the next open carries on. Progress is not a counter that can be wrong: a
  result is converted when its marker says so, and a converted box's id follows from its result
  and its position, so converting again could only ever make the same records.
- **An edit gets ahead of the queue.** Editing a page the background work has not reached
  converts that page there and then, as part of the edit, with the same ids the background
  work would have given it.
- **A half-converted project reads the same as any other.** Every reader goes through the one
  seam (and `live_geometry`), which answers for each result from whichever store it is in. No
  reader, export, search, claim or workflow may be able to tell which pages are done.
- **A report for each project.** What converted, what could not and why, where the snapshot
  is, how long it took. Shown once, kept.
- **It is not undone; it is restored.** A converted page with no edit has nothing to undo.
  The way back from a conversion that went wrong is the snapshot, and restoring it discards
  whatever was done since: it is a safety net for a failed conversion, not an undo.
- **New results.** A machine run after conversion still writes a block today. It is converted
  by the same page action as soon as it is saved (default taken; in the questions file), until
  the tools write segment records themselves.
- **Building and testing it never touches a real project.** Every test runs on a temporary
  project made for the test. This rule is about the work, not the feature: the finished
  feature converts real projects by design, and only once the maintainer has tried the whole
  programme.

### Converting one page: the rules (built as slice 6; the unit of the above)

- **What counts as an edit.** Any action that changes a box's shape, kind, membership or order:
  what `artifact.regions_edit` does today. Adding a reading, a mark or a claim to a box does
  **not** convert its page. A new machine run does **not** convert the old boxes: it writes
  segment records for itself, and the old block stays as it is until someone edits it.
- **One action, one audit record.** When an edit converts its page, the conversion happens
  inside the edit's own action. (The earlier rule "never a page with converted records nobody
  asked for" went with the ruling of 2026-09-20: the background conversion converts every
  page.)
- **One page for each conversion.** No action converts more than one document's boxes, and no
  migration ever writes segment records. The whole-project conversion is this action, run for
  each page.
- **Every result with boxes becomes its own pass**, so nothing is lost and they can be compared
  (ruled 2026-09-20, confirming the default).
- **Undo undoes the edit and keeps the conversion** (ruled 2026-09-20, confirming the default). A converted page with no edit reads exactly as it did before, so
  keeping the records costs nothing a person can see, and it needs no hard delete and no test
  of "has anything depended on these since", which, when it said yes, would have left a
  person's first edit impossible to undo. (Today's inverse for a region edit restores the
  artifact and nothing else; used on a converted result it would leave records beside a
  restored block: two stores. That trap stays closed: the old region action and its restore
  are unreachable once a result is converted, and the block is never written again.) Ids are
  repeatable, so a true "unconvert" can be added later as its own action if it is wanted.
- **What pointed at the old boxes.** The converting action **reports** each reading, mark,
  support or claim whose rectangle matches a converted box exactly, and changes none of them
  (changed 2026-09-20). Pointing by id arrives with the anchor's own segment id
  (`source.point.anchor-names-its-segment`); until then a matching anchor is followed to its
  box at read time, storing nothing. Nothing is silently re-pointed.
- **The old block is marked as replaced**, and the permitted readers of it are listed in one
  place; any other reader raises.
- **It is detected properly**: a result counts as converted when it is marked as replaced by a
  pass, and that pass must exist (a mark without its pass raises); never when its block is
  missing, and never merely because some pass names it, since a pass can be made by hand. It
  is decided for each result, not each page: a machine run after conversion adds a new block,
  which the next edit converts. A second edit never converts the same result twice.

### Finding segments across a project

"Every line in hand B", "every instance of this sign" and a search result that lands on a
segment are one more leg of the one search response (`ui/search.md` owns search; routed), not a
separate segment search.

## Behaviors (every one is **[GAP]**: designed, not built; each cites its issue on milestone `source-model`, 322)

Identity and versions
- `source.segment.lasting-id` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestLastingId::test_create_read_back_engine_made_id_client_id_refused`) a segment keeps its id through move, reshape, re-read and
  re-type, and an id is never given to another segment.
- `source.segment.rerun-is-new-pass` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestPassesNamedAuthoredNeverOverwrite::test_two_passes_keep_separate_segments_second_touches_no_row_of_first`) segmenting a page again adds a pass; nothing existing
  is replaced or renumbered.
- `source.segment.carry-across-a-match` — **[OK]** (#4922; pinned by `tests/unit/api/test_segments_matches_forwarding.py::TestCarryAcrossAMatch::test_one_to_one_carry_copies_reading_and_annotation_names_the_match`) across an accepted one-to-one match, readings and
  marks are copied (never moved) to the new segment, each copy recorded against the match; a
  statement is never copied: the same claim gains one more place it rests on;
  undoing the carry removes the copies; a match that is not one-to-one carries no reading and
  says so.
- `source.segment.versioned-alone` — **[OK]** (#4923; pinned by `tests/unit/api/test_segments_versions.py::TestVersionedAlone::test_three_updates_leave_three_versions_and_touch_nothing_else`) one segment's history can be read, compared and restored
  without touching others.
- `source.segment.delete-is-undoable` — **[OK]** (#4923; pinned by `tests/unit/api/test_segments_versions.py::TestDeleteIsUndoable::test_delete_then_undo_restores_the_segment_and_what_pointed_at_it`) a deleted segment can be brought back with everything
  that pointed at it.
  **Its places in reading orders (2026-09-28):** a delete takes the segment's entries out of every
  order -- no row is left for export, flows, neighbours, the next/previous walk or the Reader to meet --
  and its undo writes the SAME entries back (id, position, level), so it returns to its place, a
  person's reordering included; the undo of a create and its redo go the same way
  (`test_imported_page_draws_its_boxes.py::test_a_deleted_region_leaves_the_order_and_its_undo_puts_it_back_in_its_place`,
  `::test_a_line_drawn_inside_a_region_is_that_region_s_line_in_its_order_and_one_undo_takes_both`).
  **The same for merge and split (2026-09-28):** a merge takes the absorbed segments' entries out and
  its undo (`segment.unmerge`) writes the same rows back -- the PAGE export's `<ReadingOrder>` names one
  region fewer, then the same ones again
  (`::test_a_merge_takes_the_absorbed_segment_out_of_the_order_and_its_undo_puts_the_same_row_back`);
  a split's new parts, which had NO entry, follow the line they were cut from at its level in every
  order holding it, and `segment.unsplit` takes them out with the parts
  (`::test_a_split_line_s_new_part_follows_it_in_the_order_and_its_undo_takes_the_part_out`).
  `segment.carry` retires no segment (it copies readings and annotations onto a matched one), so it
  has no entries to move.

Shape and images
- `source.segment.shape-kinds` — **[OK]** (#4925 closed; `test_anchor_shapes.py::TestEachKindStoresAndReadsBack`) a segment's shape is a point, a line, an area or a stretch of
  time; it may have more than one.
- `source.segment.box-is-derived` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestBoxIsDerived::test_bbox_columns_match_anchor_for_rect_and_polygon_supplying_them_is_refused`) the box is worked out from the shape and cannot be edited
  apart from it.
- `source.segment.curved-baseline` — **[OK]** (#4925 closed; `test_segment_pictures.py::TestATiltedLineIsLevelledOnItsBaseline`) a line's baseline can curve; direction can follow it.
- `source.segment.names-its-image` — **[OK]** (#4919; pinned by `tests/unit/api/test_segments_route.py::TestNamesItsImage::test_every_segment_names_the_results_rendition`) every shape names the image it was measured on; the image
  has a size and a checksum.
- `source.segment.no-guessing-across-images` — **[PARTIAL]** (#4926) a shape is shown on another image of the page
  only through a known alignment; otherwise Fichero says it cannot.
  **Partly built 2026-09-28 (#5122):** for a segment's place in the world, a shape on another image is
  carried through a recorded crop and refused with the reason otherwise
  (`fichero-server/tests/unit/api/test_gcps_on_another_image.py::test_a_label_on_a_turned_image_is_refused_not_guessed`). Drawing a shape on another image in
  the Source view is not built.
- `source.segment.picture-by-shape` — **[OK]** (#4925 closed; `test_segment_pictures.py::TestAShapeIsMaskedNotBoxed`) any segment's picture can be had, cut to its shape, from
  a chosen image, at a chosen size; a line's can be straightened.

Giving a tool a piece of a page (#5026)
- `source.tool.scope-is-a-segment-selection` — **[PARTIAL]** (#5026) what a tool is given is a set of
  segments, not a size word: a page, a page with its boxes, a region, a line, a word and a
  character stretch of one reading are all "some segments", and any anchor is expressible as a
  scope. There is no second list of sizes beside `granularity`.
  **Built 2026-09-28 (bugs lane, slice 1):** `fichero_server/tool_context.py::tool_context(db, page, segment_ids)`
  takes a page or any set of segments (a region brings the lines inside it) and gives one compact
  line per segment, `id | x y w h | maker | text`
  (`fichero-server/tests/unit/workflows/test_a_tool_is_given_the_pages_reading.py::test_the_whole_page_is_every_line_with_its_box_and_maker`,
  `::test_a_region_brings_only_the_lines_inside_it`). **Still PARTIAL:** only Extract Table uses it
  (`::test_extract_table_sends_the_lines_with_the_picture`), on the whole page; no caller passes a
  selection yet, and a character stretch as a scope is open question (2).
- `source.tool.picture-is-optional-and-separate` — **[GAP]** (#5026) whether the picture comes with
  the text is a choice made on its own, not implied by the scope. A job on one character or one
  word gets the picture cut to the shape (`segment_picture(..., mask=...)`, which already does
  this, `source.segment.picture-by-shape`), not its box.
- `source.tool.text-follows-the-working-pass` — **[PARTIAL]** (#5026) the text a tool is given comes from
  the working pass (`source.pass.working`), marked by its maker, a person's corrected line
  outranking a machine's; the builder never invents a second answer to "which reading counts".
  **Built 2026-09-28 (slice 1):** the lines are `document_text`'s own spans, so the counting reading
  of the working pass in reading order; a person's correction is what the tool reads, marked
  `person` (`fichero-server/tests/unit/workflows/test_a_tool_is_given_the_pages_reading.py::test_a_persons_correction_is_what_the_tool_reads_and_is_marked_as_a_persons`).
  The maker mark (open question 3) is `provenance_kind` written as person / agent / machine /
  file / unrecorded, from the server-set `provenance_kind`, never `created_by`
  (`::test_a_machine_reading_is_marked_machine_though_a_person_started_the_run`).
  **Slice 2 (2026-09-28):** it is the ONE page-context builder. Extract Table, Transcribe Review,
  Analyze, Describe and Convert are given it when nothing is wired in, and transcribe_review's own
  `_existing_transcription_context` is gone
  (`fichero-server/tests/unit/workflows/test_every_page_reading_tool_is_given_the_page.py`, one
  captured model call per tool). Left out on purpose: Transcribe and Handwriting (an independent
  reading must not be primed with the one it may be compared against), Detect Regions and Layout
  (they make geometry, and given the page's boxes would echo them), Classify Script (a property
  of the ink's look), and the picture tools. **Still PARTIAL:** a page with no segments is given
  its page text, else its newest transcription, as one block with no boxes -- there is no pass to
  follow there.
- `source.tool.results-name-their-segments` — **[GAP]** (#5026) a tool's result names the segment
  ids it was read from (a table cell names its lines), so the output is anchored instead of
  free text that must be matched back; this is what `Tables and forms` means by a table becoming
  cell segments, and it changes what a tool RETURNS.
- `source.tool.budget-reports-itself` — **[PARTIAL]** (#5026) a whole page at word granularity is
  large; the builder states how much it is sending and, if it must send less, what it left out.
  It never truncates silently: a tool that quietly did a smaller job than it was asked to is worse
  than one that refused.
  **Built 2026-09-28 (slice 1), the first half:** the builder states what it sends (lines,
  characters, the pass) in the engine log and in the prompt, and a page with no reading says the tool
  works from the picture alone (`fichero-server/tests/unit/workflows/test_a_tool_is_given_the_pages_reading.py::test_a_page_with_no_reading_says_the_tool_works_from_the_picture`).
  It sends everything; there is no limit yet (open question 1), so nothing is left out.

Structure
- `source.segment.one-primitive` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestOnePrimitiveOpenKinds::test_region_line_word_picture_all_segments_unknown_kind_roundtrips_kind_raw_kept`) every level of the ladder, and every non-text thing, is a
  segment with a kind.
- `source.segment.open-kinds` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestOnePrimitiveOpenKinds::test_region_line_word_picture_all_segments_unknown_kind_roundtrips_kind_raw_kept`) kinds come from a standard list a project can extend; a model's
  own label is kept beside the tidy kind.
- `source.segment.levels-optional` — **[GAP]** (#4927) any level may be absent; adding word segments under a
  line changes no id, shape or reading of the line or its region.
- `source.segment.physical-and-logical` — **[GAP]** (#4927) a segment can sit in the physical ladder and in a
  logical unit that crosses pages or documents.
- `source.segment.flow` — **[PARTIAL]** (→ #4930; reading straight through is **[GAP]** → #5090) text
  that continues across a column, page or picture is a named reading order and reads straight
  through. **Recorded, not read.** A flow's entries may name segments of another pass
  (`fichero-server/tests/unit/api/test_reading_orders.py::TestPlacingWritesOneRow::test_a_flow_may_cross_passes`),
  and an ordinary order correctly refuses a foreign segment
  (`::test_a_segment_of_another_pass_is_refused_outside_a_flow`) — that distinction is deliberate.
  **Continuing a flow onto a page (2026-09-28, bugs lane):** `GET /api/reading-orders/flows/onto/{page}`
  offers the live flows that end on an EARLIER page of the same source, nearest first, and those on
  a source a project shares with it (marked "same project"); a flow already reaching the page, a
  non-flow order and a deleted one are not offered; flows on pages the caller may not read are
  withheld and counted
  (`fichero-server/tests/unit/api/test_flows_that_could_continue_onto_a_page.py::test_a_flow_ending_on_an_earlier_page_is_offered_nearest_first`,
  `::test_a_flow_on_a_source_the_page_shares_a_project_with_is_offered_and_marked`,
  `::test_a_flow_on_a_page_the_caller_may_not_read_is_withheld_and_counted`). The app half (adding
  the page's segments with `reading_order.place`) is archive's.
  But `document_text` draws its rows from ONE pass and then keeps only the ordered ids it holds, so
  a cross-pass continuation is still **left out** of the derived text by the same filter that
  legitimately drops a deleted line (#5090).
  **No longer silently, from 2026-09-27**: every segment a named order names and the text does not
  contain is reported on `DerivedText.omitted` with a reason — `other_pass` (and the pass that holds
  it), `deleted`, `furniture` or `unknown` — so a shortened transcription and a complete one are
  different answers, pinned by
  `test_document_derived_text.py::TestWhatAnOrderNamesAndTheTextDoesNotHold::test_a_deleted_line_and_a_missing_continuation_no_longer_look_the_same`.
  Still `[GAP]` for the reading itself: a flow that reads its other passes needs a decision about
  what the response's `pass_id` and the `page_content` cache then mean, which #5090 sketches and
  nobody has ruled on. Silent shortening of a transcription is the worst failure this programme has,
  because nothing looks wrong; this makes it loud without guessing the ruling.
- `source.segment.furniture` — **[GAP]** (#4927) page furniture is marked, and a reading can leave it out.
- `source.segment.table-cells` — **[PARTIAL]** (#4928) a table's cells are segments with row, column, spans and
  header kind. **Cells are segments on import since 2026-09-27**, found by a real file: a
  Transkribus parish register's 172 `TableCell`s were being skipped, which re-parented every line
  to the table and made the page impossible to export (the schema forbids a line directly under a
  table). A cell is now read as a `region` — what PAGE 2019 says a cell is, a `TextRegion` with a
  `TableCellRole` — with `row`, `col`, `rowSpan` and `colSpan` kept in `foreign`, pinned by
  `test_transkribus_real_files.py::TestATablePageWithCells::test_the_cells_are_read_as_regions_and_keep_their_place`.
  Still owed: the model has NO fields for row, column, span or header — they ride in `foreign`
  because inventing them in a format reader would decide this behaviour for the whole model — and
  **header-ness is not captured at all**, because the 2013 files carry none.

Tables, forms and marks — the paragraph "Tables and forms" above, tagged 2026-09-27 so the
pipeline tracks what it promises (#4928). It had one tagged behaviour and seven claims.
- `source.table.is-a-segment` — **[PARTIAL]** (#5168, #4928) a table is a segment. True on import: PAGE's
  `TableRegion` is read as a `table`-kind segment, pinned by
  `test_transkribus_real_files.py::TestATablePageWithCells::test_the_page_round_trips_and_loses_nothing`
  (the table survives a write and a re-read). No editor verb draws one yet.
- `source.table.cell-text-is-lines` — **[PARTIAL]** (#4928) a cell's text is ordinary lines and words inside it.
  True on import: every line of a real table page has a CELL as its parent, never the table,
  pinned by `test_transkribus_real_files.py::TestATablePageWithCells::test_every_line_has_a_legal_parent`.
  Partial because import is the only path that makes cells; the extractor below does not.
- `source.table.extraction-makes-cells` — **[GAP]** (#4928) the table-extraction tool's output becomes cell
  segments, so the data and the ink are tied. Today `workflows/tools/table_extract.py` returns
  rows and columns as DATA with no segment ids, so a value in its output cannot be traced to the
  ink it came from — the untied state this behaviour exists to end.
- `source.table.reads-out-as-data` — **[GAP]** (#4928) a table's rows and columns can be read out as data,
  sent to a spreadsheet and searched by column. Nothing assembles cells into rows and columns yet;
  it needs the cell fields `source.segment.table-cells` still owes.
- `source.table.row-feeds-the-graph` — **[GAP]** (#4928) each row can feed the knowledge graph (one row of
  a census is one household's claims), with every cell still pointing at its ink. The account book
  and the census return are the maintainer's named cases, and this is the behaviour that makes
  them worth having as tables rather than as text.
- `source.form.label-and-answer` — **[PARTIAL]** (#4928) a form's label and its filled-in answer are two
  segments joined by a typed link. The vocabulary already carries it — `labels` and `answers` are
  both built-in link types (slice 10) — and links between two segments are recorded and read both
  ways. What is missing is anything that recognises a form or proposes the link.
- `source.segment.mark-with-state` — **[GAP]** (#4928) ticks, crosses and cancellation marks are `mark`
  segments with a state. `mark` is in the open list of kinds; there is no state on a segment to
  say whether a box is ticked, crossed or struck through.
- `source.segment.node-has-its-region` — **[GAP]** (#4927) a node made from part of a page (a diary entry, a
  letter, a register entry) is a segment of that page with a shape, never structured data
  with no tie to its ink.
- `source.segment.structured-from-prototype` — **[GAP]** (#4927) a segment can be made from a prototype and carry
  its structured attributes; each attribute can point at the words it came from.
- `source.segment.table-as-data` — **[GAP]** (#4928) a table segment can be read out as rows and columns of data
  in which every cell still points at its segment.
- `source.segment.marks-have-state` — **[GAP]** (#4928) a tick, cross or cancellation is a segment with a state.

Passes, orders, links
- `source.pass.named-authored` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestPassesNamedAuthoredNeverOverwrite::test_two_passes_keep_separate_segments_second_touches_no_row_of_first`) segments live in named passes, each with an author; passes
  can be shown, hidden and compared.
- `source.pass.never-overwrites` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestPassesNamedAuthoredNeverOverwrite::test_two_passes_keep_separate_segments_second_touches_no_row_of_first`) two layouts of one page are two passes, both kept.
- `source.pass.compose-from-layers` — **[GAP]** (#5232, DRAFT for ruling) a person composes a new pass
  from layers of existing passes (regions from one, lines and words from another); its segments
  are new copies, each matched to the segment it came from, and lines sit in the regions that hold
  them. See "One pass from several".
- `source.pass.compose-carries-text-through-matches` — **[GAP]** (#5232, DRAFT) a transcription's
  text reaches the composed lines only across matches a person accepted, never by position alone;
  the lines left without a reading are counted.
- `source.pass.compose-keeps-its-sources` — **[GAP]** (#5232, DRAFT) composing changes nothing in a
  source pass; undoing it removes the composed pass and nothing else.
- `source.pass.working-follows-project-rule` — **[OK]** (#4929; pinned by `tests/unit/models/test_counting_and_working_pass.py::TestTheWorkingPass::test_untouched_machine_passes_fall_back_to_the_newest`) in a strict project a machine's pass never
  becomes the working pass until a person makes it so; in a relaxed project the newest pass
  counts and a person's outranks a machine's; a new project is strict.
- `source.pass.working` — **[PARTIAL]** (#4929; pinned by `tests/unit/models/test_counting_and_working_pass.py::TestTheWorkingPass::test_a_machine_pass_carrying_one_human_segment_outranks_a_newer_machine_pass`) the working pass is
  the one a person chose, or the newest, labelled unchosen, if nobody has; it is worked out, never a
  stored flag. The order: a person's live choice; then a pass a person made or touched; then the newest
  of the rest. **An import has no rank of its own (ruled 2026-10-04, #5443):** it is just the first
  pass, ranked by date among the passes nobody touched, and says what made it where the file does.
  **Built 2026-10-04 (#5443, #5425):** `resolve_working_pass` lost its "imported" tier (on Mosquera it
  had made a geometry-free TEI import of a Qwen-VL draft the working pass of 358 of 374 pages, over
  the Gemini reading of Kraken's lines), so a run's newly landed pass is working with no promote; a
  person's choice beats it; an outside edit from a synced folder still never wins until chosen; and
  the app draws the engine's working pass first rather than its own copy of the ladder. The Order tab
  lists the working pass's own `as-written` order: the engine lists it first (#5450; before, any pass's
  order could come first, and on C01_030 the tab showed Apple Vision's lines). Pinned by
  `fichero-server/tests/unit/api/test_an_import_has_no_rank_of_its_own.py` and
  `fichero/Tests/Unit/general/Models/WorkingPassRankingTests.swift` (the same cases). **One place
  (#5467, engine half built 2026-10-04):** the engine picks a page's working pass in ONE function,
  `resolve_working_pass`, read through `working_pass`, by the segments route, the page's text, the
  Order list, the text cache and export alike. An unconverted result (a run's boxes not yet made a
  pass) counts only if a person corrected it or the page has no pass at all; that rule lived in the
  segments route alone, so the canvas and the text could name different passes (a corrected result
  beside real passes; a page with only an unconverted result; a filtered segments read). Where its
  working pass is an unconverted result the text is empty and names it, the stored page text stands,
  and export refuses. Pinned by `fichero-server/tests/unit/api/test_one_working_pass.py`. **The engine serves
  the drawn pass too (#5467, built 2026-10-05):** `resolve_working_pass` is the head of `rank_passes`, the
  one ranking, and `resolve_drawn_pass` walks that same ranking to the first pass with shapes (a segment
  with a sized box and no `shape: unstated`); each `PassRead` carries `drawn` (exactly one when any pass
  has shapes) and `rank` (its place, 0 for the working pass). Pinned by
  `fichero-server/tests/unit/api/test_the_engine_serves_the_drawn_pass.py`. **App half built 2026-10-05
  (#5467):** the app ranks no pass. It reads the engine's working mark (`SegmentStore.workingPass`), the
  Segments list takes the one pass-filtered read (`SegmentStore.workingSegments`), and Preview draws by
  the engine's `drawn` and `rank` (`SegmentDisplay.drawingOrder`). The app's copy of the ladder
  (`OCRGeometrySelection`) and the artifact path's own ranking are deleted. The Inspector's focused
  artifact still goes first on Preview (ruled 2026-08-27; see `segment-editor.md`). On the diary page with
  two passes, Preview, the Segments list and a line the Reader names are the same pass, and a newer pass
  the engine did not mark does not take Preview. Pinned by
  `fichero/Tests/Unit/general/Models/ImportedPageDrawsItsBoxesTests.swift`
  (`testPreviewTheSegmentsListAndTheReaderNameTheSamePassOnAPageWithTwoPasses`,
  `testANewerPassDoesNotTakeThePreviewButAFocusedArtifactDoes`). Residue, not
  ruled here: a pass read from a PDF's own text layer still ranks above the newest. **The ENGINE half is proven by the citation above. The claim that "the Reader, search
  and export use one pass" is NOT.** Downgraded from [OK] 2026-09-26: the citation proves the
  ranking function and says nothing about which surfaces consult it, and the Reader is known NOT to
  — it reads `Document.page_content`, and the app contains no reference to the derived-text route at
  all (#5077). Search and export are unverified in either direction. A behaviour naming three
  surfaces needs evidence from those surfaces; a passing engine test is not it.
- `source.order.named-multiple` — **[OK]** (→ #4930) a source can have several named reading orders,
  each with an author and certainty (`ReadingOrder.certainty`, where `None` means nobody said and
  NOT certainty 0). Two orders hold different sequences over the same segments, deleting one leaves
  the other, and a deleted order restores with its entries
  (`fichero-server/tests/unit/api/test_reading_orders.py::TestSeveralOrdersOverOnePage`). `as-written`
  arrives with the pass rather than being invented later, and a pass made before this slice is NOT
  given one silently (`::TestAsWrittenArrivesWithThePage`) — which is the honest half: a missing
  order is left missing rather than back-filled with a guess at what somebody meant.
- `source.order.next-previous` — **[OK]** (→ #4930) next and previous are always asked of a named
  order — there is deliberately NO next-segment call without one
  (`fichero-server/tests/unit/api/test_reading_orders.py::TestNeighbours::test_there_is_no_next_segment_call_without_an_order`),
  because "the next segment" is meaningless until somebody says in which order. Neighbours differ
  between two orders for the same segment, and the ends report null rather than wrapping.
- `source.link.typed` — **[PARTIAL]** (→ #4931; the convergence is **[GAP]** → #5091) a link between
  segments has a type, direction, author and certainty; types come from an extendable list; it is
  the one typed-link record that the existing note, canvas and prediction links converge on, not a
  further kind. **The record is built and the convergence has not started.** `TypedLink` carries all
  four facts, `directed` is false for a symmetric relation so a reader is never shown a direction
  that says nothing, and the MAKER is the engine's answer and not the caller's
  (`fichero-server/tests/unit/api/test_typed_links.py::TestLinkingSegments`), and it joins segments of any
  GRANULARITY — a word to a word, a region to a region — which this behaviour owns and
  `source.link.any-depth` does NOT (`::test_links_join_segments_of_any_granularity`; the test
  cited the wrong behaviour until 2026-09-27, and so did this spec). The vocabulary reuses the KG's
  words rather than respelling them, refuses near-misses by inflection or underscore, and reports
  its one alias so no client keeps a list of its own
  (`::TestTheVocabularyHasNoNearMisses`, `::TestTheAlias`). But `NoteLink`,
  `SpatialConnection`, `PredictionLink` and `KnowledgeClaimLink` all still exist —
  `::TestTheOtherFourRecordsAreNotMoved` asserts it deliberately — so there are FIVE link records
  where this says one, and this record is for now the further kind it says it must not be (#5091).
- `source.link.end-is-entity` — **[GAP]** (#4931, → #5123) a link end can be a knowledge-graph
  **entity**, so a segment that names a place can name the place entity itself. Asked by
  `maps-and-georeference.md`. `LinkEndKind` today is `segment`, `note`, `document`, `claim` and
  `canvas_item`, with no `entity`.
- `source.link.any-depth` — **[GAP]** (#4931) links chain (a comment on a comment), and can cross sources.
  **The tag is right, and checked 2026-09-27 rather than assumed**: rule (i) flagged it because
  `test_typed_links.py` mentioned the id, and reading the test showed the citation was wrong, not the
  tag. What is built is that a link joins segments of any GRANULARITY (a word to a word, a region to
  a region) — `source.link.typed`'s business. **Chaining is genuinely absent**: an end's kind is one
  of `segment`, `note`, `document`, `claim`, `canvas_item`, and there is no `link`, so nothing can
  comment on a comment. Crossing sources is untested, which is not the same as absent — the create
  action checks each end exists and never checks they share a document, so it may already work and
  nobody has said so.
- `source.link.both-ways` — **[OK]** (→ #4931) from either end of a link you can reach the other
  (`fichero-server/tests/unit/api/test_typed_links.py::TestLinkingSegments::test_a_link_is_reachable_from_either_end`),
  a symmetric relation reads the same from both ends, and a withdrawn link disappears from both
  ends while staying auditable (`::TestWithdrawingALink`) — reachable both ways has to mean
  UNreachable both ways too, or a withdrawal leaves half a link behind.

Maps
- `source.geo.control-points` — **[GAP]** (#4933, → #5122) a point on an image can be tied to a coordinate on the earth,
  with author and certainty. Umbrella: refined as `source.geo.gcp-is-a-segment` in
  `maps-and-georeference.md`.
- `source.geo.segment-to-world` — **[GAP]** (#4933, → #5122) on a georeferenced image, any segment can give its place in
  the world. Umbrella: refined as `source.geo.world-shape` in `maps-and-georeference.md`.
- `source.geo.names-a-place` — **[GAP]** (#4933, → #5123) a label on a map can be linked to the place entity it names.
  Umbrella: refined as `source.geo.place-segment-names-entity` in `maps-and-georeference.md`, which
  needs `source.link.end-is-entity` below.

Canvas
- `source.canvas.segment-as-card` — **[GAP]** (#4931) any source, page or segment can be placed on a canvas as a
  card with its picture and chosen reading, without being copied.
- `source.canvas.links-are-links` — **[GAP]** (#4931) a link drawn between cards on a canvas is a typed link of
  the source model.

Pointing and statements
- `source.point.by-id-or-span` — **[OK]** (→ #4932; pinned by `tests/unit/api/test_readings_across_split_and_merge.py::TestTheAnchorCanNameWhatItPointsAt::test_a_stretch_names_the_exact_reading_it_was_measured_on`) a thing points at a segment by id, or at a stretch of one of
  its readings.
- `source.point.text-is-derived` — **[OK]** (→ #4932; pinned by `tests/unit/api/test_document_derived_text.py::TestTheDerivedText::test_the_page_text_is_the_join_of_its_lines_readings_in_order`) a page's text is worked out from segments and a reading
  order; it is never the master.
- `source.statement.on-segment` — **[GAP]** (#4932) a claim or mention points at a segment id, keeps a copy of
  its anchor beside it, and survives re-segmentation and re-transcription; a claim on an
  unconverted page points by its anchor alone.
- `source.point.anchor-names-its-segment` — **[OK]** (→ #4932; pinned by `tests/unit/api/test_readings_across_split_and_merge.py::TestTheAnchorCanNameWhatItPointsAt::test_all_four_carriers_gain_the_lasting_id_with_no_new_column`) the one anchor every reading, mark and claim
  carries (three stored kinds), and every supporting source embedded in a claim or an entity,
  gains an optional lasting segment id; the id is the pointer and the
  stored shape is the record of where the ink was; one resolver answers with the live
  segment's current shape, or the stored shape when the segment was deleted. One shape for
  all four, no new column on any of them; an old record reads as having none.
- `source.point.unpointed-anchor-follows-its-box` — **[GAP]** (#4932) an anchor with no segment id, whose
  rectangle equals a box of a converted result, is resolved through that box's segment at
  read time, storing nothing, so a mark drawn before conversion follows its box when it moves.
  The match is made against the result's kept block, whose boxes never move, so it can still
  be found after the box has moved. The read carries the resolved shape beside the stored
  one, and the app's one accessor for a mark's rectangle uses it (today every mark is drawn
  from its stored rectangle and stays behind when its box moves, before or after conversion).
- `source.statement.old-segment-field-left-alone` — **[OK]** (→ #4932) the claim field
  `source_segment_id`, which predates this model and names an entry in a segmentation artifact,
  keeps its meaning and its data, is described as such in the contract, and is never given a
  segment record's id. Two of the three clauses were already pinned
  (`tests/unit/api/test_segment_conversion_action.py::TestSliceSixRepointsNothing::test_the_legacy_claim_column_is_left_exactly_as_it_was`
  and `::test_a_pre_existing_legacy_value_is_not_overwritten`). **The contract clause was not,
  and was not true** until 2026-09-27: the reasoning lived in a thirteen-line comment in
  `segment_conversion.py` while every published model carried the field bare. A client author —
  the app, the CLI, a researcher's script — reads the contract, not our comments, and
  `source_segment_id` on a claim reads as "the segment this claim is about", which is exactly the
  meaning-merge the comment exists to prevent. All three publishing models now describe it, and
  the description says what it is, what it is NOT, and what to use instead
  (`::TestTheLegacyClaimFieldSaysWhatItIsInTheContract`, four tests, one of them asserting it
  reaches `app.openapi()` rather than only the Python model).

> **"No new column on any of them" — what it does and does not forbid (clarified
> 2026-09-26).** `source.point.anchor-names-its-segment` above says the lasting id
> goes in the one shared anchor, "no new column on any of them". Two of the four
> carriers DO have a segment-id column, and both are correct — a reader who finds
> them will otherwise think the behaviour is violated. Found by writing a test
> that asserted the blanket rule, watching it fail, and working out that the
> assertion was over-strict rather than the code wrong.
>
> The rule is about **pointing**, and these two columns are not pointing:
>
> * `ContentRepresentation.segment_id` is **ownership** — which segment this is a
>   reading *of*. Required by slice 8's own field table, indexed, and read once
>   per line by `document_text`. It is not a second answer to the anchor's
>   question, because a reading of a LINE may carry an anchor pointing at a WORD
>   inside it: the column says what the reading is of, the anchor says what its
>   span points at. They can legitimately differ, and when they do, neither is
>   wrong.
> * `KnowledgeClaim.source_segment_id` predates this model and is **mandated** by
>   `source.statement.old-segment-field-left-alone` below, which says it keeps its
>   meaning and must never be given a segment record's id. Its existence is the
>   spec working, not an oversight.
>
> Where a second answer WOULD be created is on a record that has no such column
> today: `Annotation` and `SourceSupport` take the lasting id from the shared
> anchor and must keep doing so. That is the half the guard test now pins
> (`test_all_four_carriers_gain_the_lasting_id_with_no_new_column`), and it is
> the half worth guarding.

- `source.statement.both-ways` — **[GAP]** (#4932) from a segment, what is said about it; from a statement, its
  ink.

Identity, continued
- `source.segment.match-record` — **[OK]** (#4922; pinned by `tests/unit/api/test_segments_matches_forwarding.py::TestMatchRecord::test_propose_as_tool_accept_as_person_tool_accept_refused`) "this new segment is that old one" is a record of its own
  with an author and certainty; ids do not move; a machine may propose, a person accepts.
- `source.segment.forwarding-notes` — **[OK]** (#4922; pinned by `tests/unit/api/test_segments_matches_forwarding.py::TestForwardingNotes::test_merge_split_delete_chain_resolves_in_one_call`) a merged, split or deleted segment leaves a permanent
  forwarding note; following an old id is one call; the walk raises past 64 steps; a merge
  into a segment that already forwards to the source is refused; a trail ending in a delete
  says so.
- `source.segment.citable` — **[OK]** (#4922; pinned by `tests/unit/api/test_segments_matches_forwarding.py::TestCitableReference::test_reference_resolves_through_locations_resolve`) a segment has one stable reference that opens it in the app and
  resolves over MCP and the command line, following forwarding notes. Scope checked 2026-09-26:
  the citation pins the HTTP route only. The `fichero_segment_reference` MCP tool and the CLI's
  `reference` command both EXIST, so the claim is plausible on all three surfaces — but neither is
  pinned by a test, and this line names them. Kept [OK] rather than downgraded because the
  capability is present, unlike `source.pass.working`, where the Reader demonstrably does not use
  what its sentence claimed.
- `source.segment.time-span` — **[GAP]** (#4933) a segment of a recording is a stretch of time (with an area,
  for video) and behaves as any other segment.
- `source.segment.opening` — **[GAP]** (#4927) a shape drawn across two facing pages belongs to the opening and
  resolves onto each page.
- `source.image.alignment-points` — **[GAP]** (#4926) two images of one page can be tied by points so shapes
  cross between them.
- `source.image.rescan-strands-nothing-silently` — **[GAP]** (#4926) after a rescan, shapes stay on their image
  and Fichero says which passes have not crossed over.
- `source.image.physical-scale` — **[GAP]** (#4926) an image can carry a scale so a segment's size can be given
  in millimetres.
- `source.edit.stale-is-refused` — **[OK]** (#4923; pinned by `tests/unit/api/test_segments_versions.py::TestStaleIsRefused::test_two_updates_against_version_one_the_second_is_refused`) an edit made against an old version of a segment is
  refused, with what changed.
- `source.derived.recomputable` — **[OK]** (#4925 closed; `test_segment_pictures.py::TestAPictureIsWorkedOutNeverARecord`) pictures, search entries, vectors and word-level analysis
  name the segment, reading, model and version they came from, and are absent when not made.

The read seam and events
- `source.seam.read-either-store` — **[OK]** (#4919; pinned by `tests/unit/api/test_segments_route.py::TestReadEitherStore::test_one_provisional_segment_per_box_rect_for_rect`) one engine call returns a source's segments whether they
  live in a block of boxes or in segment records; its answer has the same shape either way.
- `source.seam.maker-for-each-segment` — **[OK]** (#4919; pinned by `tests/unit/api/test_segments_route.py::TestSegmentProvenanceKind::test_artifact_with_provider_user_is_human_throughout`) every segment read through the seam says
  who made it, in the one maker vocabulary, set by the engine: a person when the box itself
  proves a person drew it, otherwise its pass's maker; never supplied by a caller, never
  defaulting to a person; a pass may hold segments by different makers.
- `source.seam.area-applies-to-either-store` — **[OK]** (→ #4985) asking for a page's segments by area narrows
  them the same way whether they come from segment records or from a result's block of boxes:
  each box is tested on the rectangle it would have as a row (`_converted_box_columns`). Fixed
  2026-10-01; the block branch had ignored `area` (found by the slice 6 recon, 2026-09-20).
  Pinned by `fichero-server/tests/unit/api/test_area_applies_to_either_store.py` (the same area
  before and after conversion).
- `source.seam.provisional-ids-refused` — **[OK]** (#4919; pinned by `tests/unit/api/test_segment_readings.py::TestRefusals::test_a_provisional_segment_id_is_refused_on_a_write`) an id read from a block of boxes is marked
  provisional, and every write path refuses one with a typed error.
- `source.events.segment-ids` — **[OK]** (#4920; pinned by `tests/unit/api/test_change_stream_segment_ids.py::TestChangeSpecReachesSubscriber::test_changespec_segment_and_pass_ids_reach_the_subscriber`) a change event names the segments and passes that changed, so a
  window updates those and nothing else.

Storage
- `source.store.one-page-per-conversion` — **[OK]** (→ #4924) no action converts more than one
  document's boxes; a whole project is converted by running that action once for each page.
  Tested by `fichero-server/tests/unit/api/test_segment_conversion_action.py::TestOnePagePerConversion`. The
  restraint is the point: one page per action is what makes the whole-project runner resumable and
  its half-done state readable, rather than one enormous transaction.
- `source.store.undo-first-edit-keeps-conversion` — **[OK]** (→ #4924; tested by
  `fichero-server/tests/unit/api/test_first_edit_conversion.py::TestUndoOfAFirstEditKeepsTheConversion`)
  undoing the first edit undoes the edit
  and keeps the page's segment records; the old block is never restored over them, and the old
  region action is unreachable on a converted result. (Replaces
  `source.store.conversion-undo-leaves-nothing`, 2026-09-20; default taken, in the morning file.)
- `source.store.conversion-changes-nothing-seen` — **[OK]** (→ #4924) a page read just before and
  just after conversion is the same in every field but the ids: kinds, shapes, order, words, page
  numbers and who made each box. Pinned TWICE, deliberately: in its pure form over the rows
  (`fichero-server/tests/unit/models/test_segment_conversion_rows.py::TestConversionChangesNothingYouCanSee`)
  and through the real seam the app reads
  (`fichero-server/tests/unit/api/test_segments_seam_after_conversion.py`). A row-level equality can hold
  while the seam that assembles them reorders or drops one, which is why one test was not enough.
- `source.store.conversion-ids-repeatable` — **[OK]** (→ #4924) a converted box's id follows from its
  result and its position, so converting the same page again, eagerly or on first edit, gives the
  same ids; a provisional id resolves to the real one on reads and is still refused on writes.
  Tested by
  `fichero-server/tests/unit/models/test_segment_conversion_rows.py::TestTheNamespaceAndTheIds::test_the_same_box_gets_the_same_id_every_time`.
  This is what lets the eager runner and a first edit race without either undoing the other:
  they arrive at the same ids, so the second is a no-op rather than a duplicate.
- `source.store.converted-boxes-keep-their-maker` — **[OK]** (→ #4924) converted boxes are stored as
  their maker's (machine, the person who drew them, or unknown), never as the person whose edit
  caused the conversion; only the edited segment becomes that person's. Tested by
  `fichero-server/tests/unit/models/test_segment_conversion_rows.py::TestConvertedBoxesKeepTheirMaker` and,
  through the real edit, `fichero-server/tests/unit/api/test_first_edit_conversion.py`. The defect it
  prevents is the one that matters most in this programme: an edit that makes a machine's 200 boxes
  look like a historian's work, which would be the engine inventing provenance (the shape of → #4869).
- `source.store.old-app-still-works` — **[OK]** (→ #4924) until the app draws from segments, a
  converted result is served with its boxes filled from the segment records in one order, and an
  edit by position lands on the box shown at that position. Tested by
  `fichero-server/tests/unit/api/test_first_edit_conversion.py::TestTheAppsPositionsKeepMeaningWhatItWasGiven`
  and `fichero-server/tests/unit/api/test_live_geometry_projection.py`. "One order" is load-bearing and is
  not the same order as the derived text's — see the three orderings named in
  `segment_readings.py::_segment_order_key`; a fourth would break exactly this behaviour.
- `source.store.conversion-reports-exact-matches` — **[GAP]** (#4924) the converting action lists each reading,
  mark, support and claim whose rectangle matches a converted box exactly, with the segment id
  it would take, and changes none of them. (Replaces `…conversion-repoints-exact-matches`,
  2026-09-20: there is nowhere lawful to write the id until `source.point.anchor-names-its-segment`.)
- `source.store.edit-converts-its-page-first` — **[GAP]** (#4924) reading a page never converts it; editing a page
  that is not yet converted converts it as part of that edit, one audited action, with the
  same ids the whole-project conversion would give it; undo takes back the edit and keeps the
  records. (Replaces `source.store.ids-on-first-edit`: by the ruling of 2026-09-20 this is no
  longer how a project is converted, it is how an edit gets ahead of the conversion.)
- `source.store.bounded-reads` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestRecordPerSegment::test_lines_of_this_pass_and_children_of_this_region_are_single_filtered_queries`) a page's segments come back by kind and by area, never "all
  of a project"; one page at one kind returns in under 200 ms with 200,000 segment records in
  the source (threshold in the morning file).
- `source.store.record-per-segment` — **[OK]** (#4921; pinned by `tests/unit/api/test_segments_write_actions.py::TestRecordPerSegment::test_lines_of_this_pass_and_children_of_this_region_are_single_filtered_queries`) the store can answer questions about single segments
  (the lines of a page; a word's history; all segments in a hand).
- `source.store.never-converted-by-a-migration` — **[GAP]** (#4924) no migration, script, second engine or
  command-line process ever writes a segment record into an existing project; opening a
  project adds empty tables and columns and nothing else. (Replaces
  `source.store.no-batch-rewrite`, overturned 2026-09-20: a whole project IS converted, but
  only by the running app's engine, a page at a time.)

Converting a whole project (ruled 2026-09-20; built after readings are on segments)

> **Reachable since 2026-09-28 (#5222, #5088).** The running engine starts the conversion when a
> library opens (`maintenance/conversion_on_open.py`, called from `DatabaseManager.get_database`
> after the open-time migrations), and the app reads it at `GET /api/conversion/status`. Before
> that date nothing called `convert_project`, and every page curated before the page model stayed
> one rerun away from losing its correction (#5075).
- `source.convert.results-live-as-passes` — **[OK]** (→ #5222) results always live as passes: old
  ones convert when their library opens (the behaviours below), and every tool that finds boxes
  writes its result as its own pass (the next three behaviours, built 2026-09-30).
- `source.convert.a-new-result-is-a-pass-at-once` — **[OK]** (→ #5222 part 2; ruled 2026-09-28: "bring
  them over when they're generated from now on") a result with boxes becomes its own pass in the
  same run that made it, not at the next open: Apple Vision OCR, a VLM's layout or transcription, a
  PDF's text layer at import, detect regions, Kraken, merged geometry, and a transcript aligned to
  baselines (`artifact.create` takes no boxes, so it has none to convert). It goes through the SAME
  page action the background
  runner and a person's first edit use (`segment.convert_and_edit` with the page alone, as the
  engine's own actor), so a pass made at once and a pass made at the next open are the same pass.
  It is the machine's work (`source.convert.converting-is-not-a-persons-work`): the page's chosen
  working pass, a person's boxes and readings, and the page's text rules are unchanged, and a
  rerun on a page a person corrected adds a pass beside theirs rather than replacing it. Measured
  2026-09-30 on the Air under load: 0.22 s for a page of 50 boxes, 0.66 s for 400, which a
  born-digital PDF's import now pays per page. One seam,
  `maintenance/project_conversion.py::convert_new_results`, called after `save_artifact` (every
  vision and LLM tool), a split PDF's per-page results, Merge Geometry, both alignment paths and the
  importer's text layer. Pinned by `fichero-server/tests/unit/workflows/test_a_new_result_is_a_pass_at_once.py`
  (`::test_a_tools_result_with_boxes_is_its_own_pass_when_the_run_saves_it`, a rerun adds a pass
  beside the first, no boxes make no pass, the aligned transcript) and
  `test_merge_geometry_tool.py::TestMergeGeometry::test_the_merged_result_becomes_its_pass_in_this_run`.
- `source.convert.a-result-that-cannot-convert-is-kept` — **[OK]** (→ #5222) when the new result's
  conversion fails, the result is still saved and the run still succeeds: the page reads it from
  its stored boxes exactly as before this was built, the failure is logged as an error naming the
  page and the reason, and the result counts as waiting in `GET /api/conversion/status`, so the
  next open converts it or reports why not. Converting is never a reason to lose a result.
  (`fichero-server/tests/unit/workflows/test_a_new_result_is_a_pass_at_once.py::test_a_conversion_that_fails_keeps_the_result_and_the_run`)
- `source.convert.no-producer-writes-boxes-alone` — **[OK]** (→ #5222: "a guard that fails if a tool
  emits geometry without a pass") a guard reads the engine's code and fails on any place that saves
  a result with boxes without handing it to the conversion, naming the file and line; a place that
  legitimately does not (the conversion's own undo, a person's edit through the older regions
  route) is listed with its reason (`fichero-server/tests/unit/workflows/test_a_new_result_is_a_pass_at_once.py::test_no_producer_saves_boxes_without_converting_them`,
  with fixtures proving it catches one). Per function: a builder that returns an unsaved result is
  not followed to its caller.
- `source.convert.starts-when-a-project-opens` — **[OK]** (→ #5222, #4998, #5088) conversion starts by
  itself after a project opens -- after its migrations, on a background thread -- and never
  delays the opening; pages not yet converted read through from their stored geometry; closing
  the library stops it at a page boundary and the next open finishes it; a second open with
  nothing left writes nothing. Automatic on every open with work, announced only through the
  status route (ruled 2026-09-20; #5088 decided 2026-09-28). A bare `Database()` open -- a
  migration, a script, the CLI's own process -- still converts nothing
  (`::TestOpeningIsNotHeldUp` below). Pinned by
  `fichero-server/tests/unit/maintenance/test_conversion_starts_on_open.py::test_opening_converts_every_page_in_the_background`,
  `::test_the_open_returns_before_the_conversion_does`, `::test_a_second_open_writes_nothing`,
  `::test_closing_mid_run_stops_at_a_page_boundary_and_the_next_open_finishes`, and
  `::test_when_the_snapshot_cannot_be_made_nothing_converts_and_it_says_why`. Every stored shape
  of an older result, one fixture per producer and era (Apple Vision lines and words, VLM boxes, a
  PDF's text layer, regions, Kraken's pixel polygons, Kraken HTR, merged geometry, aligned
  transcripts, a box set measured on a crop), converts: `test_every_legacy_shape_converts.py`.
  Opening the real engine converts nothing in the test suite (`FICHERO_SKIP_PROJECT_CONVERSION`).
- `source.convert.converting-is-not-a-persons-work` — **[OK]** (→ #5222, #5081) a page the ENGINE
  converted is still the machine's to write: a later tool run still writes its text into the page's
  stored text (search, embeddings, the Reader), exactly as before the conversion. Only a person's
  mark on the page model -- a working pass chosen, a box drawn or moved, a reading written or
  corrected, a line deleted -- makes the page's text derived and stops a machine run writing it.
  (#5081 took "any result converted" as that sign, which was true while only a person's first edit
  converted; with whole-library conversion it would have frozen every page on first open.) Pinned
  by `fichero-server/tests/unit/workflows/test_curation_guard.py::TestConvertedByTheEngineIsNotAPersonsWork`
  (four tests) and, through real reruns, `fichero-server/tests/unit/api/test_segment_corrections_survive_a_rerun.py`.
  Not seen: a person's move in a reading order, which records no maker on any row.
- `source.convert.only-the-running-engine` — **[OK]** (→ #4998) the only thing that converts a
  project is the engine of the running app that has it open. A lock, and a lock that can be
  RECOVERED: a second opening is refused while one runs, being refused is not mistaken for
  nothing-to-do, a finished run and a refusal verdict are not locks, and an abandoned run is taken
  over rather than obeyed forever
  (`fichero-server/tests/unit/maintenance/test_project_conversion_resume.py::TestTheLock`, six tests).
- `source.convert.snapshot-first-and-proved` — **[OK]** (→ #4998) no page converts until a snapshot
  of the project exists and has been read back and checked; that snapshot is kept out of the
  ordinary tidy-up until the conversion is finished and its report has been seen. Proved against
  the RESTORE SOURCE rather than a derivative, so a proof cannot pass on a copy a restore would
  not use; a project reporting no tables is treated as blindness and not as cleanliness
  (`fichero-server/tests/unit/maintenance/test_project_conversion_preflight.py::TestIsThereAWayBack`, and
  `::TestTheReport::test_the_snapshot_stays_pinned_until_the_run_is_finished_and_seen`).
- `source.convert.refused-when-disk-is-short` — **[OK]** (→ #4998) with too little free disk nothing
  starts and nothing is half done; the report says how much is needed; it tries again at the next
  open. The margin is applied, the estimate grows with the work, and an unreadable disk RAISES
  rather than assuming room
  (`fichero-server/tests/unit/maintenance/test_project_conversion_preflight.py::TestWillItFit`) — that last
  one is the difference between a gate and a gate that opens when it cannot see.
- `source.convert.the-machine-stays-usable` — **[OK]** (→ #4998) it runs at background priority, a
  page at a time, and gives way to a person's work; measured, not assumed — and the test MEASURES
  it: a person's read AND edit both finish while a conversion runs, and the runner yields between
  every page
  (`fichero-server/tests/unit/maintenance/test_project_conversion_measured.py::TestTheMachineStaysUsable`).
- `source.convert.a-page-is-all-or-nothing` — **[OK]** (→ #5222, #4998) each page converts in one transaction or not at
  all; a page that cannot convert is recorded with its reason, skipped, and still reads from
  its block as before; the rest carry on. A fault raised INSIDE a page's transaction, after its
  pass and segments were written, leaves that page with none of them
  (`fichero-server/tests/unit/maintenance/test_conversion_starts_on_open.py::test_a_fault_inside_a_pages_transaction_leaves_that_page_untouched`);
  a stored box a later validator refuses is named against its page and the rest convert
  (`test_every_legacy_shape_converts.py::test_a_stored_box_a_later_validator_refuses_is_named_and_the_rest_convert`).
- `source.convert.stops-starts-and-repeats-safely` — **[OK]** (→ #4998) quitting part-way loses
  nothing; the next open carries on; running it again over a converted project writes nothing. A
  resumed run ends EXACTLY where an uninterrupted one would, a third run writes nothing and files
  no report, and progress survives a close and reopen
  (`fichero-server/tests/unit/maintenance/test_project_conversion_resume.py::TestStoppingAndResuming`).
- `source.convert.half-done-reads-the-same` — **[OK]** (→ #4998) at every moment of a conversion,
  every reader gets the same answer for every page as before it started, but for the ids. Pinned
  across surfaces rather than one: the page text at every point, a claim anchored by rectangle
  still revealing after its page converts, and the artifact still reporting its own boxes
  (`fichero-server/tests/unit/maintenance/test_project_conversion_invisible.py::TestAHalfConvertedProjectReadsTheSame`).
- `source.convert.report` — **[OK]** (→ #5222, #4998) each project has a kept report: what converted, what could not and
  why, where the snapshot is, how long it took. The kept `ConversionRun` of each run, read at
  `GET /api/conversion/status` (running, verdict, pages converted and skipped, each page not
  converted with its reason, pages and results still waiting asked of the database now, the
  snapshot, the disk a refusal needed, and results left as they were -- the old `segmentation`
  artifact, which no engine producer wrote); `POST /api/conversion/{run_id}/seen` records that a
  person saw it, which is what releases the snapshot. Pinned by
  `fichero-server/tests/unit/maintenance/test_conversion_starts_on_open.py::test_the_status_route_reports_the_run_what_is_left_and_what_was_not_converted`.
- `source.convert.words-move-with-the-boxes` — **[PARTIAL]** (#4998, #5066) once readings are on segments, converting a page
  also gives each segment its words as a reading with its maker, so the old block is no longer
  the only home of the text and a converted result can be deleted again. The words half is built
  (slice 8b, `segment_conversion._readings_from_conversion`; pinned by
  `fichero-server/tests/unit/workflows/test_a_new_result_is_a_pass_at_once.py::test_each_converted_box_gets_its_words_as_a_reading_with_the_machines_maker`).
  Deleting a converted result is NOT: its kept block is also the rectangle-to-position table
  `resolve_anchor` needs (#5066, ruled: move that table out of the artifact).
- `source.convert.box-origins-are-their-own-record` — **[OK]** (→ #5066, ruled 2026-09-26: "promote the
  table out of the artifact") where each converted box WAS -- its rectangle, the picture it was
  measured on, the result and its position in it -- is written at conversion as a small record of
  its own, one per segment, keyed by the segment's id (`ConvertedBoxOrigin`). The fact is not new:
  the archive keeps it today inside the result's block, which is the thing a person will want to
  delete. `resolve_anchor` matches an unpointed anchor against these records, never the block. A
  library converted before this gains them once, at its first open after the change: only results
  converted and not yet recorded are read, so a later open reads none. Recording repeats safely.
  Until a result is recorded its block still answers, so the reads are the same throughout. Pinned
  by `fichero-server/tests/unit/maintenance/test_converted_box_origins.py` (written at conversion; a
  mark follows its box with the result's row gone; a library converted before reads the same, then
  gains the records once; the recording stops between results when the library closes).
- `source.convert.a-converted-result-can-be-deleted` — **[PARTIAL]** (→ #5066) a converted result can be
  deleted once every box has its origin recorded and its words are a reading on its segment
  (`source.convert.words-move-with-the-boxes`). Its passes, segments and readings stay; a mark drawn
  before conversion still follows its box after the delete; the delete is undone like any other,
  bringing the result back exactly as it was. Until both hold for a result, the delete is refused
  with the reason, as today. What the page's working-pass choice reads from the result -- that it is
  a PDF's own text layer, and that a person made, reviewed or corrected it (the SACRED signals,
  #5222) -- is kept on its pass when the result goes, so the page's text and its working pass are
  the same after the delete as before it (found auditing the delete, 2026-09-30: the ranking read
  both from the result, so deleting a person's corrected result would have demoted their pass).
  Built 2026-09-30 in the engine: the guard refuses only while a segment has no origin or a box's
  words no reading, naming which; the pass keeps `source_artifact_type` and
  `source_holds_a_persons_work`; it also refuses while a person's correction made before
  conversion still names the result as what it corrects (`derived_from_artifact_id`); a deleted
  result comes back only with the boxes its origins
  record (a single undo refuses others; a bulk restore brings it back without them). Pinned by
  `fichero-server/tests/unit/maintenance/test_converted_box_origins.py` (the page keeps its words,
  boxes, label, working pass and marks; a person's corrected result keeps its rank; undo brings it
  back exactly; a forged snapshot is refused; no origins, no delete) and
  `tests/unit/api/test_conversion_undo_and_refusals.py` (no readings, no delete, and the refusal
  says why). Not yet: the pass's own `text` reads null once its result is gone (its segments carry
  the words), and no app surface offers the delete.

## Test matrix

To be filled at approval. The hard gate will be: the same segment gives the same id, shape,
image and picture from the engine, MCP, the command line and the app.

## Rulings

- **2026-10-04 (#5395):** Apple Vision's word boxes are kept (they are worth showing later), and the
  word pass keeps running, but they are stored compactly: one packed row per line holding that line's
  words with integer coordinates, not one row per word (about 2 MB a photo is too much). See
  `source.words.packed-per-line`.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.

Still open, from #5026 ("What a tool is given"): (1) the **budget**: how many tokens or segments a
tool may be sent, who sets it (the tool, the model, the project), and what is left out first when
it is exceeded; nothing rules this yet. (2) how a **character stretch** inside one reading is
addressed as a scope, and whether it needs the anchor's text-position form or a segment of its
own. (3) how the **maker mark** is written into the compact line, and how a project's own working-pass
rule shows up there when the page holds several readings. (4) whether **more than one model**
receiving the same scope is one call or several. Settled and not reopened here: the trust order
(a person's line outranks a machine's), the compact text form rather than SVG, and cutting the
picture to the shape.
- **Answered** (design lead 2026-10-04, applying the spec's lean): (2) A character stretch inside one reading is addressed by the anchor's text-position form, with no new segment.
- **Answered** (design lead 2026-10-04, by the existing design): (3) A tool is given only the working pass's reading (ruled 2026-09-26, "What a tool is given"), and the maker tag is built as `provenance_kind`.
- **Answered** (design lead 2026-10-04, applying the spec's lean): (4) Sending the same scope to more than one model is several calls, one per model, fanned out.

## Triaged from the backlog (2026-10-04)
- `source.tool.each-model-gets-its-own-call` **[GAP]** (#5026): when the same scope goes to more than one model, each model gets its own call, fanned out, never one combined call.
- `segments.claims-carry-box-anchor` — **[GAP]** (#970) a claim extracted from transcribed text carries the box/segment it was read from
- `geometry.review-word-boxes-on-ink` — **[GAP]** (#4615) word boxes in the Transcription Review artifact sit over the right ink (data-side defect on 9_Hoja_534_Recto).
- `source.pass.nothing-drawable-never-covers` **[BROKEN]** (#4955): a result whose shapes are all unusable (zero width or height) never hides a lower-ranked result that has boxes to draw, and the page says the chosen result had no usable shapes. (Items 1-3 and the audit-id fix landed in cb304e65a.)
- `source.store.dense-page-reads-whole-in-bound` **[GAP]** (#4956): a dense page (20,000 segments) reads whole, with no filter and cold, within the bound the segment editor needs, and moving one box on an already converted page does not re-read every result on that page.
- `source.pass.keeps-its-own-text` **[GAP]** (#5067): a pass holds its own whole text, even with no lines or with lines that come later, a source may carry several text passes and the person chooses the canonical one, and workflows write their text as a pass, including when they run on lines. (Ruled by the maintainer 2026-10-01.)
- `source.segment.reference-opens-on-every-device` **[GAP]** (#5164): a fichero:segment link opens its page with the segment selected on iOS as on the Mac, and a link that cannot be resolved says why instead of only beeping. (Links section 13494cbb7 and the macOS handler e041b2882 landed; `source.link.any-depth` and `source.form.label-and-answer` stay owed.)
- `source.segment.carry-from-the-review` **[GAP]** (#5165): after accepting a proposed match in the Segments pane, the person can carry its readings and marks across from the same list, and the head's count updates as soon as a match is reviewed. (Review itself landed in fca401334.)
- `source.tool.run-on-selection` **[GAP]** (#5230): one Run on Selection… (Segment menu, right-click, the Inspector for one segment) runs a segment-scoped tool on just the selected lines, words or regions: transcribe (VLM, Kraken, Apple Vision) writes a machine reading on each, word segmentation and line detection write child segments under each. One ⌘Z per run, a pre-run estimate for the selection, and never over a person's reading.
- `source.words.packed-per-line` **[GAP]** (#5395): Apple Vision's word boxes are kept and the word pass keeps running, but a line's words are stored as one packed row per line with integer coordinates, not one row per word, so a photo's words no longer cost about 2 MB; the words still read back with their boxes for showing later. (Ruled 2026-10-04.)
