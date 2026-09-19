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
order, in a layer, and its links to other segments. Readings, hands and certainty are in
`readings-and-apparatus.md`; language and signs in `languages-scripts-glyphs.md`.

## The design

### Identity

A segment has an id that lasts. It keeps the id when it is moved, reshaped, re-read,
re-typed or moved to another layer. When a page is segmented again by a model, the new run
arrives as a **new layer** with new segments; it does not replace or renumber the old ones. A
person (or a rule they approve) may then say "this new line is that old line", which carries
the old id, its readings, marks and statements forward.

Merging keeps one id and records the others as merged into it. Splitting keeps the id on one
part and records where the rest went. Either way, anything that pointed at an old id can still
be followed to where that ink is now. Nothing that points at a segment is ever left dangling.

This grows from what exists. The shared anchor (`SourceAnchor`) stays the one way to say
"where". A segment is the lasting thing that *has* an anchor; today's boxes-in-a-list become
segments with anchors. There is still one addressing scheme, not two.

### Shape

- A shape is a **point**, a **line** (open path), or an **area** (closed polygon; a box is the
  simplest one). A segment may have more than one shape when the ink really is in two places
  (a word broken across a line end).
- A line of writing also has a **baseline**, which may curve, and may have a top line.
- The **box** around a shape is always worked out from the shape, never typed in.
- A shape may have a **text angle**, apart from any tilt of the whole page.
- Every shape names **the image it was measured on**. Coordinates are fractions of that image,
  from the top-left. The image record carries its pixel size and a checksum, so a shape can
  never be silently drawn over the wrong picture.

### Several images of one page

A page can have many images: the original, an enhanced one, a split half, ultraviolet,
raking light. A shape drawn on one can be shown on another only when Fichero knows how the
two images line up (the same frame; a crop; a recorded transform). If it does not know, it
says so and does not guess. This is today's rule (`ui/reader-overlay-frame-identity.md`),
kept.

A reading may be tied to the image it was read from: "this under-text was read from the
ultraviolet image".

### The ladder, and two kinds of structure

```
collection / codex unit  >  group of pages  >  page  >  region  >  line or column
                                                     >  word  >  character  >  stroke
```

- Every level is a segment with a **kind**. Kinds come from a standard list (SegmOnto's zones
  and lines, plus word, character, stroke, and the non-text kinds: picture, music, seal, stamp,
  table, table cell, diagram, map, mark, damage, blank). A library can add its own. When a
  model supplied the kind, the model's own label is kept beside the tidy one.
- Any level can be missing. Finer levels can be added later.
- **Physical structure** is the ladder: what is where on the object (codex unit, quire, leaf,
  page, region…). **Logical structure** is what the text is: a letter, a chapter, a diary
  entry, a legal case across several documents. Both are trees over the same segments, and a
  segment can sit in both. A letter that starts on one page and ends on the next is one logical
  unit over two physical pages.
- **A flow** joins text that continues: across a column break, a page turn, or around a
  picture. A reading of the flow reads straight through.
- **Page furniture** (running heads, page numbers, catchwords, quire signatures) is marked as
  furniture, so a reading of the text can leave it out and an export can put it where the
  format wants it.

### Tables and forms

A table is a segment; its cells are segments with a row, a column, how many rows and columns
they span, and whether they are a header. A cell's text is ordinary lines and words inside it.
A form's "label" and "filled-in answer" are two segments joined by a typed link. Ticks,
crosses and cancellation marks are **mark** segments with a state.

### Layers

A layer is a named set of segments on a source, with an author (a person, a model run, an
import). Examples: a model's proposed layout; a person's corrected layout; a second
scholar's competing layout; an imported PageXML file; the glosses; the pictures. Layers can be
shown, hidden and compared. They never overwrite each other. Two people disagreeing about
where a line ends is two layers, both kept: disagreement is data.

One layer is the **working layer** for a source: the one the Reader, search and export use
unless told otherwise.

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
*translates*, *same as*, *names* (a label on a map to the place). A library can add types.
Links can chain to any depth (a comment on a comment on the text).

### Maps and plans

An image can carry **control points**: a point segment whose reading is a coordinate on the
earth. A few of them georeference the sheet. After that, any segment on it can be asked for
its place in the world, the sheet can be laid over a modern map, and a place name on it can
be linked to the place in the knowledge graph. Control points have authors, certainty and
versions like any other segment.

### Two ways to point

Something can point at a segment **by its id** (the normal way), or at **a stretch of a
reading's text** (characters 14 to 22 of this reading of this line). The second is needed for
things finer than the segments that exist yet (a name inside a line that has no word
segments). When word segments are later made, the pointer can be moved onto them. The text of
a page is always worked out from its segments and a reading order; it is never the master
copy.

### Statements

A knowledge-graph claim or entity mention points at a segment id (and, if needed, a stretch
of a reading). Because ids last, a claim survives the page being re-segmented or
re-transcribed. From a segment you can list what is said about it; from a statement you can
go to its ink.

### Versions

Every change to a segment (shape, kind, layer, order, links) is a new version of *that
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
segment in this hand". Existing libraries are never converted by batch (see the foundation's
open questions on how their segments get ids).

## Behaviors (ids proposed; untagged until approval)

Identity and versions
- `source.segment.lasting-id` — a segment keeps its id through move, reshape, re-read, re-type.
- `source.segment.rerun-is-new-layer` — segmenting a page again adds a layer; nothing existing
  is replaced or renumbered.
- `source.segment.carry-forward` — a person can match a new segment to an old one; readings,
  marks and statements follow.
- `source.segment.merge-split-followable` — after a merge or split, every old id still leads to
  where that ink is now.
- `source.segment.versioned-alone` — one segment's history can be read, compared and restored
  without touching others.
- `source.segment.delete-is-undoable` — a deleted segment can be brought back with everything
  that pointed at it.

Shape and images
- `source.segment.shape-kinds` — a segment's shape is a point, a line or an area; it may have
  more than one.
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
- `source.segment.open-kinds` — kinds come from a standard list a library can extend; a model's
  own label is kept beside the tidy kind.
- `source.segment.levels-optional` — any level may be absent and added later without
  disturbing others.
- `source.segment.physical-and-logical` — a segment can sit in the physical ladder and in a
  logical unit that crosses pages or documents.
- `source.segment.flow` — text that continues across a column, page or picture reads straight
  through.
- `source.segment.furniture` — page furniture is marked, and a reading can leave it out.
- `source.segment.table-cells` — a table's cells are segments with row, column, spans and
  header kind.
- `source.segment.marks-have-state` — a tick, cross or cancellation is a segment with a state.

Layers, orders, links
- `source.layer.named-authored` — segments live in named layers, each with an author; layers
  can be shown, hidden and compared.
- `source.layer.never-overwrites` — two layouts of one page are two layers, both kept.
- `source.layer.working` — one layer is the working layer the Reader, search and export use by
  default.
- `source.order.named-multiple` — a source can have several named reading orders, each with an
  author and certainty.
- `source.order.next-previous` — next and previous are asked of a named order, and work the
  same in the app, over MCP and on the command line.
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

Pointing and statements
- `source.point.by-id-or-span` — a thing points at a segment by id, or at a stretch of one of
  its readings.
- `source.point.text-is-derived` — a page's text is worked out from segments and a reading
  order; it is never the master.
- `source.statement.on-segment` — a claim or mention points at a segment id and survives
  re-segmentation and re-transcription.
- `source.statement.both-ways` — from a segment, what is said about it; from a statement, its
  ink.

Storage
- `source.store.record-per-segment` — the store can answer questions about single segments
  (the lines of a page; a word's history; all segments in a hand).
- `source.store.no-batch-rewrite` — an existing library's geometry is never converted by
  batch.

## Test matrix

To be filled at approval. The hard gate will be: the same segment gives the same id, shape,
image and picture from the engine, MCP, the command line and the app.

## Open questions

See `source-model.md`. The ones that belong here: how existing libraries' segments get ids;
whether a claim keeps a copy of its anchor as well as the segment id.
