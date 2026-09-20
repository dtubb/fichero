# Source Model — The segment editor — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — an "Editing the layout of a page" section: selecting, drawing, reshaping,
> merging and splitting segments on the image; setting their order, direction and type;
> drawing links; working with the Apple Pencil.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Behaviour ids below have **no tags yet**; everything
> is design unless stated under "What exists today".

## Intent

Everything the model can hold can be seen and edited on the page. The editor lives in the
**Source view** (the pane the app has called the Preview; the maintainer has decided on the
new name, and the rename is not this spec's to carry through the app), on the image, and
nowhere else. It is **native SwiftUI** (ruled), so one editor
serves the Mac, the iPad and the iPhone, feels like a Mac app, and takes the Apple Pencil.

The three surfaces stay three. The **Source view** shows the image and edits segments. The
**Reader** shows readings. The **Inspector** shows the facts about the one selected segment.
Selecting a segment in any of them selects it in the others.

## What exists today (read on disk 2026-09-19; to be re-read before tagging)

- `Views/Preview/ImageViewer/OCRGeometryOverlay.swift` draws all boxes, display only.
- `Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift` sits above it and can
  select (click, shift-click, band), move a region, draw a new box and name it, delete, and
  rate lines. No reshape, no polygon, no merge or split, no order, no links.
- Boxes are addressed by their position in a list, because they have no ids.
- `RegionInteractionLayer.swift` is compiled for the Mac only (`#if os(macOS)`) and takes its
  clicks from the Mac's pointer. There is no segment editing on the iPad or iPhone today. One
  editor for all three means this gate goes and the editor has **one** input seam that
  pointer, touch and Pencil all feed. Otherwise a second editor gets built.
- Crops are rectangles only (`media/region_crops.py`).

## The design

### The Source view, with a segment focus, beside anything

The Source view shows a source. With a **segment focus** it becomes the segment editor: the
tools below appear, and the image is the working surface. Because it is a pane like any
other, it can sit **beside** a Reader (type the reading of the selected line), beside an
Inspector (the facts of the selected segment), beside the Library, or beside a second Source
view on another pass, another image of the same page, or another source altogether.

**A Segments pane (ruled in direction 2026-09-19; its design is open).** The Library gets you
to a page. Getting to the segments themselves wants a surface of its own: to see a source's
segments with their pictures and readings, step through them, **reorder** them, **move** them
between regions or passes, and edit them, with a reading view beside. There may be more than
one such view (a list, a strip, a grid). What is fixed already: it is a pane like any other,
so it sits beside the Source view, the Reader and the Inspector; selecting a segment there
selects it everywhere; every change is the same audited action the Source view's editor
makes; and it draws on the one store. Questions about the whole project ("every line in hand
B", "every segment with no chosen reading") remain searches in the Library, which can list
segments as rows like any other node. The pane's own design is an open question in the
foundation.

### One overlay, one editor

The display overlay and the region layer become **one** thing that draws segments and edits
them. There is not a second renderer anywhere: the Reader's highlights, thumbnails with
boxes, and exports to SVG and PDF all come from the same segment records and the same drawing
rules.

### Every edit is an action

The editor owns no data. Each edit is one audited, reversible action sent to the engine,
which answers with the changed segments; the editor updates only those. Undo and redo are the
system's (⌘Z), and undo what the *action layer* did. An agent over MCP and the command line
can make every edit the editor can, through the same actions.

### What you can do

- **See**: what is shown follows from what you are doing, not from a panel of switches. The
  working pass is shown. Finer levels appear as you zoom in. Selecting a segment shows its
  links and its place in the order. There are two switches only: *show the reading order*
  and *show the links*. Comparing passes is done by opening a second pass beside the first,
  the same way two sources are compared.
- **Select**: click; shift-click; band; "select the same kind"; step through a reading order
  with the arrow keys; go up to the parent or down to the children.
- **Draw**: a box, a polygon, a point, a line, a baseline. On the iPad, with the Pencil.
- **Reshape**: drag a corner or a side; add a point (double-click an edge or a baseline);
  remove a point; move the whole shape; nudge with the arrow keys.
- **Propose**: click on something and the engine proposes its shape, which you then adjust.
- **Cut and join**: a scissors stroke across one or many lines splits them (across columns in
  one go); join merges the selected segments; group lines into a region; ungroup.
- **Set**: kind, pass, campaign, direction (and "reverse this line"), language, script,
  hand, furniture or text, table row and column.
- **Order**: see the order as numbers on the page and as a list; drag in the list, or click
  segments in turn on the page, to reorder; choose which named order you are editing.
- **Link**: drag from one segment to another and pick the link's type; see and delete links.
- **Match**: say that a segment in a new pass is the same as one in an old pass.
- **Read while you edit**: readings are typed in the **Reader**, not the Source view. With a line
  selected, the Reader shows that line's picture above its reading, and Return moves the
  selection to the next line in the order; the Source view follows. Line-by-line transcription is
  keyboard-only if you want it to be, and the three surfaces stay three.
- **Mark**: note, highlight, star and tag the selection.
- **Georeference**: drop control points and give them coordinates.

Every command is in the menu bar with a shortcut, in the context menu of a segment, and
reachable by keyboard alone.

### Apple Pencil

The Pencil draws polygons, baselines and scissors strokes, and taps to select. Separately, a
researcher can **trace** a sign or a stroke with the Pencil: the trace is kept with its
points, timing, pressure and tilt, as the **stroke** level of the ladder. That is how the
ductus of a letter (the order and direction of its strokes) can be recorded.

### It must stay smooth

A dense page can have twenty thousand word and character shapes on a very large image. The
editor must zoom and pan smoothly, find the shape under the pointer at once, and drag a point
without lag, on the oldest supported iPhone as well as a Mac. The survey's advice: tile the
image for deep zoom; keep shapes in a spatial index for hit-testing; draw only what is
visible at the current zoom (characters appear when you are close enough to see them).
SwiftUI's simple canvas has no per-shape hit-testing or accessibility of its own, so both are
built. Before the editor is built, **a small trial settles the drawing approach** by
measuring: frames during zoom and pan at 5,000 and 20,000 shapes; time to hit-test and to
drag one point; peak memory on a very large scan; and one edit going through the engine and
system undo in under a tenth of a second.

### Accessibility

Drawn shapes are invisible to VoiceOver unless the editor describes them. Each visible
segment is an accessibility element with its kind, its reading and its place in the order,
and every command that can be done with the pointer can be done from the keyboard.

### Segment pictures

Wherever a segment appears (the Inspector, the transcription strip, a comparison, a training
export) its picture comes from one engine call that cuts the image to the segment's shape.
There is one way to get a segment's picture, used by the app, MCP, the command line and
export.

## Behaviors (ids proposed; untagged until approval)

- `source.editor.segment-focus` — the Source view has a segment focus in which the editing
  tools appear; it can sit beside a Reader, an Inspector, the Library or another Source view.
- `source.segments-pane.exists` — a Segments pane shows a source's segments with their pictures
  and readings, and lets them be stepped through, reordered, moved and edited; it sits beside
  any other pane. (Design open.)
- `source.segments-pane.same-actions` — every change made in the Segments pane is the same
  audited action the Source view's editor makes; selection is shared.
- `source.editor.library-lists-segments` — the Library can list segments as rows, so
  project-wide questions about segments are ordinary Library searches.
- `source.editor.one-overlay` — one component draws and edits segments in the Source view; no
  second overlay renderer exists in the app.
- `source.editor.source-view-only` — segments are edited in the Source view, not in the Reader or the
  Inspector.
- `source.editor.selection-shared` — selecting a segment in the Source view, Reader or Inspector
  selects it in the others.
- `source.editor.edits-are-actions` — every edit is one audited, reversible engine action; the
  editor updates only the changed segments.
- `source.editor.system-undo` — ⌘Z and ⇧⌘Z undo and redo editor actions through the action
  pass.
- `source.editor.agent-parity` — every edit the editor can make can be made over MCP and the
  command line through the same actions.
- `source.editor.two-switches` — the editor has two view switches only (show the order; show
  the links); everything else shown follows from zoom and selection.
- `source.editor.draw-shapes` — box, polygon, point, line and baseline can be drawn.
- `source.editor.reshape` — points can be dragged, added and removed; shapes moved and nudged.
- `source.editor.propose-shape` — a click asks the engine to propose a shape, which can then be
  adjusted.
- `source.editor.cut` — a scissors stroke splits one or many lines at once.
- `source.editor.join-group` — selected segments can be merged; lines grouped into a region
  and ungrouped.
- `source.editor.set-kind` — the selection's kind (and furniture or text) can be set.
- `source.editor.set-direction` — the selection's direction can be set, and a line reversed.
- `source.editor.set-language-script` — the selection's language and script can be set.
- `source.editor.set-hand-campaign` — the selection's hand and campaign can be set.
- `source.editor.reorder` — a named reading order can be edited by dragging in a list or
  clicking segments in turn.
- `source.editor.draw-link` — dragging from one segment to another makes a typed link.
- `source.editor.match-across-passes` — a segment in one pass can be matched to one in
  another.
- `source.editor.transcribe-by-line` — with a line selected, the Reader shows its picture above
  its reading; Return selects the next line in the order and the Source view follows.
- `source.editor.marks` — the selection can be noted, highlighted, starred and tagged.
- `source.editor.control-points` — control points can be placed and given coordinates.
- `source.editor.keyboard-complete` — every command has a menu item and can be done from the
  keyboard.
- `source.editor.pencil-draws` — on the iPad the Pencil draws shapes, baselines and cuts.
- `source.editor.pencil-traces-strokes` — a Pencil trace is kept as stroke segments with
  position, time, pressure and tilt.
- `source.editor.smooth-when-dense` — zoom, pan, hit-test and drag stay smooth at twenty
  thousand shapes on the oldest supported device (numbers set by the trial).
- `source.editor.level-of-detail` — finer levels appear as you zoom in.
- `source.editor.voiceover` — each visible segment is an accessibility element with kind,
  reading and order.
- `source.editor.one-input-seam` — pointer, touch and Pencil feed one input path; the same
  editor runs on Mac, iPad and iPhone.

## Test matrix

To be filled at approval. The click-around leg matters most here, on the Mac, the iPad and
the iPhone.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
