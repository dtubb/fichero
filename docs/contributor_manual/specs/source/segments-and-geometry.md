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
points or more; no id; no baseline). **What the anchor must gain:** a point; an open path; a
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
the engine (an iPad offline) is **not supported** in this work: a queue of stale edits
refused one by one is no way to work, and reconciling them is a design of its own.

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

### Storage (the one big change)

Today all the boxes of a result are one block of data. This design needs **one record per
segment**, so the store can answer "the lines of this page", "this word's history", "every
segment in this hand". Existing projects are never converted by
batch: a page's boxes become segments on that page's first edit (ruled 2026-09-19; rules
below).

### First-edit conversion: the rules

- **What counts as an edit.** Any action that changes a box's shape, kind, membership or order:
  what `artifact.regions_edit` does today. Adding a reading, a mark or a claim to a box does
  **not** convert its page. A new machine run does **not** convert the old boxes: it writes
  segment records for itself, and the old block stays as it is until someone edits it.
- **One action, one audit record.** The conversion happens inside the edit's own action; there
  is never a page with converted records nobody asked for.
- **One page for each conversion.** No action converts more than one document's boxes, and no
  migration ever writes segment records.
- **Every result with boxes becomes its own pass**, so nothing is lost and they can be compared
  (default taken; in the morning file).
- **Undo undoes the edit and keeps the conversion** (changed 2026-09-20; design, default taken,
  in the morning file). A converted page with no edit reads exactly as it did before, so
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
- `source.segment.lasting-id` — **[GAP]** (#4921) a segment keeps its id through move, reshape, re-read and
  re-type, and an id is never given to another segment.
- `source.segment.rerun-is-new-pass` — **[GAP]** (#4921) segmenting a page again adds a pass; nothing existing
  is replaced or renumbered.
- `source.segment.carry-across-a-match` — **[GAP]** (#4922) across an accepted one-to-one match, readings and
  marks are copied (never moved) to the new segment, each copy recorded against the match; a
  statement is never copied: the same claim gains one more place it rests on;
  undoing the carry removes the copies; a match that is not one-to-one carries no reading and
  says so.
- `source.segment.versioned-alone` — **[GAP]** (#4923) one segment's history can be read, compared and restored
  without touching others.
- `source.segment.delete-is-undoable` — **[GAP]** (#4923) a deleted segment can be brought back with everything
  that pointed at it.

Shape and images
- `source.segment.shape-kinds` — **[GAP]** (#4925) a segment's shape is a point, a line, an area or a stretch of
  time; it may have more than one.
- `source.segment.box-is-derived` — **[GAP]** (#4921) the box is worked out from the shape and cannot be edited
  apart from it.
- `source.segment.curved-baseline` — **[GAP]** (#4925) a line's baseline can curve; direction can follow it.
- `source.segment.names-its-image` — **[GAP]** (#4919) every shape names the image it was measured on; the image
  has a size and a checksum.
- `source.segment.no-guessing-across-images` — **[GAP]** (#4926) a shape is shown on another image of the page
  only through a known alignment; otherwise Fichero says it cannot.
- `source.segment.picture-by-shape` — **[GAP]** (#4925) any segment's picture can be had, cut to its shape, from
  a chosen image, at a chosen size; a line's can be straightened.

Structure
- `source.segment.one-primitive` — **[GAP]** (#4921) every level of the ladder, and every non-text thing, is a
  segment with a kind.
- `source.segment.open-kinds` — **[GAP]** (#4921) kinds come from a standard list a project can extend; a model's
  own label is kept beside the tidy kind.
- `source.segment.levels-optional` — **[GAP]** (#4927) any level may be absent; adding word segments under a
  line changes no id, shape or reading of the line or its region.
- `source.segment.physical-and-logical` — **[GAP]** (#4927) a segment can sit in the physical ladder and in a
  logical unit that crosses pages or documents.
- `source.segment.flow` — **[GAP]** (#4930) text that continues across a column, page or picture is a named
  reading order and reads straight through.
- `source.segment.furniture` — **[GAP]** (#4927) page furniture is marked, and a reading can leave it out.
- `source.segment.table-cells` — **[GAP]** (#4928) a table's cells are segments with row, column, spans and
  header kind.
- `source.segment.node-has-its-region` — **[GAP]** (#4927) a node made from part of a page (a diary entry, a
  letter, a register entry) is a segment of that page with a shape, never structured data
  with no tie to its ink.
- `source.segment.structured-from-prototype` — **[GAP]** (#4927) a segment can be made from a prototype and carry
  its structured attributes; each attribute can point at the words it came from.
- `source.segment.table-as-data` — **[GAP]** (#4928) a table segment can be read out as rows and columns of data
  in which every cell still points at its segment.
- `source.segment.marks-have-state` — **[GAP]** (#4928) a tick, cross or cancellation is a segment with a state.

Passes, orders, links
- `source.pass.named-authored` — **[GAP]** (#4921) segments live in named passes, each with an author; passes
  can be shown, hidden and compared.
- `source.pass.never-overwrites` — **[GAP]** (#4921) two layouts of one page are two passes, both kept.
- `source.pass.working-follows-project-rule` — **[GAP]** (#4929) in a strict project a machine's pass never
  becomes the working pass until a person makes it so; in a relaxed project the newest pass
  counts and a person's outranks a machine's; a new project is strict.
- `source.pass.working` — **[GAP]** (#4929) the Reader, search and export use one pass: the one a person chose,
  or the newest, labelled unchosen, if nobody has; it is worked out, never a stored flag.
- `source.order.named-multiple` — **[GAP]** (#4930) a source can have several named reading orders, each with an
  author and certainty.
- `source.order.next-previous` — **[GAP]** (#4930) next and previous are always asked of a named order.
- `source.link.typed` — **[GAP]** (#4931) a link between segments has a type, direction, author and certainty;
  types come from an extendable list; it is the one typed-link record that the existing note,
  canvas and prediction links converge on, not a further kind.
- `source.link.any-depth` — **[GAP]** (#4931) links chain (a comment on a comment), and can cross sources.
- `source.link.both-ways` — **[GAP]** (#4931) from either end of a link you can reach the other.

Maps
- `source.geo.control-points` — **[GAP]** (#4933) a point on an image can be tied to a coordinate on the earth,
  with author and certainty.
- `source.geo.segment-to-world` — **[GAP]** (#4933) on a georeferenced image, any segment can give its place in
  the world.
- `source.geo.names-a-place` — **[GAP]** (#4933) a label on a map can be linked to the place entity it names.

Canvas
- `source.canvas.segment-as-card` — **[GAP]** (#4931) any source, page or segment can be placed on a canvas as a
  card with its picture and chosen reading, without being copied.
- `source.canvas.links-are-links` — **[GAP]** (#4931) a link drawn between cards on a canvas is a typed link of
  the source model.

Pointing and statements
- `source.point.by-id-or-span` — **[GAP]** (#4932) a thing points at a segment by id, or at a stretch of one of
  its readings.
- `source.point.text-is-derived` — **[GAP]** (#4932) a page's text is worked out from segments and a reading
  order; it is never the master.
- `source.statement.on-segment` — **[GAP]** (#4932) a claim or mention points at a segment id, keeps a copy of
  its anchor beside it, and survives re-segmentation and re-transcription; a claim on an
  unconverted page points by its anchor alone.
- `source.point.anchor-names-its-segment` — **[GAP]** (#4932) the one anchor every reading, mark, support and
  claim already carries gains an optional lasting segment id; the id is the pointer and the
  stored shape is the record of where the ink was; one resolver answers with the live
  segment's current shape, or the stored shape when the segment was deleted. One shape for
  all four, no new column on any of them; an old record reads as having none.
- `source.point.unpointed-anchor-follows-its-box` — **[GAP]** (#4932) an anchor with no segment id, whose
  rectangle equals a box of a converted result, is resolved through that box's segment at
  read time, storing nothing, so a mark drawn before conversion follows its box when it moves.
- `source.statement.old-segment-field-left-alone` — **[GAP]** (#4932) the claim field `source_segment_id`, which
  predates this model and names an entry in a segmentation artifact, keeps its meaning and
  its data, is described as such in the contract, and is never given a segment record's id.
- `source.statement.both-ways` — **[GAP]** (#4932) from a segment, what is said about it; from a statement, its
  ink.

Identity, continued
- `source.segment.match-record` — **[GAP]** (#4922) "this new segment is that old one" is a record of its own
  with an author and certainty; ids do not move; a machine may propose, a person accepts.
- `source.segment.forwarding-notes` — **[GAP]** (#4922) a merged, split or deleted segment leaves a permanent
  forwarding note; following an old id is one call; the walk raises past 64 steps; a merge
  into a segment that already forwards to the source is refused; a trail ending in a delete
  says so.
- `source.segment.citable` — **[GAP]** (#4922) a segment has one stable reference that opens it in the app and
  resolves over MCP and the command line, following forwarding notes.
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
- `source.edit.stale-is-refused` — **[GAP]** (#4923) an edit made against an old version of a segment is
  refused, with what changed.
- `source.derived.recomputable` — **[GAP]** (#4925) pictures, search entries, vectors and word-level analysis
  name the segment, reading, model and version they came from, and are absent when not made.

The read seam and events
- `source.seam.read-either-store` — **[GAP]** (#4919) one engine call returns a source's segments whether they
  live in a block of boxes or in segment records; its answer has the same shape either way.
- `source.seam.maker-for-each-segment` — **[GAP]** (#4919) every segment read through the seam says
  who made it, in the one maker vocabulary, set by the engine: a person when the box itself
  proves a person drew it, otherwise its pass's maker; never supplied by a caller, never
  defaulting to a person; a pass may hold segments by different makers.
- `source.seam.area-applies-to-either-store` — **[GAP]** (#4985) asking for a page's segments by area narrows
  them the same way whether they come from segment records or from a result's block of boxes.
  (Today the block branch ignores `area` and applies only `kind`; found by the slice 6 recon,
  2026-09-20. Until it is fixed, "the page reads the same before and after conversion" cannot
  be tested with an area.)
- `source.seam.provisional-ids-refused` — **[GAP]** (#4919) an id read from a block of boxes is marked
  provisional, and every write path refuses one with a typed error.
- `source.events.segment-ids` — **[GAP]** (#4920) a change event names the segments and passes that changed, so a
  window updates those and nothing else.

Storage
- `source.store.one-page-per-conversion` — **[GAP]** (#4924) no action converts more than one document's boxes,
  and no migration writes segment records.
- `source.store.undo-first-edit-keeps-conversion` — **[GAP]** (#4924) undoing the first edit undoes the edit
  and keeps the page's segment records; the old block is never restored over them, and the old
  region action is unreachable on a converted result. (Replaces
  `source.store.conversion-undo-leaves-nothing`, 2026-09-20; default taken, in the morning file.)
- `source.store.conversion-changes-nothing-seen` — **[GAP]** (#4924) a page read just before and just after
  conversion is the same in every field but the ids: kinds, shapes, order, words, page numbers
  and who made each box.
- `source.store.conversion-ids-repeatable` — **[GAP]** (#4924) a converted box's id follows from its result and
  its position, so converting the same page again, eagerly or on first edit, gives the same
  ids; a provisional id resolves to the real one on reads and is still refused on writes.
- `source.store.converted-boxes-keep-their-maker` — **[GAP]** (#4924) converted boxes are stored as their
  maker's (machine, the person who drew them, or unknown), never as the person whose edit
  caused the conversion; only the edited segment becomes that person's.
- `source.store.old-app-still-works` — **[GAP]** (#4924) until the app draws from segments, a converted result
  is served with its boxes filled from the segment records in one order, and an edit by
  position lands on the box shown at that position.
- `source.store.conversion-reports-exact-matches` — **[GAP]** (#4924) the converting action lists each reading,
  mark, support and claim whose rectangle matches a converted box exactly, with the segment id
  it would take, and changes none of them. (Replaces `…conversion-repoints-exact-matches`,
  2026-09-20: there is nowhere lawful to write the id until `source.point.anchor-names-its-segment`.)
- `source.store.ids-on-first-edit` — **[GAP]** (#4924) opening a page with old geometry shows its segments
  without writing anything; the first edit writes that page's segments once, as one audited
  action that can be undone. (Ruled 2026-09-19.)
- `source.store.bounded-reads` — **[GAP]** (#4921) a page's segments come back by kind and by area, never "all
  of a project"; one page at one kind returns in under 200 ms with 200,000 segment records in
  the source (threshold in the morning file).
- `source.store.record-per-segment` — **[GAP]** (#4921) the store can answer questions about single segments
  (the lines of a page; a word's history; all segments in a hand).
- `source.store.no-batch-rewrite` — **[GAP]** (#4924) an existing project's geometry is never converted by
  batch.

## Test matrix

To be filled at approval. The hard gate will be: the same segment gives the same id, shape,
image and picture from the engine, MCP, the command line and the app.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
