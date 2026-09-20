# Source Model — Segments and geometry — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — part of the "How Fichero represents a source" section: what a segment is, how
> segments nest, how they are ordered and linked, and how a page can have several images.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first (the rulings and the words are there). The evidence is in `source-survey.md`.
> Behaviour ids below have **no tags yet**. Unless "What exists today" in the foundation says
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
carried across the match onto the new segment, and the trail stays visible. A machine may
*propose* matches; only a person accepts them.

When segments are **merged**, one id goes on and the others leave a **forwarding note**
("merged into X"). When one is **split**, its id stays on one part and a forwarding note says
where the rest went. When one is **deleted**, it leaves a forwarding note that says so, and
the delete can be undone. Forwarding notes are never removed. Following an old id to where
that ink is now is one lookup, the same from the app, MCP and the command line. If the trail
ends at a delete, Fichero says "this was deleted, by whom, when", and never shows nothing.

**How this grows from what exists.** Today's shared anchor (`SourceAnchor`) stays the one way
to say *where*. A segment is a record with an id whose *place* is an anchor; today's
boxes-in-a-list become segments. There is one addressing scheme, not two. But the anchor as
built cannot yet say everything this design needs (read on disk, `models/anchors.py`: one
rectangle, which must have width and height; one polygon, which must be closed with three
points or more; no id; no baseline). **What the anchor must gain:** a point; an open path; a
baseline that can curve; more than one shape; a text angle; a stretch of time. Its
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
  Today geometry names its image once for a whole result, and an image has no checksum or
  scale of its own; both are part of this design, not built.

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
attribute. Checked in the running app on 2026-09-19, read-only: the entries are there and
dated, but an entry looked at carried **no region at all** (`region_in_parent` and `bbox`
empty; its note says the page's dimensions were not known when it was made). So the entry is
structured data with nothing tying it back to its part of the page.

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
So a table on a page (an account book, a census return, a register, a palaeographer's table
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

One pass is the **working pass** for a source: the one the Reader, search and export use
unless told otherwise. What may become the working pass follows **the project's rule** (ruled
2026-09-19). In a *strict* project, which is how every new project starts, only a person
makes a pass the working pass: a machine's pass (from a chain run automatically, an import,
the synced folder) is there to look at and compare. In a *relaxed* project the newest pass
counts, and a person's always outranks a machine's.

### Reading orders

A source has one or more **named reading orders**. Each is a sequence of segments with an
author and a certainty: the order as written; the order that reading-marks impose; the order
of a commentary. An order can nest (regions in order, lines in order inside each). "Next" and
"previous" are always asked *of a named order*.

### Links

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
what changed. Edits are never silently merged or silently lost.

### What is worked out from a segment

Some things are computed from a segment and its readings and can always be computed again:
its picture; search entries; **vectors** for finding similar images or text; the **words and
grammar** of a reading (tokens, parts of speech, lemmas), which are stretches of a reading.
They are kept with the segment and the reading they came from, with the model and version
that made them, and are absent, not faked, when they have not been made. (This is what
`segment-representations.md` calls representations.)

### Statements

A knowledge-graph claim or entity mention points at a segment id (and, if needed, a stretch
of a reading). Because ids last, a claim survives the page being re-segmented or
re-transcribed. From a segment you can list what is said about it; from a statement you can
go to its ink.

### Versions

Every change to a segment (shape, kind, pass, order, links) is a new version of *that
segment*, with who, when and why. A segment's history can be read, compared and restored by
itself. Deleting a segment is a version too, and can be undone. Nothing is rewritten by batch.

### Its picture

Any segment can be asked for its picture: the image cut to its shape (not just its box), at a
chosen size, with or without a margin, from a chosen image of the page. For a line, also
straightened along its baseline, which is what a recogniser wants. Pictures are made when
asked for and may be cached; they are never the record.

### Storage (the one big change)

Today all the boxes of a result are one block of data. This design needs **one record per
segment**, so the store can answer "the lines of this page", "this word's history", "every
segment in this hand". Existing projects are never converted by batch (see the foundation's
open questions on how their segments get ids).

## Behaviors (ids proposed; untagged until approval)

Identity and versions
- `source.segment.lasting-id` — a segment keeps its id through move, reshape, re-read and
  re-type, and an id is never given to another segment.
- `source.segment.rerun-is-new-pass` — segmenting a page again adds a pass; nothing existing
  is replaced or renumbered.
- `source.segment.carry-across-a-match` — across an accepted match, readings, marks and
  statements can be carried to the new segment, leaving a visible trail.
- `source.segment.versioned-alone` — one segment's history can be read, compared and restored
  without touching others.
- `source.segment.delete-is-undoable` — a deleted segment can be brought back with everything
  that pointed at it.

Shape and images
- `source.segment.shape-kinds` — a segment's shape is a point, a line, an area or a stretch of
  time; it may have more than one.
- `source.segment.box-is-derived` — the box is worked out from the shape and cannot be edited
  apart from it.
- `source.segment.curved-baseline` — a line's baseline can curve; direction can follow it.
- `source.segment.names-its-image` — every shape names the image it was measured on; the image
  has a size and a checksum.
- `source.segment.no-guessing-across-images` — a shape is shown on another image of the page
  only through a known alignment; otherwise Fichero says it cannot.
- `source.segment.picture-by-shape` — any segment's picture can be had, cut to its shape, from
  a chosen image, at a chosen size; a line's can be straightened.

Structure
- `source.segment.one-primitive` — every level of the ladder, and every non-text thing, is a
  segment with a kind.
- `source.segment.open-kinds` — kinds come from a standard list a project can extend; a model's
  own label is kept beside the tidy kind.
- `source.segment.levels-optional` — any level may be absent and added later without
  disturbing others.
- `source.segment.physical-and-logical` — a segment can sit in the physical ladder and in a
  logical unit that crosses pages or documents.
- `source.segment.flow` — text that continues across a column, page or picture is a named
  reading order and reads straight through.
- `source.segment.furniture` — page furniture is marked, and a reading can leave it out.
- `source.segment.table-cells` — a table's cells are segments with row, column, spans and
  header kind.
- `source.segment.node-has-its-region` — a node made from part of a page (a diary entry, a
  letter, a register entry) is a segment of that page with a shape, never structured data
  with no tie to its ink.
- `source.segment.structured-from-prototype` — a segment can be made from a prototype and carry
  its structured attributes; each attribute can point at the words it came from.
- `source.segment.table-as-data` — a table segment can be read out as rows and columns of data
  in which every cell still points at its segment.
- `source.segment.marks-have-state` — a tick, cross or cancellation is a segment with a state.

Passes, orders, links
- `source.pass.named-authored` — segments live in named passes, each with an author; passes
  can be shown, hidden and compared.
- `source.pass.never-overwrites` — two layouts of one page are two passes, both kept.
- `source.pass.working-follows-project-rule` — in a strict project a machine's pass never
  becomes the working pass until a person makes it so; in a relaxed project the newest pass
  counts and a person's outranks a machine's; a new project is strict.
- `source.pass.working` — one pass is the working pass the Reader, search and export use by
  default.
- `source.order.named-multiple` — a source can have several named reading orders, each with an
  author and certainty.
- `source.order.next-previous` — next and previous are always asked of a named order.
- `source.link.typed` — a link between segments has a type, direction, author and certainty;
  types come from an extendable list.
- `source.link.any-depth` — links chain (a comment on a comment), and can cross sources.
- `source.link.both-ways` — from either end of a link you can reach the other.

Maps
- `source.geo.control-points` — a point on an image can be tied to a coordinate on the earth,
  with author and certainty.
- `source.geo.segment-to-world` — on a georeferenced image, any segment can give its place in
  the world.
- `source.geo.names-a-place` — a label on a map can be linked to the place entity it names.

Canvas
- `source.canvas.segment-as-card` — any source, page or segment can be placed on a canvas as a
  card with its picture and chosen reading, without being copied.
- `source.canvas.links-are-links` — a link drawn between cards on a canvas is a typed link of
  the source model.

Pointing and statements
- `source.point.by-id-or-span` — a thing points at a segment by id, or at a stretch of one of
  its readings.
- `source.point.text-is-derived` — a page's text is worked out from segments and a reading
  order; it is never the master.
- `source.statement.on-segment` — a claim or mention points at a segment id and survives
  re-segmentation and re-transcription.
- `source.statement.both-ways` — from a segment, what is said about it; from a statement, its
  ink.

Identity, continued
- `source.segment.match-record` — "this new segment is that old one" is a record of its own
  with an author and certainty; ids do not move; a machine may propose, a person accepts.
- `source.segment.forwarding-notes` — a merged, split or deleted segment leaves a permanent
  forwarding note; following an old id is one lookup; a trail ending in a delete says so.
- `source.segment.citable` — a segment has one stable reference that opens it in the app and
  resolves over MCP and the command line, following forwarding notes.
- `source.segment.time-span` — a segment of a recording is a stretch of time (with an area,
  for video) and behaves as any other segment.
- `source.segment.opening` — a shape drawn across two facing pages belongs to the opening and
  resolves onto each page.
- `source.image.alignment-points` — two images of one page can be tied by points so shapes
  cross between them.
- `source.image.rescan-strands-nothing-silently` — after a rescan, shapes stay on their image
  and Fichero says which passes have not crossed over.
- `source.image.physical-scale` — an image can carry a scale so a segment's size can be given
  in millimetres.
- `source.edit.stale-is-refused` — an edit made against an old version of a segment is
  refused, with what changed.
- `source.derived.recomputable` — pictures, search entries, vectors and word-level analysis
  name the segment, reading, model and version they came from, and are absent when not made.

Storage
- `source.store.ids-on-first-edit` — opening a page with old geometry shows its segments
  without writing anything; the first edit writes that page's segments once, as one audited
  action that can be undone. (Ruled 2026-09-19.)
- `source.store.bounded-reads` — a page's segments come back by level and by area, in bounded
  time, however many there are.
- `source.store.record-per-segment` — the store can answer questions about single segments
  (the lines of a page; a word's history; all segments in a hand).
- `source.store.no-batch-rewrite` — an existing project's geometry is never converted by
  batch.

## Test matrix

To be filled at approval. The hard gate will be: the same segment gives the same id, shape,
image and picture from the engine, MCP, the command line and the app.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
