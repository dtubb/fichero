# Source Model — The segment editor — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — an "Editing the layout of a page" section: selecting, drawing, reshaping,
> merging and splitting segments on the image; setting their order, direction and type;
> drawing links; working with the Apple Pencil.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Every behaviour below is tagged **[GAP]** with its issue; everything
> is design unless stated under "What exists today".

## Intent

Everything the model can hold can be seen and edited on the page. The editor lives in the
**Source view** (the pane the app has called the Preview; the maintainer has decided on the
new name, and the rename is not this spec's to carry through the app), on the image. **Shapes
are edited in the Source view; readings are typed in the Reader; the Inspector shows and does
not edit.** That is the split, and it is what keeps three surfaces three. It is **native SwiftUI** (ruled), so one editor
serves the Mac, the iPad and the iPhone, feels like a Mac app, and takes the Apple Pencil.

The three surfaces stay three. The **Source view** shows the image and edits segments. The
**Reader** shows readings. The **Inspector** shows the facts about the one selected segment.
Selecting a segment in any of them selects it in the others.

## What exists today (read on disk 2026-09-19; to be re-read before tagging)

- `Views/Preview/ImageViewer/OCRGeometryOverlay.swift` draws all boxes, display only.
- `Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift` sits above it and can
  select (click, shift-click, band), move a region, draw a new box and name it, and rate
  lines; delete is in `ZoomableImagePreviewMac+Regions.swift`. No reshape, no polygon, no merge
  or split, no order, no links.
- **Other things are drawn over a page too**: annotations, a PDF's own marks, and the
  image-editing overlay. `ui/reader-overlay-frame-identity.md` (`frame.*`) owns when any of
  them may draw.
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

**A text-first segment editor: direction given 2026-09-20, design below, not built.** The
earlier request for a Segments pane was answered with a clearer one: **edit a page's segments
by editing its text.** The comparison offered was the kind of audio editor where you cut the
recording by cutting its transcript. You work as in a word processor, the segments change as
you type, and a Source view beside it shows the page with all its boxes. Asked where it lives,
the answer was a new kind of pane, and in the same breath that it could well live in the
Reader. So this is a direction to design. Both ways are written out, with a recommendation;
the choice is the maintainer's.

### Editing a page by its text (design; recommended home: the Reader)

**Option 1, recommended: the Reader.** For a source whose segments have readings, the Reader's
text IS those readings, in the page's named reading order, and it is editable. Not a mode to
switch on: it is what the Reader shows for such a source (nodes, not modes). The Source view
beside it is linked to it, as panes already link. When no Source view is visible, the Reader
shows each line's picture above its text, so the ink is never out of sight; when one is, it
does not, and nothing has to be toggled.
- Keeps three surfaces three: the Source view is the page, the Reader is the words, the
  Inspector is the facts. Words are already typed in the Reader.
- Keeps one navigator. Stepping through a source's lines is moving the caret; reordering is
  cut and paste; a list of segments as rows stays a Library listing
  (`source.editor.library-lists-segments`); moving a segment to another pass stays a Source
  view verb. Nothing the Segments pane was asked for is left without a home.
- No new pane plumbing: no sixth entry in the kind switcher, the workspaces, the saved pane
  lists and the per-pane state, which is where duplicate code paths have come from before.

**Option 2: a sixth kind of pane.** A pane made for this one job: line pictures and text in a
fixed two-column layout, its own toolbar. What the modes-to-panes ruling would have to give
up: that the Library is always the navigator (this pane would be a second way to move through
a source's contents); that there is no browser kind of pane; and, in practice, that the
Source view, the Reader and the Inspector are the three surfaces, because words would now be
typed in two places with two sets of editing rules to keep the same. It buys a layout tuned
for transcription. Option 1 gets the same layout from the Reader's line pictures.

**Whichever home it has, the rules below hold.** Every edit is one of the segment, reading
and reading-order actions that already exist or are already specified; the text surface adds
no action and no second path. Where an edit touches both a shape and words (a split, a
join), it is ONE action whose existing parameters carry both, never two.

**Which text it shows.** One level: the lines of the page's working pass, in its named reading
order, grouped by region; a region that reads in another direction is its own block. Words
and characters are not units of their own here: they are positions inside a line's reading.
A page with 20,000 segments is a page with a few hundred lines and many words, and the text
still shows the lines. A page with no line level shows its lowest level that has readings, in
order. Only the blocks near what is on screen are laid out, and reads stay bounded by kind
and area. It is part of the editor's speed trial (slice 12).

**Typing.** Typing in a line corrects the reading of the segment under the caret. A correction
is a new reading, never an overwrite (`source.reading.corrections-are-new`): its maker is the
person, set by the engine; it records what it was corrected from; the machine's reading
stays. Which reading then counts follows the project's rule.

**Return inside a line splits that line's segment at the caret.** The reading divides at the
caret. Where the cut falls on the page, in order of preference:
1. Between the word before and the word after the caret, when the line has word segments or
   the reading carries positions for its characters: the cut crosses the baseline at the
   middle of the gap, at right angles to the baseline there.
2. Otherwise by proportion: the caret's share of the reading's length, measured along the
   baseline in the line's own direction, and the cut is marked **estimated**. The Source view
   shows an estimated cut differently, with a handle, and dragging it is an ordinary reshape.
3. A caret inside a word is allowed: the same two rules, within the word.
Return is never refused for want of word boxes; it is honest that the cut is a guess. The
first part keeps the line's id; the second is new; both go into the reading order where the
line was.

**Backspace at the start of a line joins it to the line before it in the reading order** (the
line before in the order, not the line above on the page). The earlier line is kept and keeps
its id; the shape becomes both shapes; the readings join, with the separator the script calls
for (a space, or nothing). Refused, with the reason, when the two lines are in different
regions or passes: move the line first.

**Deleting words deletes words, never ink.** Removing text is a correction of the reading:
the person is saying the word is not there. The earlier reading keeps it. If that word has a
segment of its own, the segment stays, is shown in the Source view as having no reading in
this reading, and is not deleted. Emptying a whole line leaves the line's segment in place,
marked as having no reading. Deleting a SEGMENT is a command of its own, said out loud
(Delete Segment), and is the undoable delete the Source view already has.

**Cut and paste of whole lines edits the named reading order**, and nothing else: the lines'
shapes and places on the page do not change. Pasted text that is not lines just cut from this
source is typing; line breaks in it become spaces, so a paste can never set off a run of
estimated splits.

**One selection, both ways.** The caret's line is the selected segment in the Source view, and
the word under it when there are word segments; selecting boxes in the Source view selects
their text. One shared selection, the one the rest of the app already uses, so a command
acts on what is visibly selected.

**A run of keystrokes is one action.** Typing in one line gathers into one edit, committed
when the caret leaves the line, when a structural key is pressed (Return, a joining
Backspace, cut, paste), when the pane loses focus, on Save, or after two seconds without a
keystroke. One committed edit is one new reading, one audit record and one undo step. While
an edit is still gathering, Undo is the text field's own; once committed, Undo goes through
the record like any other action. A split, a join, a cut or a paste is always its own action,
at once. By the ruling of 2026-09-20 the audit record's chained part holds ids, version
numbers and a keyed fingerprint; the typed words go in the content part.

**Someone else got there first.** A committed edit names the version it was made against. If
the line or its reading has changed since, it is refused, and **the typed words are not
thrown away**: the line shows both and asks, keep mine, take theirs, or compare. Out of reach
of the engine the text is read-only and says why (ruled 2026-09-20); an edit still gathering
when the connection drops is kept and committed, with its version check, when it returns.

**Every direction of writing.** Each block is laid out in its own direction from the cascade:
left to right, right to left, top to bottom. The caret moves in reading order; "the start of
a line" is its start in reading order; a cut runs along the baseline in the line's own
direction, from the right for right-to-left, downward for vertical. A page with two scripts
in two directions is two blocks. Where the platform cannot lay a direction out properly, the
block is shown horizontally with a plain label saying so; it is never silently reordered.

**Before readings are on segments there is nothing to show.** This surface is the readings of
segments in a reading order. It depends on slice 8 (readings on segments), slice 10 (named
reading orders, for cut and paste), the speed trial (12) and the one store, selection and
input seam of the editor (13). It is placed as **slice 13b, after 13**; typing, splitting and
joining could come before cut and paste if 10 is late.

### The earlier Segments pane record (kept for the history; superseded by the direction above)

On 2026-09-19 the
maintainer asked for a surface of its own for getting to a source's segments: to see them with
their pictures and readings, step through them, reorder them, move them between regions or
passes, and edit them, with a reading beside. An earlier ruling (`ui/modes-to-panes.md`) says
the Library is always the navigator and that **there is no browser kind of pane**; and the
Library's word-level view work (#4728) covers some of the same ground. Both cannot stand as
written. The reviewers' recommendation is that this be a **view of the Library** (rows can be
segments; a strip or grid is a Library view mode) beside the Source view, not a sixth kind of
pane. That is the maintainer's to rule; it is in the morning file. **Nothing is built for it
until then.** What holds whichever way it goes: selecting a segment selects it everywhere;
every change is the same audited action the Source view makes; it draws on the one store.

### One overlay, one editor

The display overlay and the region layer become **one** thing that draws segments and edits
them, under the same frame rule as the annotation, PDF-mark and image-editing overlays (it
joins that one gated family; it is not a fifth overlay with rules of its own). There is not a second renderer anywhere: the Reader's highlights, thumbnails with
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
- **Mark**: note, highlight, check and tag the selection.
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

### Slice 12: the speed trial, and how it is measured

The trial is a **hard gate**: the editor is not built on a drawing approach that failed it.
A gate needs a number that can be failed and a method that two people follow to the same
answer, and this section is the method. It is written because the numbers were ruled and the
method was not, and a threshold without a method is two people disagreeing politely. Three
measurement mistakes in one week of this programme — a cause named from a single run, a 13%
difference that was noise, and a figure quoted from a comment as though it had been measured —
are what this is guarding against, and every rule below has one of them behind it.

**What the numbers are.** Ruled already, and not reopened here: sixty frames a second during
zoom and pan, twenty thousand shapes, the oldest supported iPhone, and one edit through the
engine and system undo in under a tenth of a second. Sixty frames a second is a budget of
**16.7 ms per frame**, and the gate is on the **worst frame in the run, not the mean** —
a mean hides exactly the dropped frame a person feels. Hit-testing and dragging one point are
each inside one frame's budget, because they happen during a gesture.

**Peak memory has no ruled ceiling and this spec does not invent one.** The trial measures and
records it on a very large scan, and the ceiling is set from that first measurement and ruled
before the gate can fail anything on memory. What the trial can already fail on is **growth**:
memory must not scale with the page's shape count once only the visible shapes are drawn, and
a run whose peak grows between 5,000 and 20,000 shapes in proportion to the count has failed
regardless of the absolute figure.

**Which page.** One committed fixture, named in the test, and **declared for what it is**. Its
shape count, its nesting (regions, lines, words, characters) and the distribution of shape
sizes are taken from a real dense import measured for the purpose; the shapes themselves are
generated, so that the fixture can live in the repository and so that the trial is repeatable.
A generated fixture described as a real page would be the same lie as a number quoted from a
comment, so the fixture's own file records which real page its distribution came from.

**Which machine.** Two, and both are named in the result: the oldest supported iPhone (the
ruled target) and the Mac the work is done on. A number with no machine beside it cannot be
compared with next month's number, so the record carries the device model, the OS version and
the build configuration. **Release, not Debug** — measuring a Debug build and calling it the
product's speed is measuring the wrong thing.

**How many runs, and which number counts.** The first run is discarded as cold, then **five
runs**, and the recorded result is the median of the five together with the worst frame seen
in any of them. One run is not a measurement: a single figure cannot be told apart from
noise, and this programme has already mistaken noise for a 13% regression. If the five runs
disagree by more than a tenth of their median, the run is **inconclusive rather than passing**,
and the answer is more runs or a quieter machine, never the best of the five.

**What counts as the machine being idle.** No build running, no background embedding,
processing or conversion, no other lane's test suite, mains power, and the thermal state
recorded with the result. A run taken while the machine was thermally throttled is **void, not
failing** — the two are different facts and recording a throttled run as a failure would send
somebody to optimise code that was never slow. The trial refuses to record a result when it
cannot read the thermal state, because a gate that cannot read its input must fail rather than
pass quietly.

**What the number is measured against.** A committed baseline file, one line per measurement,
the way the spec pipeline and the swallowed-exception seam keep theirs. A run is compared with
the baseline and a regression beyond the noise band is a failure; a clear improvement updates
the baseline in the same commit as the change that earned it, never in a commit of its own.
The baseline records the machine, the OS, the fixture and the date, because a baseline that
does not say what it was measured on is a number somebody will argue with.

**What the trial may conclude.** That a drawing approach holds, or that it does not, or **that
the target itself is wrong** — the ruled sixty frames at twenty thousand shapes on the oldest
iPhone may turn out to be the wrong gate, and the trial is allowed to come back and say so
with its measurements. What it may not do is pass by lowering the target quietly.

### Accessibility

Drawn shapes are invisible to VoiceOver unless the editor describes them. Each visible
segment is an accessibility element with its kind, its reading and its place in the order,
and every command that can be done with the pointer can be done from the keyboard.

### Segment pictures

Wherever a segment appears (the Inspector, the transcription strip, a comparison, a training
export) its picture comes from one engine call that cuts the image to the segment's shape.
There is one way to get a segment's picture, used by the app, MCP, the command line and
export.

## Behaviors (every one is **[GAP]**: designed, not built; each cites its issue on milestone `source-model`, 322)

Reading before editing (the app's first step: it draws from the seam, and edits nothing new)
- `source.app.one-segment-store` — **[GAP]** (#4954) one store in the app holds a document's
  segments and passes, read from the engine's one segments call; it is the only caller of that
  call, and nothing else in the app keeps segments.
- `source.app.index-is-the-engines` — **[GAP]** (#4954) a box on screen is addressed by the engine's
  own index for it, never by its position in what happens to be drawn; leaving an undrawable
  box out of the drawing changes no other box's address.
- `source.app.edits-name-the-chosen-pass` — **[GAP]** (#4954) an edit made on the page is sent to the
  result the shown pass came from, and to no other; when what is shown changes (another pass
  wins; an artifact is chosen in the Inspector), the next edit follows it; with nothing shown,
  no edit is sent.
- `source.app.curated-pass-stays-on-top` — **[GAP]** (#4954) a pass that a person made, or that
  carries any segment a person made, is shown ahead of every machine pass, as today; a newer
  machine run never covers a person's region.
- `source.app.overlays-draw-from-the-seam` — **[GAP]** (#4954) the boxes drawn over an image and
  over a PDF page both come from that store through one shared function, with the same
  drawing code as today and no new overlay; a page looks the same before and after the switch.
- `source.app.segment-events-patch-in-place` — **[GAP]** (#4954) when the engine says which
  segments changed, the store replaces those items and no others; when it says only that a
  document's results changed, the store re-reads that one document.

The editor
- `source.editor.segment-focus` — **[GAP]** (#4941) the Source view has a segment focus in which the editing
  tools appear; it can sit beside a Reader, an Inspector, the Library or another Source view.
- `source.textedit.reader-shows-segments` — **[PARTIAL]** (#5001) for a source whose segments have readings, the text
  surface shows the lines of the working pass in the named reading order, one block for each
  region and direction, and is editable; with no Source view in sight each line shows its
  picture. (Home recommended: the Reader; a sixth pane kind is the other option; the
  maintainer's to choose.) **Read from the code, not the tag, 2026-09-27:** the derivation is
  already whole — `document_text()` reads the working pass and follows the named order, spans
  and all (`fichero-server/tests/unit/api/test_textedit_engine_primitives.py::TestReaderShowsSegmentsUsesTheWorkingPassAndNamedOrder::test_the_derived_text_follows_the_working_pass_and_names_its_segments`).
  **Not built:** the packaging this line names — one block per region, each with its own
  direction. `DerivedTextSpan` carries only `segment_id`/`representation_id`/`start`/`end` today,
  pinned by `::test_spans_carry_no_region_grouping_or_direction_today` so the day it grows region
  and direction is a deliberate change to that test, not a silent one. No Source-view surface
  exists yet either way.
- `source.textedit.typing-is-a-new-reading` — **[PARTIAL]** (#5001) typing corrects the reading of the segment under the
  caret as a new reading whose maker is the person, set by the engine; the earlier reading
  stays. **The engine primitive is whole**, tested against the request the app would actually send
  (a real actor, no run_id, no via_mcp) rather than a synthetic id:
  `representation.create` sets the maker from `ActionContext` via `provenance_kind_from_ctx` —
  the same function the machine-claims-stored-as-human defect (2026-09-18) fixed — never from
  client input (`RepresentationCreateParams` forbids a `created_by`/`provenance_kind` field
  outright), and no update action exists for a reading, so the earlier one cannot be touched.
  **Stays PARTIAL**, not OK: the SURFACE — a text edit that calls this action on
  keystroke-commit — does not exist, and #5001 (the umbrella this whole family is tracked under)
  is still open. Pinned:
  `test_textedit_engine_primitives.py::TestTypingIsANewReadingSetsTheMakerFromContext` (all four
  cases: a real actor recorded as human, a workflow run recorded as workflow even under the same
  actor name, a client-supplied maker refused outright, the earlier reading unchanged by a
  correction). **What is not built is the SURFACE** — a text edit that calls this action on
  keystroke-commit does not exist; that is #5001's UI half, tracked separately.
- `source.textedit.return-splits-the-line` — **[PARTIAL]** (#5001) Return inside a line splits that segment at the caret
  in one action: the reading divides at the caret; the cut falls between words when their
  places are known, otherwise by proportion along the baseline and marked estimated; the
  first part keeps the id. **Read from the code, 2026-09-27:** `segment.split` already takes an
  independent geometric `anchor` and text `reading_span` per part — the primitive a Return
  handler would call — pinned by
  `test_textedit_engine_primitives.py::TestReturnSplitsTheLineSegmentSplitPrimitive::test_a_split_takes_an_independent_anchor_and_reading_span_per_part`.
  **Not built, confirmed absent by search rather than assumed** (`::test_no_caret_to_geometry_mapping_exists_in_the_tree`):
  the mapping from a caret's character offset to a geometric cut point, in any direction —
  word-aligned when word children exist, proportional-along-the-baseline and marked estimated
  otherwise. This is a design decision (what the estimate looks like, how it behaves for RTL and
  boustrophedon text) and is not implemented anywhere in the tree.
- `source.textedit.backspace-joins-in-reading-order` — **[GAP]** (#5001) Backspace at a line's start joins it to the line
  before it in the reading order, in one action, keeping the earlier line's id; refused with
  the reason across regions or passes.
- `source.textedit.deleting-words-keeps-ink` — **[GAP]** (#5001) removing text is a new reading without those words;
  no segment is deleted by it; a word segment left without a reading, or an emptied line, is
  shown as such; deleting a segment is a separate, named command.
- `source.textedit.lines-move-in-the-order` — **[GAP]** (#5001) cutting and pasting whole lines changes the named
  reading order and nothing on the page; other pasted text is typing, its line breaks
  turned to spaces.
- `source.textedit.one-selection` — **[GAP]** (#5001) the caret's line (and word) is the selection in the Source
  view, and a selection there selects the text; one shared selection.
- `source.textedit.a-run-of-keys-is-one-action` — **[GAP]** (#5001) typing in one line commits as one reading, one
  audit record and one undo step, on leaving the line, a structural key, loss of focus, Save,
  or two seconds' pause; structural edits are their own action at once.
- `source.textedit.stale-keeps-your-words` — **[GAP]** (#5001) an edit against a version that has moved on is refused
  and the typed words are kept and offered: keep mine, take theirs, compare; out of reach of
  the engine the text is read-only.
- `source.textedit.every-direction` — **[GAP]** (#5001) each block is laid out and edited in its own direction;
  line starts, joins and cuts follow reading order and the baseline; a direction the platform
  cannot lay out is labelled, never reordered.
- `source.textedit.no-second-path` — **[GAP]** (#5001) every change made from the text is one of the existing
  segment, reading and reading-order actions; the text surface defines none of its own.
- `source.segments-pane.exists` — **[GAP]** (#4942) **Superseded in direction 2026-09-20 by `source.textedit.*`;
  still not to be built** (a Segments pane, or a view of
  the Library): a surface shows a source's segments with their pictures and readings, and lets
  them be stepped through, reordered and moved. Not to be built or tested until ruled.
- `source.segments-pane.same-actions` — **[GAP]** (#4942) **BLOCKED with the one above**: whatever that surface
  is, every change it makes is the same audited action the Source view's editor makes, and
  selection is shared.
- `source.editor.library-lists-segments` — **[GAP]** (#4941) the Library can list segments as rows, so
  project-wide questions about segments are ordinary Library searches.
- `source.editor.one-overlay` — **[GAP]** (#4941) one component draws and edits segments in the Source view; no
  second overlay renderer exists in the app.
- `source.editor.shapes-in-source-view` — **[GAP]** (#4941) a segment's shape is edited in the Source view; its
  readings are typed in the Reader; the Inspector shows and does not edit.
- `source.editor.selection-shared` — **[GAP]** (#4941) selecting a segment in the Source view, Reader or Inspector
  selects it in the others.
- `source.editor.edits-are-actions` — **[GAP]** (#4941) every edit is one audited, reversible engine action; the
  editor updates only the changed segments.
- `source.editor.redo-works` — **[GAP]** (#4957) after undoing a segment edit, Redo (⇧⌘Z) does it again;
  redo is worked out afresh as the undo of the undo, so it succeeds although the segment's
  version has moved on; it is refused only if something else has changed the segment since.
  Doing, undoing, redoing and undoing again, any number of times, ends where the first undo
  ended, and nothing is left over under a new id. A segment or pass that comes back on redo
  comes back under its own id. (Reviewed twice, 2026-09-20. In the worktree, not yet committed:
  the version number is refreshed on redo, and a redone step is undone through its own record
  of what it made, which closes the leftover parts, copies and stranded rows. Still owed under
  #4957: merge, split and carry, and their inverses, take no version number, so a redo is not
  refused when someone else changed a member in between, and undoing a split deletes its parts
  outright even if someone else has worked on one; the parts of a split, the copies of a carry
  and a proposed match get new ids on each redo.) The rule itself, that a step is reversed
  through its own inverse when it has one, belongs to the shared undo route, not to segments;
  the safety set (branch `spec/undo-trash`, not merged) proposes it for every action, and this
  set agrees.
  (Today a redo of a segment edit is refused as stale: the shared undo route replays the
  original request. The editor cannot ship without this.)
- `source.editor.system-undo` — **[GAP]** (#4941) ⌘Z and ⇧⌘Z undo and redo editor actions through the action
  pass.
- `source.editor.agent-parity` — **[GAP]** (#4941) every edit the editor can make can be made over MCP and the
  command line through the same actions.
- `source.editor.two-switches` — **[GAP]** (#4941) the editor has two view switches only (show the order; show
  the links); everything else shown follows from zoom and selection.
- `source.editor.draw-shapes` — **[GAP]** (#4941) box, polygon, point, line and baseline can be drawn.
- `source.editor.reshape` — **[GAP]** (#4941) points can be dragged, added and removed; shapes moved and nudged.
- `source.editor.propose-shape` — **[GAP]** (#4941) a click asks the engine to propose a shape, which can then be
  adjusted.
- `source.editor.cut` — **[GAP]** (#4941) a scissors stroke splits one or many lines at once.
- `source.editor.join-group` — **[GAP]** (#4941) selected segments can be merged; lines grouped into a region
  and ungrouped.
- `source.editor.set-kind` — **[GAP]** (#4941) the selection's kind (and furniture or text) can be set.
- `source.editor.set-direction` — **[GAP]** (#4941) the selection's direction can be set, and a line reversed.
- `source.editor.set-language-script` — **[GAP]** (#4941) the selection's language and script can be set.
- `source.editor.set-hand-campaign` — **[GAP]** (#4941) the selection's hand and campaign can be set.
- `source.editor.reorder` — **[GAP]** (#4941) a named reading order can be edited by dragging in a list or
  clicking segments in turn.
- `source.editor.draw-link` — **[GAP]** (#4941) dragging from one segment to another makes a typed link.
- `source.editor.match-across-passes` — **[GAP]** (#4941) a segment in one pass can be matched to one in
  another.
- `source.editor.transcribe-by-line` — **[GAP]** (#4941) with a line selected, the Reader shows its picture above
  its reading; Return selects the next line in the order and the Source view follows. (The
  Reader's planned in-place transcription editing, → #4375, is this same editor: one place to
  type a reading.)
- `source.editor.marks` — **[GAP]** (#4941) the selection can be noted, highlighted, checked and tagged.
- `source.editor.control-points` — **[GAP]** (#4941) control points can be placed and given coordinates.
- `source.editor.keyboard-complete` — **[GAP]** (#4941) every command has a menu item and can be done from the
  keyboard.
- `source.editor.pencil-draws` — **[GAP]** (#4941) on the iPad the Pencil draws shapes, baselines and cuts.
- `source.editor.pencil-traces-strokes` — **[GAP]** (#4941) a Pencil trace is kept as stroke segments with
  position, time, pressure and tilt.
- `source.editor.smooth-when-dense` — **[GAP]** (#4940) zoom, pan, hit-test and drag hold sixty frames a second
  with twenty thousand shapes on the oldest supported iPhone (the ruled target; the trial
  settles how to draw, and may come back and say the target is wrong).
- `source.editor.level-of-detail` — **[GAP]** (#4940) finer levels appear as you zoom in.

The trial that settles it, and what makes its numbers checkable (slice 12; all **[GAP]**, #4940)
- `source.perf.worst-frame-not-mean` — **[GAP]** (#4940) the frame gate is on the worst frame in a
  run against a 16.7 ms budget, never the mean, because a mean hides the dropped frame a person
  feels.
- `source.perf.five-runs-median` — **[GAP]** (#4940) a measurement is the median of five runs after a
  discarded cold one, reported with the worst frame; runs that disagree by more than a tenth of
  their median are inconclusive, and the best of the five is never the answer.
- `source.perf.names-its-machine` — **[GAP]** (#4940) every recorded number carries the device model,
  the OS version, the build configuration and the fixture it was measured on; a Release build,
  never Debug.
- `source.perf.declared-fixture` — **[GAP]** (#4940) the trial's page is one committed fixture whose
  shape count, nesting and size distribution come from a named real page, and whose own file
  says it is generated.
- `source.perf.void-when-throttled` — **[GAP]** (#4940) a run taken on a thermally throttled or busy
  machine is void rather than failing, and a run that cannot read the thermal state records
  nothing at all rather than recording a pass.
- `source.perf.baseline-or-fail` — **[GAP]** (#4940) results are compared with a committed baseline
  that states its machine, OS, fixture and date; a regression beyond the noise band fails, and
  an improvement updates the baseline in the commit that earned it.
- `source.perf.memory-growth` — **[GAP]** (#4940) peak memory is recorded rather than gated on an
  invented ceiling, and the trial fails when peak memory scales with a page's shape count
  instead of with what is visible.
- `source.perf.may-say-the-target-is-wrong` — **[GAP]** (#4940) the trial may conclude that the ruled
  target is the wrong gate and say so with its measurements; it may not pass by lowering the
  target.
- `source.editor.voiceover` — **[GAP]** (#4941) each visible segment is an accessibility element with kind,
  reading and order.
- `source.editor.one-input-seam` — **[GAP]** (#4941) pointer, touch and Pencil feed one input path; the same
  editor runs on Mac, iPad and iPhone.

## Test matrix

To be filled at approval. The click-around leg matters most here, on the Mac, the iPad and
the iPhone.

Engine-side rows filled 2026-09-27 (`source.textedit.*`'s first three; the click-around leg is
still to be filled at approval):

| Behaviour | Engine primitive | Test |
|---|---|---|
| `reader-shows-segments` | `document_text()` | `test_textedit_engine_primitives.py::TestReaderShowsSegmentsUsesTheWorkingPassAndNamedOrder` (2 tests: follows the working pass and order; spans carry no region/direction today) |
| `typing-is-a-new-reading` | `representation.create` + `provenance_kind_from_ctx` | `test_textedit_engine_primitives.py::TestTypingIsANewReadingSetsTheMakerFromContext` (4 tests: human, workflow, refused client-supplied maker, earlier reading unchanged) |
| `return-splits-the-line` | `segment.split` | `test_textedit_engine_primitives.py::TestReturnSplitsTheLineSegmentSplitPrimitive` (2 tests: independent anchor + reading_span per part; no caret-to-geometry mapping exists) |

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
