# Segment Editor Tools — the Source pane and segment lines — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — the "Editing the layout of a page" section tracked by `../source/segment-editor.md`
> must also tell a researcher how to merge, split, reassign and redraw lines, how to cut words,
> and what the Pencil does on the iPad.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — awaiting approval before tests/code.**
> Direction given 2026-11-13 (paraphrased throughout). This file is the TOOLS slice of
> `../source/segment-editor.md`, which stays the umbrella: the Source view and its panes, editing a
> page by its text (`source.textedit.*`), the Segments pane, colours and hierarchy, the speed
> trial, and the rulings of 2026-09-27 and 2026-10-04 all live there and are not repeated here.
> This file says what each correction feels like under the hand, what the engine has to do for
> it, and in what order it is built. Ids here are `segment-editor.*`; where an umbrella behaviour
> already covers part of one, it is named and built on, never restated.
> Tags: [OK] built · [PARTIAL] exists in part / not wired · [GAP] not built · [BROKEN] seen fail.

## Intent

The segmenter (Kraken's blla, or a YOLO region detector) hands a page back as regions, text
lines with an outline and a baseline, and a reading order. People look at hundreds of those
pages before any transcription is trusted, and the corrections they make are few and repeated:
join two lines the segmenter cut in two, cut one it fused, move a note out of the main block,
redraw a baseline the model missed, fix the order, say what a region is. The editor is tuned
to those corrections. It is not a drawing program: there is one selection, a handful of tools,
a modifier for the next most common thing, and no dialog on the way to any of them. It is the
same editor on the Mac with a mouse and on the iPad with a finger and the Pencil.

Everything below holds to the rules the umbrella already fixed: shapes are edited in the Source
view and readings are typed in the Reader; the editor owns no data; **every edit is one audited,
undoable action sent to the engine**, which answers with the changed segments; the app is a
client of the generated OpenAPI client; the logic (geometry, cuts, order) is the engine's, so
MCP, the command line and a workflow can make every edit a hand can.

## What exists today (read on disk 2026-11-13)

Engine (`fichero-server/src/fichero_server/api/routes/document/segments.py`,
`reading_orders.py`, `segment_readings.py`):
- Audited, undoable actions: `segment.create`, `create_many`, `update`, `update_many`, `delete`,
  `undelete`, `merge` / `unmerge`, `split` / `unsplit`, `carry` / `uncarry`, `match_propose` /
  `match_accept` / `match_reject`, `pass_create` / `pass_delete` / `pass_restore`,
  `restore_version`; `reading_order.create` / `delete` / `place` / `remove` / `restore_place` /
  `renumber`; `representation.create` for a reading. Every write takes the version last read
  and refuses a changed row (`source.segment.versioned-alone`).
- The `segment.update` action takes an anchor (rect, polygon, extra shapes), a `baseline` on its own,
  `kind`, `parent_segment_id`, `is_furniture`, `mark_state`, language, script, direction.
- The `segment.merge` action keeps one id and leaves forwarding notes; `segment.split` takes explicit
  `parts` (anchor, baseline, `reading_span`) **or** `at_offset`, which cuts the box in
  proportion along the line's direction and marks both parts `cut: estimated`, because, in the
  code's own words, nothing records where a character sits on the image (`_parts_cut_at`,
  `estimated_cut`). Merge and split keep the parts in every reading order (`source.segment.delete-is-undoable`).
- A segment's picture cut to its outline and straightened on its baseline
  (`media/segment_pictures.py`, `_straightened`).
- Geometry is stored as fractions of the page's upright photograph whatever image a step read;
  `media/current_image.py` and `media/frame_map.py` carry shapes between the photograph, a
  person's edit chain and a run's rendition, and refuse an image whose frame cannot be worked out.
- Reading order from geometry: `media/layout_order.py` (`reading_order`, columns, right-to-left).
- Kraken: `llm/kraken_runtime.py` segments with blla and reads with a recognition model
  (`_read_given_raw`, `read_given_lines`); per line it keeps the text, the line confidence and
  the per-character confidences. **It does not keep Kraken's per-character cuts** (section 7.2 below).
- A reading row already has `char_confidences` and `char_positions` (each character's place
  along the line, 0 to 1), served by `GET /api/segments/{id}/readings`. **No producer writes
  `char_positions`**; only tests do.
- Apple Vision's word boxes are kept packed per line (`source.words.packed-per-line`).
- ALTO export writes a `String` per word segment with its box; PAGE XML carries `custom`
  attributes both ways (`formats/alto.py`, `formats/pagexml.py`); both have a loss report.
- The Kraken training set is PAGE XML beside each photograph (`training/kraken_set.py`), lines
  with a baseline and some text, flagged lines left out.

App (`fichero/fichero/Views/Preview/ImageViewer/Regions/`, `fichero/fichero/Models/`):
- `RegionInteractionLayer` (Mac only, `#if os(macOS)`): click, shift-click and band selection;
  move one box; the one Shape tool draws a box, a polygon or a baseline; `+Reshape` drags a
  point, adds one on a side, removes one with ⌥-click; arrow keys nudge the pressed point by a
  pixel (ten with ⇧); ⌫ deletes in the mode; Join is ⌘J with a plan (`SegmentEditCommand.mergePlan`)
  and no caller yet; `SegmentEditingMode` decides what Edit Segments allows; `SegmentEdit.move/set/delete/join`
  build the requests; `SegmentEditRunner` sends them and registers undo by audit id.
- `PreviewPointerFeed` is the one input seam on the Mac; `ZoomableImagePreviewIOS` zooms and
  pans and has no segment editing at all (`source.editor.one-input-seam` is a GAP).
- `SegmentShapes` draws a segment as its shapes and reshapes them; `RegionColours` gives each
  region a hue and its lines a gradient along the order; `SegmentSelection` is the one selection.
- PDF pages: select and reshape only (`SegmentVerbs.pdfPage`).

## Prior art (what is adopted, what is done differently)

- **eScriptorium** has the closest editor: select, merge, cut with a line, link lines to a
  region, edit baselines, and *recalculate masks* (line polygons) from baselines by calling
  Kraken's polygonal-environment routine over the page image. Its merge joins baselines end to
  end. Fichero adopts those four verbs and the recompute-from-baseline call, and makes every
  one of them an audited engine action rather than a canvas edit saved later.
- **Transkribus** adds reading-order editing by numbered overlay and a text-region type list;
  adopted. Its many tools and dialogs are not: Fichero keeps one Select tool with modifiers.
- **Kraken's own serialisers** (ALTO and PAGE) write words and glyphs from the recogniser's
  per-character cuts; section 7 derives words the same way and says what the cuts cannot do.
- **Apple's Pencil conventions** (PencilKit, Notes, Freeform): the Pencil draws while a finger
  scrolls, a two-finger tap undoes, palm rejection is the system's, lasso selection is a drawn
  loop. Adopted as the iPad grammar; nothing is invented there.
- **Procreate / Pixelmator** brush selection (paint a mask, hold a modifier to subtract):
  adopted for the brush selection and the paint-to-polygon tool, with the size on a slider.
- Illustrator's pen tool, nested groups and compound paths are deliberately not the model: a
  line is a polygon and a baseline, and the common fix must never need a vertex.

## User stories

1. A researcher opens a page Kraken segmented. Two short lines of one sentence were found as
   two; she drags across both and presses ⌘J. One line, its reading joined, one step to undo.
2. Two lines of a cramped hand came back as one tall line. He holds K, draws a stroke across
   the fused line between the two baselines, lets go. Two lines, each with its own baseline,
   the reading cut at the nearest word gap.
3. A marginal note was folded into the main text block. She drags the note's line out of the
   block onto the margin region; it is now that region's line and sits in its order.
4. The segmenter missed a faint line. He holds the Pencil along the ink; the stroke becomes a
   baseline, the engine draws the outline around it, and the new line is in the order between
   its neighbours.
5. A baseline wanders off the ink at one end. She drags the baseline's last point onto the ink
   and presses ⌘⇧R; the outline is redrawn from the corrected baseline.
6. The page reads in the wrong order: a second column is interleaved with the first. He turns
   the order overlay on, clicks the lines in the order they should read, and is done.
7. Twenty pages of a register have the same three regions in the same places. She corrects
   one, chooses Apply Regions to Similar Pages, and reviews the proposals on the rest.
8. A page is read; she wants word boxes for a name index. Cut Words derives them from the
   recogniser's character positions; where the hand is cursive the cuts show as uncertain,
   and she drags two of them.
9. Before exporting to PAGE XML, the validator lists a line outside every region and a
   self-crossing polygon; she fixes both from the list.
10. On the iPad in the archive, with the Pencil, she merges, cuts and redraws through a box of
    pages without a keyboard; a two-finger tap undoes.

## The interaction model

### Tools, modes and modifiers

One tool is always armed: **Select**. The others are **modes** a person steps into and out of,
and three of them are also **spring-loaded**: hold the key for a stroke, let go, back to Select.

| Tool | Key | Spring-loaded | What a drag does |
|---|---|---|---|
| Select | V, Esc | — | band (marquee); ⌥-drag lasso; drag on a selected shape moves it; drag a handle reshapes |
| Brush select | B | hold B | paints a selection mask; ⌥ subtracts; `[` `]` size |
| Knife | K | hold K | one stroke cuts every line it crosses |
| Marker | M | hold M | freehand outline (closed) or baseline (open), simplified on release |
| Paintbrush | P | — | paints a polygon along the ink; width on a slider, pressure optional |
| Order | O | — | click segments in sequence to set the reading order |
| Shape (box / polygon / baseline by points) | S | — | the umbrella's one Shape tool, unchanged (`source.editor.draw-shapes`) |

Space held pans in any tool. The Pencil's double-tap switches between the current tool and
Select (the system's gesture; a setting may map it to the last tool instead).

Rules:
- Escape, in order: cancels a stroke in progress; leaves the current mode for Select; clears
  the selection. One thing per press, never two (`WindowState.abandonDrawing` already does
  the first).
- A spring-loaded tool lasts one stroke. Letting go mid-stroke finishes the stroke.
- A tool never opens a dialog. Its one or two settings (brush size, marker smoothing,
  paintbrush width, pressure on or off) are a small popover on the tool's button, remembered
  per window.
- Nothing writes a segment outside Edit Segments (`source.editor.segment-focus`). Outside it,
  Select selects and the tools are not offered.

### Cursor states (Mac) and the hover

| Over | Cursor | Hover feedback |
|---|---|---|
| empty page | arrow (crosshair in a drawing tool) | none |
| a segment | arrow | the smallest segment under the pointer gets the hover wash and its label (`source.editor.hover-picks-the-line`) |
| a selected segment's body | open hand; closed while moving | — |
| a handle (point) | crosshair | the handle fills |
| a side midpoint | crosshair with a plus | a hollow handle appears |
| a handle with ⌥ | crosshair with a minus | — |
| a cut mark (word / character) | horizontal resize | the mark thickens and its two words' text shows |
| a line while dragging another line | copy cursor over a region that will take it | the target region's outline lights |
| Knife, Marker, Brush | the tool's own cursor; the Brush shows its size as a circle | — |

Touch has no cursor: the hover feedback appears on the first finger-down and the handle
targets are at least 44 pt.

### Selection feedback

- Selected segments draw the Mac selection look the umbrella fixed (`source.editor.selection-like-preview`):
  a filled wash in the region's hue and a 2 px outline; handles only when exactly one is selected,
  or for every selected segment when fewer than six are.
- A selection of mixed kinds shows a count in the head ("3 lines, 1 region") and the verbs that
  apply to all of them; the rest are disabled with the reason in their help text.
- The selection is the one selection the Reader, Inspector and Segments pane share
  (`source.editor.selection-shared`); the brush and lasso write to it the same way a click does.

## The tools, one by one

### Structure: merge, split, reassign

- `segment-editor.merge-lines` — **[OK]** (→ #4941; app + engine; builds on `source.editor.join-is-easy`, #6182) two or
  more selected lines and ⌘J become one line: the first picked keeps its id; the outlines are
  joined into one polygon (their union, hulled across the gap when they do not touch); the
  baselines are joined end to end in the page's reading order; the readings join with the
  script's separator; the result sits where the first line sat in every order; the others
  leave forwarding notes. **Across different regions (owner 2026-11-13):** the other lines are
  moved into the first line's region and merged in the same action, one undo; the merged line
  is that region's line in its order. (This overrides the refusal `source.editor.join-is-easy`
  wrote; `segment.merge` gains the move.) *Built (2026-11-13):* `segment.merge` with `join_geometry`
  and `move_into_region` (off by default, so the Reader's join is unchanged): the union on a raster,
  hulled across a gap (`media/line_join.py`), the baselines end to end in reading order, the readings
  joined with the script's separator, the move across regions, one undo (`unmerge` with
  `keep_restore`) and redo; the Preview's Join sends both flags (`SegmentEdit.join(_:asLines:)`).
  The key is ⌥⌘J, the owner's ruling of 2026-11-08 in menus-and-commands.md, not the ⌘J written
  here (open question). Lines measured on another image are refused, not carried. *Tests:* `tests/unit/api/test_segment_merge_lines.py` (union,
  hull, baseline order, across regions is one action and one undo); `SegmentJoinTests.swift`.
- `segment-editor.merge-regions` — **[PARTIAL]** (→ #4941; engine) two or more selected regions and ⌘J become one region
  whose outline is the union; their lines become the kept region's lines, interleaved into its
  order by page position (`layout_order`), with the result shown before it lands as a
  highlighted order overlay for two seconds.
  *Built (2026-11-13):* `segment.merge` with `join_geometry` moves what the absorbed members held
  (a region's lines, a line's words) to the kept one, placed in every order that held them by
  page position (`place_in_page_order`), and `unmerge` puts parents and entries back; the
  Preview's Join on selected regions sends it. *Built (2026-11-14):* after a Join of regions lands, the
  page shows its order numbers for two seconds (`WindowState.flashOrderOverlay`), then hides them unless
  Show Order Numbers is on. *Not built:* showing the order before the merge lands (the merge lands at
  once, `segment-editor.every-edit-lands-at-once`), and lighting only the kept region's lines.
  *Tests:* `test_segment_merge_lines.py::TestMergeRegions`;
  `fichero/Tests/Unit/general/Views/Source/SegmentJoinTests.swift::mergedRegionsFlashTheOrder`.
- `segment-editor.split-knife` — **[PARTIAL]** (→ #4941; app + engine; refines `source.editor.cut`) a Knife stroke, a
  polyline drawn across one or many lines, splits every line it crosses at the crossing: the
  engine (`segment.split` gains `cut_path`, points in the frame of the image drawn on) cuts each
  outline along the stroke, cuts each baseline where the stroke crosses it, and gives each part
  its own baseline; a stroke that crosses a line twice makes three parts; a line the stroke only
  grazes (no baseline crossing) is left alone and said so in the answer. The reading is cut at
  the character whose position is nearest the crossing when positions are known
  (`segment-editor.char-positions-kept`), else in proportion and marked `cut: estimated` as
  today. One stroke over many lines is one action, one undo. *Built (2026-11-13):* `segment.split`
  with `cut_path` and `expected_versions` (the lines the stroke may cross), `media/line_cut.py`
  (crossings, baseline pieces, the outline cut along the stroke on a raster), the reading cut at the
  nearest `char_positions` else in proportion, `left_alone` naming grazed lines and lines with no
  baseline, the undo `segment.unsplit_many`; the app holds the Knife while K is down in Edit
  Segments and sends the stroke once on release (`SegmentEdit.knife`, `RegionInteractionLayer+Knife`).
  The Knife button (scissors) in the segment editor's tool row stays on until another tool is
  chosen; when it leaves lines alone the page says how many for five seconds
  (`SegmentEdit.knifeNotice`). *Built (2026-11-14):* a tap of K (pressed and let go with no stroke between)
  chooses the Knife until another tool is chosen; Esc puts it down before it clears the selection
  (`WindowState.letGoOfKnifeKey`). *Not built:* the Pencil.
  *Tests:* `test_segment_split_knife.py`
  (two crossings, graze, rtl, vertical); `KnifeStrokeTests.swift` (the stroke is sent once,
  in the drawn frame, with versions; `aTapOfKChoosesTheKnife`).
- `segment-editor.split-at-a-point` — **[OK]** (→ #4941; app) with one line selected, ⌘⇧K splits it under the
  pointer (a vertical cut through that point at right angles to the baseline), for the common
  case where a stroke is more than is needed; the same engine call with a two-point `cut_path`.
  *Built (2026-11-13):* Edit › Segments ▸ Split Line at Point (⌘⇧K), at the point last pressed on the
  page (the Preview tracks presses, not hover), `SegmentEdit.splitAtPoint`. *Tests:*
  `fichero/Tests/Unit/general/Views/Source/KnifeStrokeTests.swift::splitAtAPoint`.
- `segment-editor.reassign-by-drag` — **[PARTIAL]** (→ #4941; app + engine) dragging a line (or a selection of lines)
  onto another region, in Select, makes them that region's lines: one `segment.reparent`, which
  also moves each line's entry, in every order that holds it, among the region's lines by page
  position (the entry keeps its id, so whatever is nested under it stays). The target region's outline lights while the drag is over it; dropping on no region
  makes the lines regionless (`source.editor.colour.regionless-lines-are-one-region`); dropping
  back where it started is nothing, not an action. ⌘-drag moves the shape instead (a move is
  the default when the drag stays inside the line's own region, a reassignment when it leaves
  it; the head says which while dragging). One drop, one undo: the undo puts back the parents AND
  the order entries where they were (`segment.restore_versions` with `order_entries`), and a redo
  moves them again. *Built (2026-11-14):* the engine half (`segment.reparent` places by page position
  in every order, `_reposition_entries`; the undo restores the entries) and the drag in Edit Segments:
  a drag of selected lines let go on another region, or on none, is one `segment.reparent`
  (`SegmentMover.drop`, the region holding the point, the smaller on a tie), the target region's
  outline lit while the drag is over it; inside their own region, or with ⌘, the box moves as before.
  *Not built:* the head's word while dragging, a polygon moving with its box (`segment-editor.group-drag`).
  *Tests:* `fichero-server/tests/unit/api/test_segment_reassign_by_drag.py`;
  `fichero/Tests/Unit/general/Views/Source/ReassignDragTests.swift`.

### Selecting and moving

- `segment-editor.select-marquee-lasso` — **[PARTIAL]** (→ #4941; app) a drag on empty page is a band; ⌥-drag is a
  lasso (a drawn loop); both select every segment whose outline is mostly (over half its area)
  inside, at the level being edited (lines by default; regions when the band starts on nothing
  and ⌘ is held). *Built:* the band on the Mac (`finishBand`, regions and words). *Built (2026-11-14):*
  the lasso (⌥-drag from empty page in Select, drawn dashed), the over-half rule and the level rule
  for the band and the lasso (`SegmentSelectionGestures.inside`, `level`: lines when the page shows
  any, regions with ⌘, else what is shown). *Not built:* touch. *Tests:*
  `fichero/Tests/Unit/general/Views/Source/SegmentSelectionGesturesTests.swift`.
- `segment-editor.select-shift-toggles` — **[PARTIAL]** (→ #4941; app) ⇧-click and ⇧-band add to the selection;
  ⇧-click on a selected segment removes it; ⌘A selects every segment of the level shown; ⌘⇧A
  selects the same kind as the selection ("select the same kind" from the umbrella). *Built:*
  ⇧-click and band on the Mac, ⌘A (Edit › Segments ▸ Select All Segments: every box shown).
  *Built (2026-11-14):* ⇧-click on a selected segment in Edit Segments removes it (it no longer starts
  a move, `SegmentEditingMode.pressStartsMove`); Edit › Segments ▸ Select Same Kind (⌘⇧A,
  `SegmentSelectionGestures.sameKind`). *Tests:*
  `fichero/Tests/Unit/general/Views/Source/SegmentSelectionGesturesTests.swift`.
- `segment-editor.select-brush` — **[GAP]** (→ #4941; app) the Brush paints a mask on the page; every segment the
  mask touches is selected when the stroke ends; ⌥ while painting subtracts; `[` and `]` change
  the size, shown as a circle under the pointer; on the iPad the size follows the slider and,
  optionally, pressure. The mask is drawn locally and sent nowhere: selection is not an action.
- `segment-editor.group-drag` — **[PARTIAL]** (→ #4941; app + engine) dragging one of several selected segments
  moves all of them by the same offset, as one `segment.update_many`, one undo. *Built:* a single
  box moves (`finishMove`, `SegmentEdit.move`). *Not built:* the group, polygons and baselines
  moving with the box (only a rect moves today).
- `segment-editor.nudge` — **[PARTIAL]** (→ #4941; app) with a selection and no pressed point, the arrow keys move
  the whole selection one image pixel, ⇧ ten, ⌥⇧ a hundred; with a pressed point, the point
  alone (built). A held key gathers into one action, committed when the key is released or
  after half a second of stillness (`undo.typing.commit-is-one-step` applied to keys).
- `segment-editor.vertices` — **[PARTIAL]** (→ #4941; app + engine) a click on a side adds a point; ⌥-click a
  point removes it (built); ⌫ with a pressed point removes it; **Simplify** (⌘⌥S, and a slider
  in the Shape popover) asks the engine for a simpler outline, `segment.simplify` with a
  tolerance in image pixels (Douglas-Peucker on the outline and the baseline), shown live as
  the slider moves and committed once on release. A dense outline from an import or a paint
  stroke comes down to a handful of points without the person touching one.
  *Built (2026-11-13):* `segment.simplify` (Douglas-Peucker in the page image's pixels, outline closed
  and baseline open, never below three and two points, re-checked for a self-crossing; a shape
  already that simple is left alone; one undo through `segment.restore_versions`) and
  Edit › Segments ▸ Simplify Outline at 2 px. *Built (2026-11-14):* the slider (0.5 to 20 px) in
  Simplify's popover in the segment tools row, beside the shape tools (there is no Shape popover yet);
  while it is held the page draws, dashed, what the engine would make of the selection
  (`GET /api/segments/document/{doc_id}/simplify-preview`, the same computation the action writes,
  writing nothing), and letting go sends one `segment.simplify` at that tolerance; ⌫ with a pressed point
  removes that point (before the selection; a shape at its fewest points keeps it and says so,
  `SegmentEditingMode.deleteKey`). *Not built:* the chord: ⌥⌘S is Star's in the markup row
  (`PreviewMarkupToolsRow`).
  *Tests:* `fichero-server/tests/unit/api/test_segment_simplify.py` (the preview);
  `fichero/Tests/Unit/general/Views/Source/SegmentSimplifyTests.swift` (`theSlider`, `thePreviewPaths`);
  `fichero/Tests/Unit/general/Views/Preview/SegmentEditingModeTests.swift` (⌫ on a pressed point).

### Drawing

- `segment-editor.marker` — **[PARTIAL]** (→ #4941; app + engine) the Marker draws freehand: a stroke that ends near
  where it began (within 12 pt) is a closed outline and makes a region or a line of **the kind
  last used** (owner 2026-11-13; the same rule for the Paintbrush); any other stroke is a
  baseline and makes a line of that kind with its outline regenerated from the
  baseline (`segment-editor.regenerate-polygon-from-baseline`). The engine simplifies the
  stroke on the way in (`segment.create` with `stroke` and `smoothing`, 0 to 1, default the
  popover's) so the record never holds a point per pixel. The new segment lands in the region
  holding it and in the order by position, as the Shape tool's lines do (`source.editor.draw-shapes`).
  *Built (2026-11-14):* `segment.create` takes `smoothing` (Douglas-Peucker in the page image's
  pixels, 0.5 px at 0 to 5 px at 1, `MARKER_TOLERANCE_PX`) and `outline_from_baseline` (the line's
  outline drawn from the ink as Redraw does; on no ink the line keeps its baseline alone and the
  answer says `outline: none`). In Edit Segments, M held is the Marker for one stroke and a tap of M
  (or the tool row's Marker) chooses it until another tool or Esc; a stroke ending within 12 points of
  its start is an outline of the kind last drawn, any other a line on it as a baseline, in the
  region holding most of it (`MarkerStroke`). *Not built:* the popover's smoothing (0.5 is sent),
  the Pencil. *Tests:* `fichero-server/tests/unit/api/test_segment_create_from_stroke.py`;
  `fichero/Tests/Unit/general/Views/Source/MarkerToolTests.swift`.
- `segment-editor.paintbrush` — **[GAP]** (→ #4941; app + engine) the Paintbrush paints along a line of ink with a
  finger, the pointer or the Pencil; the painted area is the outline, its centreline is the
  baseline. The app sends the stroke as points with a width each (the slider's; pressure is
  **off by default** and an option in the tool's popover turns it on, owner 2026-11-13); the
  engine turns it into the polygon and the centreline (`segment.create`
  with `brush_stroke`). Strokes that overlap a line painted in the same session merge into that
  line (its outline grows, the baseline is recomputed) rather than making a second line; a
  stroke over an existing line that was not painted this session is a new line, never a silent
  merge. Width is remembered per window.

### Lines and baselines

- `segment-editor.baseline-independent` — **[OK]** (app + engine) a baseline is reshaped on its own and
  sent on its own (`segment.update` with `baseline` only); the outline does not change until
  asked. Pinned by `fichero/Tests/Unit/general/Models/ImportedPageDrawsItsBoxesTests.swift::testReshapingABaselineSendsItAloneAndTheRefusalsHold`.
- `segment-editor.regenerate-polygon-from-baseline` — **[PARTIAL]** (→ #4941; engine + app) with one or more lines
  selected, **Redraw Outline from Baseline** (⌘⇧R) asks the engine for a new outline for each
  from its baseline and the page image: `segment.regenerate_outline`, which runs Kraken's
  polygonal-environment routine (`kraken.lib.segmentation.calculate_polygonal_environment`)
  on the current image in the line's frame, with the neighbouring baselines as bounds so
  outlines do not overlap, and an optional fixed height in image pixels for a page with no ink
  to measure; the old outline is the version before, so one undo restores it. A selection of
  lines is one action. It is also what the Marker and the knife use for a part with a baseline
  and no good outline, and it is offered on a line whose outline is missing or invalid
  (`segment-editor.edge.no-baseline`). *Built (2026-11-13):* `segment.regenerate_outline` and
  `POST /api/segments/regenerate-outline` (`media/outline_from_baseline.py`, with an ink check
  because Kraken answers a blank page with an outline to the page edge, and the fixed-height band
  as the fallback); Edit › Segments ▸ Redraw Outline from Baseline and the Preview's context menu,
  which say why for a line with no baseline. *Not built:* the ⌘⇧R chord (it is Run Workflow on
  Selection's today), the fixed height in the app, the background helper for a whole page.
  *Tests:* `test_regenerate_outline.py` (a tilted line, two
  close lines do not overlap, a line with no ink gets the fixed height, undo restores);
  `RedrawOutlineTests.swift`.

### Semantics: reading order and kinds

- `segment-editor.order-by-clicking` — **[PARTIAL]** (→ #4941; app + engine; refines `source.editor.reorder`) in Order,
  the page shows every segment of the level with its number; clicking segments in turn gives
  them positions 1, 2, 3 … in the chosen named order; the first click starts at 1, ⇧-click
  continues from the selection's number, and clicking a numbered segment again removes its
  number. The engine takes the clicks as one `reading_order.sequence` on release of the mode
  (Return, Escape or picking another tool), one undo for the whole sequence (confirmed, owner
  2026-11-13: never per click). Segments not clicked keep their relative order after the clicked ones.
  (`reading_order.renumber`, named here first, must stay order-preserving and not undoable: the
  undo of a move depends on it, so the clicks are a new action.) *Built (2026-11-14):* the engine
  half: `reading_order.sequence` (the clicked segments, all at one level of the order, in click
  order, first or right after `after_segment_id`; the level numbered 1, 2, 3 again; refused with
  segments from two levels or not in the order), its undo `reading_order.restore_positions` and the
  redo; both refresh the page's cached text. The Order tool in Edit Segments (O, or the tool row's
  Order): the page shows its order numbers, each click numbers a segment in an accent badge (a second
  click takes it away, ⇧ on the first continues after the selected segment), and leaving the tool
  (O, Return, Esc, another tool) sends one `reading_order.sequence` in the pass's `as-written` order.
  *Not built:* ordering a named order the Segments pane chose (the Preview knows only `as-written`).
  *Tests:* `fichero-server/tests/unit/api/test_reading_order_renumber_by_clicks.py`;
  `fichero/Tests/Unit/general/Views/Source/OrderToolTests.swift`.
- `segment-editor.order-overlay` — **[PARTIAL]** (→ #4941; app) the order is visible as the gradient the umbrella
  fixed (`source.editor.colour.reading-order-gradient`) and, with the overlay on, as numbers at
  each segment's start and a thin arrowed line from each to the next; the overlay is a layer
  (`segment-editor.layers`). *Built:* the gradient in the model. *Not built:* numbers, arrows.
- `segment-editor.type-by-key` — **[PARTIAL]** (→ #4941; app; refines `source.editor.set-kind`) the selection's kind
  is set from a **Kind menu** (under Segment in the menu bar, in the context menu and the
  Inspector) that lists the project's kinds in its order (main text, heading, marginalia, stamp,
  signature, table, picture, damage, blank by default; a project can reorder the list); the
  first nine carry menu shortcuts with a modifier, ⌃⌥1 … ⌃⌥9. **Never bare number keys**
  (owner 2026-11-13). The menu shows each kind's shortcut as menus do. *Built:*
  `SegmentEditCommand.plan` for `kind`. *Not built:* the menu, its shortcuts, the project list.

### Words and characters

See section 7.2 below for what exists. The design:

- `segment-editor.char-positions-kept` — **[PARTIAL]** (→ #5154; engine) when Kraken reads a line, the recogniser's
  per-character cuts are kept on the reading as `char_positions` (the fraction of the baseline's
  length at which each character starts, in the frame the line was read in) beside
  `char_confidences`, so every later cut can be measured instead of guessed. A reading from a
  reader that gives no positions (a vision model, a cloud reader) has none and says so (absent,
  never faked: `segment.rep.honest-absence`).
  *Built (2026-11-13):* `kraken_runtime.char_positions` reads each record's raw cuts (start and end
  along the dewarped line) over the baseline's length; `ReadLine` and the full-page read carry them;
  the read-given-lines path in `vision_base` keeps them (and `char_confidences`) on the box and
  `write_readings` passes them to `representation.create`, which keeps them on a machine's reading
  when there is one per character. `segment.split(at_offset)` cuts at the position and marks
  `cut: measured` (not for right-to-left lines yet: their positions run along the baseline as
  drawn). *Not built:* the full-page read's writer, the app's `Reading` model. *Tests:*
  `test_kraken_char_positions.py`.
- `segment-editor.cut-words-from-positions` — **[PARTIAL]** (→ #5212; engine + app) **Cut Words** (⌘⇧W) on selected lines, or
  a page, derives word segments from the counting reading: each space in the text is a gap
  between two characters; the cut is the point on the baseline midway between the end of the
  character before and the start of the one after; the line's outline is cut across the
  baseline at right angles there; each piece is a `word` child of the line with its
  `reading_span`, made by `segment.cut_words` as one action per line (one undo per line, one
  batch for a page). **It runs by itself after every Kraken read** (owner 2026-11-13): the
  words it makes are a machine's, marked `cut_source: ctc` with their confidence, and ⌘⇧W runs
  it again by hand. **Positions win over Apple Vision's words** (owner 2026-11-13): where a line
  has both, the word layer shows the words cut from the positions and Vision's boxes stay in
  their packed row for the missed-words check; a hand-drawn word is kept and matched by overlap,
  never duplicated. Only lines with a reading and positions are cut this way; the rest fall to
  the ink-gap fallback and say so. *Built (2026-11-13):* `segment.cut_words` (one action for the
  lines given, undo `segment.uncut_words`, redo through its own invert; a machine's earlier words
  are replaced, a person's kept and not duplicated; the page's text is unchanged); it runs after
  every Kraken read-given-lines read on the lines with positions (`cut_words_after_read`, never
  failing the read); Edit › Segments ▸ Cut Words (⇧⌘W), which says how many lines it could not
  cut. *Not built:* the full-page read's hook, a word's own reading (the word carries its
  `reading_span` into the line's reading), right-to-left lines from positions (they take the
  ink-gap path), Vision's packed row beside them. *Tests:* `test_segment_cut_words.py`;
  `CutWordsTests` in `SegmentSimplifyTests.swift`.
- `segment-editor.cut-characters` — **[GAP]** (→ #5212; engine + app) **Cut Characters** does the same inside a word
  from its character positions, giving `character` children; offered only at a zoom where a
  character is at least 24 pt tall on screen.
- `segment-editor.cut-fallback-ink-gaps` — **[OK]** (→ #5212; engine) a line with a reading and no positions is
  cut by the ink-gap projection profile along its baseline: the dark pixels of the current
  image inside the outline are summed across the baseline, gaps wider than a fraction of the
  line's height are candidate cuts, and the N widest gaps are taken for N spaces in the reading.
  It is much less reliable and is marked so (`cut_source: ink-gap`, confidence from the gap's
  width against the median, capped low). **Kept** (owner 2026-11-13): the fallback stays, with
  its source and its low confidence on every cut it makes. A line with no reading cannot be cut
  into words at all and says why. *Built (2026-11-13):* `line_cut.cuts_from_ink_gaps` (the profile
  along the chord of the baseline, gaps a seventh of the line's height, confidence at most 0.4);
  a line with too few gaps is left alone and named. *Tests:* `fichero-server/tests/unit/api/test_segment_cut_words.py::TestFallback`.
- `segment-editor.cut-records-source-and-confidence` — **[PARTIAL]** (→ #5212; engine) every word and character made by a cut
  carries `cut_source` (`ctc`, `ink-gap`, `person`), `cut_confidence` (0 to 1; the recogniser's
  character confidence at the cut for `ctc`, the gap measure for `ink-gap`, 1 for `person`) and
  the reading it was cut from, in the segment's metadata, so a later pass, the Check lens and an
  export can tell a measured cut from a guessed one and a person's from a machine's.
  *Built (2026-11-13):* `cut_source` (`ctc`, `ink-gap`), `cut_confidence`, `cut_from_representation_id`
  and `reading_span` on every word `segment.cut_words` makes. *Not built:* `person` (the cut marks).
- `segment-editor.cut-marks-editable` — **[GAP]** (→ #5212; app + engine) in the word layer each cut is a short mark
  across the baseline: drag it to move the cut (one `segment.update` of the two words' anchors
  and spans, `cut_source: person`); click on the baseline between two words to add a cut
  (`segment.split` of the word under the click, `at_offset` chosen from the positions); click
  a mark and press ⌫ to remove it (`segment.merge` of the two words). The same marks appear for
  characters inside a word at a deeper zoom. A mark whose confidence is under 0.5 is drawn
  dashed; a person's is solid.
- `segment-editor.word-view` — **[GAP]** (→ #5212; app; ties to `../source/line-editor.md`) with the word layer on, words
  are shown as alternating tints of the line's hue (two steps) or, by a setting, as outlines
  only; hovering a word shows its text; selecting a word selects its stretch of the reading in
  the Reader and the line editor, and selecting text there selects the word on the page (one
  selection, `source.textedit.one-selection`). The word and character layers are two toggles
  with opacity (`segment-editor.layers`), off by default, and characters only draw at the zoom
  where they can be seen (`source.editor.level-of-detail`).

### Workflow helpers

- `segment-editor.rerun-on-area` — **[GAP]** (→ #6185; app + engine) **Find Lines Here** (⌘⇧F) with a region or a
  band selected runs the segmenter on that area of the current image, as the existing
  `find-lines` job scoped to the selection (`source.tool.scope-is-a-segment-selection`); the
  result is a new pass named for the run (`source.segment.rerun-is-new-pass`) and its lines
  are shown as proposals over the area with Accept All / Replace the lines in this area /
  Discard, each an action: accept creates the lines in the working pass, replace is a delete of
  the area's old lines and the creates in one batch (`undo.batches.whole`). Nothing is replaced
  without the person pressing it.
- `segment-editor.low-confidence-lens` — **[GAP]** (→ #6185; app + engine) a Check lens over the page (`../source/checking.md`)
  lists the page's lines by confidence, lowest first: the segmenter's line confidence where it
  gave one, the reading's confidence, a cut's confidence, and the validator's findings; a row
  selects the line on the page; the head's **Next Doubtful** (⌘⌥N) steps through them.
- `segment-editor.layers` — **[PARTIAL]** (→ #5114; app; applies Q2 of the umbrella's rulings and `layers.toggle.one-menu-per-surface`)
  the What-to-show menu's segment entries are layers: regions, lines, baselines, words,
  characters, reading order, each on or off with an opacity, remembered per pane
  (`layers.toggle.remembered-per-pane`); the defaults follow the workspace; a layer whose data
  the page lacks says so instead of drawing nothing (`layers.toggle.empty-layer-says-so`).
  *Built:* the image and overlay switches. *Not built:* per-layer entries, opacity, words,
  characters, order.
- `segment-editor.batch-apply-template` — **[GAP]** (→ #5382; app + engine) **Apply Regions to Similar Pages** takes the
  selected page's regions as a template and proposes them on the pages the person names (the
  folder or a selection); the match is **by the page layout box only** (owner 2026-11-13: no
  ink-layout similarity measure); each target page gets a proposed pass (`proposed: true`, as the missed-lines
  check does), reviewed in the Check lens, accepted per page or all at once. Regions are placed
  by the page box where one exists (`image.enhance.page-crop`) so a shift in the scan does not
  shift the template. A line correction has no template: lines are found, not copied.
- `segment-editor.validate-before-export` — **[PARTIAL]** (→ #4943; engine + app) `GET /api/documents/{id}/segments/validate`
  lists, per page: lines outside every region; outlines that cross themselves; outlines that
  overlap another of the same level by more than a tenth; segments with no shape; lines with
  no baseline; a reading order with a gap, a repeat or a segment missing from it; words whose
  spans do not tile their line's reading. The export sheet runs it first and shows the count
  with Fix (opens the lens) or Export Anyway; the loss report names what was exported invalid.
  MCP and the CLI get the same list. *Built (2026-11-13):* the checks (`media/segment_checks.py`,
  per pass, plus empty regions) behind `GET /api/segments/document/{doc_id}/validate` (beside the
  other per-page segment reads rather than under `/api/documents`). *Built (2026-11-14):* Export Page
  As and the Inspector's per-pass Export check the page first (`PageExportRunner.checkedBeforeExport`):
  problems show their count, each kind in words, with Export Anyway or Cancel, and the report then
  begins "Exported with N segment problems"; a check that fails does not block the export and the
  report says the page was not checked. *Not built:* Fix (there is no lens to open yet; Cancel
  stands in), MCP and CLI. *Tests:* `test_segments_validate.py`;
  `fichero/Tests/Unit/general/PageExportTextTests.swift::problemsBeforeExport`.
- `segment-editor.every-edit-lands-at-once` — **[PARTIAL]** (→ #4957; app + engine) there is no autosave because
  there is nothing unsaved: a gesture is local until it ends, and its end is one action the
  engine has written before the app draws the result. The app holds no dirty state; closing
  the window loses at most the stroke in progress. ⌘Z and ⇧⌘Z are the window's undo stack
  over audit ids (`undo.window`, `source.editor.system-undo`); a refused undo says why in words
  (`undo.refusal.in-words`). *Built:* for move, delete, draw, reshape. *Not built:* for every
  tool here; the coalescing rules above.
- `segment-editor.shortcuts-for-everything` — **[GAP]** (→ #4941; app; refines `source.editor.keyboard-complete`) every
  verb in this file is in the menu bar under Segment with its shortcut, in the context menu of a
  segment, and on the pane head; the map below is the one list, and
  `MenuShortcutUniquenessTests` reads it.

### iPad and touch

- `segment-editor.touch-pinch-pan` — **[PARTIAL]** (→ #4941; app) pinch zooms about the pinch's centre, two fingers
  pan, in every tool; one finger in Select taps to select and drags a selected shape; a long
  press opens the context menu. *Built:* zoom and pan in `ZoomableImagePreviewIOS`. *Not built:*
  the editor on iOS at all (`source.editor.one-input-seam`).
- `segment-editor.pencil-draws-finger-pans` — **[GAP]** (→ #4941; app) with a Pencil paired, the Pencil draws, cuts,
  paints and drags handles in every tool, and a finger only selects, pans and zooms; a setting
  lets a finger draw for people without a Pencil. The Pencil's hover (where supported) shows the
  cursor states above.
- `segment-editor.palm-rejection` — **[GAP]** (→ #4941; app) palm rejection is the system's (`UIPencilInteraction`,
  PencilKit's touch policy), never Fichero's own heuristics; a finger touch that begins while
  the Pencil is down is ignored by the editor.
- `segment-editor.two-finger-tap-undo` — **[GAP]** (→ #4941; app) a two-finger tap undoes, three fingers redo (the
  system gestures, `UIEditingInteraction`), through the same stack as ⌘Z on a keyboard.
- `segment-editor.one-input-seam` — **[GAP]** (→ #4941; app; is `source.editor.one-input-seam`) pointer, touch and
  Pencil events become the same `PreviewPointerEvent` with a `source` (pointer, finger, pencil),
  pressure and tilt where given; `RegionInteractionLayer` loses its `#if os(macOS)`; the
  decisions in `SegmentEditingMode` and the tools above read the event, never the platform.

### Integration

- `segment-editor.export-carries-every-edit` — **[PARTIAL]** (→ #4943; engine; ties to `../source/formats-and-training.md`)
  every edit this editor makes reaches the formats without loss where the format can carry it,
  and the loss report names it where it cannot (`source.format.loss-report`): word and character
  segments go to ALTO `String` and `Glyph` (with `WC` / `GC` from the cut's confidence) and PAGE
  `Word` / `Glyph`; the cut's source and confidence go to PAGE `custom`
  (`cut {source:ctc; confidence:0.82;}`) and are reported lost in ALTO and hOCR; the reading order
  to PAGE `<ReadingOrder>` and ALTO's line sequence; kinds to PAGE region types and ALTO
  `TYPE`, with the raw label beside; provenance (model or person, who, when) to PAGE's
  `<MetadataItem>` per segment and the package sidecar; a merged or split segment's forwarding
  notes to the sidecar only. *Built:* ALTO and PAGE lines, words, order, loss report; and
  (2026-11-13) the cut's source and confidence: PAGE `custom` (`cut {source:ctc; confidence:0.82;}`),
  ALTO `WC` with the source named in the loss report (`page_export.CUT_FACTS`). *Not built:*
  glyphs, hOCR's cut, per-segment provenance. *Tests:* `test_cuts_in_page_and_alto.py`;
  `test_segment_cut_words.py::TestExport`.
- `segment-editor.coordinates-one-frame` — **[PARTIAL]** (→ #5382; engine + app; ties to `../source/image-enhancement.md`)
  the page a person draws on may be an enhanced or deskewed image; what is **stored** is always
  fractions of the upright photograph (`prep.image.one-upright-frame`, `current_image.py`). The
  app sends every drawn point in the frame of the image it drew on, naming that image
  (`SourceAnchor.rendition_id`); the engine carries it to the photograph with `frame_map`
  before writing and carries stored shapes to the shown image before the app draws them, so a
  line drawn on a deskewed rendition sits on the ink when the person switches back to the
  original. An image whose transform is not known cannot be drawn on: the tools are disabled and
  the head says why (`source.segment.no-guessing-across-images`). **Export offers both frames
  now** (owner 2026-11-13): the export sheet asks for the original photograph or the prepared
  (deskewed, enhanced) image; the prepared choice re-maps every shape to that rendition and
  writes the image beside the file; either way the loss report names the frame written and,
  for the prepared one, the transform, since ALTO and PAGE have no place for it. *Built:*
  storage in the upright frame; the carry for Kraken, YOLO and crops. *Not built:* the app
  naming the shown rendition on a create or update; the export choice and its loss-report line.
- `segment-editor.corrections-train` — **[PARTIAL]** (→ #4947; engine; ties to `../compute/training-and-evaluation.md`)
  a corrected page's working pass, with its lines, baselines, outlines, regions and order, is
  what the Kraken training set writes (`training/kraken_set.py`); word and character cuts made
  or confirmed by a person are included as PAGE `Word` / `Glyph` so a recogniser trained on
  them learns the alignment; a corrected region set is a YOLO label
  (`prep.yolo.fine-tune-from-corrected-regions`); a machine's cut no person touched is left
  out by default (`source.train.human-checked-by-default`). *Built:* the line set. *Not built:*
  words, glyphs and regions in it.
- `segment-editor.provenance-on-every-segment` — **[PARTIAL]** (→ #4923; engine) every segment says who made it
  (`created_by`, `provenance_kind`: model and run, or person, set by the engine from the
  action's context, never from the client) and every change is a version with who and when
  (`source.segment.versioned-alone`); a merged line names the lines it came from; a cut names
  its source. The Inspector shows it; the Segments list can sort by it. *Built:* maker and
  versions. *Not built:* the merged-from list on the row, the cut's source.

### Visual design

- Region hue and the order gradient are the umbrella's (`source.editor.colour.*`); nothing here
  adds a colour of its own. Kinds are told apart by a small label at the region's top-left in
  its hue, not by colour, so a page with nine kinds does not need nine hues.
- Lines are drawn thin by default and the selected one thick (`source.editor.thin-by-default`);
  baselines are drawn heavier than outlines and a shade darker; words are the alternating tints;
  characters are outlines only; cut marks are short strokes across the baseline, 8 pt on the Mac
  and 14 pt on touch.
- Confidence is shown on demand, never always: the low-confidence lens, a dashed cut mark, and a
  dotted outline for a proposed segment (`proposed: true`). An estimated cut from the Reader's
  Return keeps its handle (`source.textedit.return-splits-the-line`).
- Legibility over varied scans: every stroke is drawn with a 1 px contrasting halo (white under
  a dark hue, black under a light one) so it reads over dark paper, pale ink and binarised
  pages alike; the halo and the wash are the only two tricks, and both scale with zoom so a
  line does not become a band when zoomed in. Opacity per layer is the person's.
- Dark mode uses the same hues at the same lightness; the wash is lighter.

## Keyboard and gesture map

Mac keys (every one is also a Segment menu item; ⌘ chords stay unique across the app):

| Action | Key |
|---|---|
| Select tool / leave mode / clear | V / Esc |
| Brush select, Knife, Marker, Paintbrush, Order, Shape | B, K, M, P, O, S (hold B/K/M for one stroke) |
| Brush size down / up | [ / ] |
| Pan while held | Space |
| Add to / remove from selection | ⇧-click, ⇧-drag |
| Lasso | ⌥-drag on empty page |
| Select all (level) / same kind | ⌘A / ⌘⇧A |
| Merge (Join) | ⌘J |
| Split under pointer | ⌘⇧K |
| Redraw Outline from Baseline | ⌘⇧R |
| Simplify outline | ⌘⌥S |
| Cut Words / Cut Characters | ⌘⇧W / ⌘⌥W |
| Find Lines Here | ⌘⇧F |
| Set kind (Kind menu, first nine of the project's list) | ⌃⌥1 … ⌃⌥9 |
| Remove point / delete selection | ⌫ |
| Nudge selection or point | ← ↑ → ↓ (⇧ ×10, ⌥⇧ ×100) |
| Next / previous in reading order | Tab / ⇧Tab |
| Up to parent / down to first child | ⌘↑ / ⌘↓ |
| Move in order | ⌥⌘↑ / ⌥⌘↓ / ⌥⌘⇞ / ⌥⌘⇟ (the umbrella's) |
| Next doubtful | ⌘⌥N |
| Reading order overlay / words / characters layers | ⌘⌥O / ⌘⌥1 / ⌘⌥2 |
| Undo / redo | ⌘Z / ⇧⌘Z |

iPad gestures (finger unless said):

| Action | Gesture |
|---|---|
| Zoom / pan | pinch / two-finger drag |
| Select / add to selection | tap / tap with a second finger held on the page |
| Lasso | Pencil drag in Select on empty page (finger with the setting on) |
| Move selection | drag a selected shape |
| Reshape | drag a handle (44 pt target) |
| Context menu | long press |
| Draw, cut, paint, brush-select | Pencil in the tool |
| Switch tool ↔ Select | Pencil double-tap (system) |
| Undo / redo | two-finger tap / three-finger tap (system) |
| Tool popover | tap the tool button again |
| Kind | long press › Kind, or an attached keyboard's ⌃⌥1 … ⌃⌥9 |

## Data model and which operations are engine calls

Nothing new is stored for the common fixes: a merge, a split, a reassignment, a reshape, a
regenerate and a reorder are the existing records changed by the existing actions. The
additions, all on the engine:

| Operation | Action | New? |
|---|---|---|
| merge lines / regions | `segment.merge` (joins geometry and readings) | existing; joins geometry |
| knife split | `segment.split` with `cut_path` | parameter |
| reassign to a region | `segment.update_many` (`parent_segment_id`) + `reading_order.place` | existing |
| move / nudge a group | `segment.update_many` | existing |
| simplify | `segment.simplify` (tolerance) | new action |
| marker stroke | `segment.create` with `stroke`, `smoothing` | parameter |
| paintbrush stroke | `segment.create` with `brush_stroke` (points, widths) | parameter |
| regenerate outline | `segment.regenerate_outline` (ids, fixed height) | new action |
| order by clicking | `reading_order.renumber` | existing |
| set kind | `segment.update` (`kind`) | existing |
| cut words / characters | `segment.cut_words`, `segment.cut_characters` | new actions |
| move / add / remove a cut | `segment.update`, `segment.split`, `segment.merge` on words | existing |
| find lines here | `find-lines` job scoped to segments; accept = `segment.create_many` | existing job, scope |
| apply template | `segment.create_many` into a proposed pass per page | existing, new caller |
| validate | `GET …/segments/validate` | new read |
| character positions | `char_positions` on the reading (field exists) | producer |
| cut provenance | `metadata.cut_source`, `metadata.cut_confidence` on a word or character | metadata keys |

Every new action has an inverse that reads only its own `after` (ids and versions, never
geometry), as `segment.merge` and `segment.split` do, and a compare-and-set on every row it
touches. Selection, hover, the brush mask, a stroke in progress and the live Simplify preview
are app-local and are never sent.

## State, undo and redo

- The app's state is: the one selection; the armed tool and its popover settings per window;
  the stroke in progress; the layers per pane. All of it is rebuilt from the engine's answer
  after any action; none of it is persisted except the tool settings and layers.
- One gesture is one action, committed on release; a run of nudges is one; an Order sequence
  is one; a page-wide Cut Words is one batch per page (`undo.batches`); the Edit menu names it
  ("Undo Merge Lines", "Undo Cut Words on 3 lines": `undo.naming`, `undo.naming.counts`).
- Undo is by audit id through the one path (`undo.one-path`); a stale undo (someone reshaped the
  line since) is refused in words and the page reloads that line.
- Out of reach of the engine the editor is read-only and says so (ruled 2026-09-20, the umbrella).

## Performance

The umbrella's speed trial (slice 12) is the gate and is not restated. This file adds:
- Cut marks, words and characters draw only at a zoom where they are at least 2 pt apart on
  screen, and only inside the visible rect; a page of 20,000 characters draws its lines when
  zoomed out.
- The brush mask and a stroke in progress are rasterised locally at screen resolution, never at
  image resolution.
- The engine's answer to any action names only the changed segments; the store patches them in
  place (`source.app.segment-events-patch-in-place`); a knife across forty lines returns forty
  changed rows and no page reload.
- A `segment.regenerate_outline` over a page of lines runs in the background compute helper and
  reports per line; the page stays usable (`core/background_compute.py`).
- Hit-testing for cut marks uses the same spatial index as segments; a mark is a segment edge.

## Accessibility

- Every segment, word, character and cut mark is an accessibility element with its kind, its
  reading (or the two words a cut divides), its place in the order and its confidence when
  shown (`source.editor.voiceover`). Tools are buttons with labels and help; a mode announces
  itself when entered and left.
- Every tool has a keyboard path: Merge, Split under pointer (the pointer being the selected
  line's centre when driven by keyboard), Redraw, Simplify, Cut Words, kinds, order (Tab to the
  next segment, Return to number it in Order). A drawn stroke has no keyboard equivalent, and the
  Shape tool by points is its equivalent.
- Handles and marks meet 44 pt on touch; contrast of every stroke is held by the halo
  regardless of the image under it; Reduce Motion drops the two-second order flash.

## Edge cases

- `segment-editor.edge.overlapping-regions` — **[GAP]** (→ #4941; engine) two regions that overlap are allowed (a
  stamp over text is two regions); a line inside both belongs to the one that holds more of it,
  then the smaller (`SegmentShapes.containingRegion`'s rule, moved to the engine for the create
  and the reassignment); the validator reports overlaps over a tenth without refusing them.
- `segment-editor.edge.self-intersecting` — **[PARTIAL]** (→ #4941; engine) a self-crossing outline is never written: a
  reshape, a marker stroke or a merge that would make one is answered with the nearest simple
  polygon (the outer boundary of the shape's union) and the answer says it was simplified; an
  imported one is reported by the validator and offered Redraw from Baseline.
  *Built (2026-11-13):* `segment.create` and `segment.update` store a self-crossing polygon as the
  outer boundary of the area it covers (`line_join.simple_outline`), mark the row
  `outline_simplified` and answer `simplified: true`; a merge's outline is traced from a raster and
  is simple by construction. *Not built:* the validator's report on imported ones, `update_many`.
  *Tests:* `test_segment_self_intersecting.py`.
- `segment-editor.edge.empty-region` — **[PARTIAL]** (→ #4941; engine + app) a region with no lines is kept (a person
  may draw into it), drawn with its label only, and listed by the validator as empty before export.
  *Built (2026-11-13):* the validator lists it (`empty-region`). *Not built:* the label-only drawing.
- `segment-editor.edge.no-baseline` — **[OK]** (→ #4941; app + engine) a line with no baseline (a box from an older
  result, an Apple Vision line) cannot be cut by the knife, redrawn or cut into words by
  positions; the tools say so and offer **Add Baseline**, which proposes one through the box's
  middle in its direction (`segment.update` with `baseline`, marked estimated) for the person to
  drag onto the ink. *Built (2026-11-13):* Redraw refuses such a line in the engine and the menu says
  why; the knife leaves it alone and names it (`left_alone`, `no-baseline`); Add Baseline
  (`segment.add_baseline`, Edit › Segments ▸ Add Baseline) proposes one a quarter up from the
  box's bottom along its direction (down the middle of a vertical line), marked
  `baseline: estimated`, one undo. *Not built:* the offer on the tools' own refusal (the menu says
  it). *Tests:* `fichero-server/tests/unit/api/test_segment_add_baseline.py`; `fichero/Tests/Unit/general/Views/Source/RedrawOutlineTests.swift`.
- `segment-editor.edge.word-across-lines` — **[GAP]** (→ #5212; engine) a word broken at a line end is one segment with
  two shapes (`source.segment.shape-kinds`); Cut Words on both lines makes the two pieces and
  offers to join them as one word when the second line's reading starts without a space and the
  first's ends with a hyphen; the join is `segment.merge` keeping both shapes.
- `segment-editor.edge.knife-through-words` — **[PARTIAL]** (→ #4941; engine) a knife split of a line that already has
  words assigns each word to the part its centre falls in and splits a word the stroke crosses.
  *Built (2026-11-13):* words go with the part holding their centre, and undo puts them back
  (`moved_children`; `test_segment_split_knife.py::TestWords`). *Not built:* splitting a word the stroke crosses.
- `segment-editor.edge.merge-across-passes` — **[OK]** (engine) refused in words by
  `SegmentPassMismatchError`; the app offers nothing across passes but a match. Pinned by
  `fichero-server/tests/unit/api/test_segments_matches_forwarding.py`.
- `segment-editor.edge.stale` — **[OK]** (engine) every action here is refused when the row changed
  since it was read; the app reloads the row and shows what changed. Pinned by
  `fichero-server/tests/unit/api/test_segment_update_many.py::test_one_stale_line_refuses_the_whole_edit`.
- `segment-editor.edge.rtl-vertical` — **[PARTIAL]** (→ #5154; engine) a knife cut, a word cut and an order
  sequence follow the line's resolved direction: "before the cut" is the right part of a
  right-to-left line and the upper part of a vertical one (`estimated_cut` already does this
  for the proportional case). *Built (2026-11-13):* the knife (`test_segment_split_knife.py`, rtl and
  vertical). *Not built:* the word cut and the order sequence.

## 7.2 — Does Fichero keep Kraken's per-character positions today?

**No.** Read in `fichero-server/src/fichero_server/llm/kraken_runtime.py` on 2026-11-13:

- Both recognition paths call `net.predict(image, segmentation, config)` and keep, per line,
  `record.prediction` (the text), a line confidence (`_line_confidence`) and, on the
  read-given-lines path, `record.confidences` rounded per character (`ReadLine.char_confidences`).
  Neither reads `record.cuts`, which is where Kraken's baseline OCR record carries each
  character's extent along the line (the per-character boxes its own ALTO and PAGE serialisers
  write as `String` and `Glyph` positions).
- The reading row (`ContentRepresentation`, `models/__init__.py`) **already has the field**:
  `char_positions: list[float] | None`, documented as each character's place along the line
  from 0 to 1, served by `GET /api/segments/{id}/readings` and round-tripped by the reading
  tests. `char_confidences` beside it is written by the Kraken paths; `char_positions` is
  written by no producer in `src/` (the only writers are tests).
- A `segment.split` with `at_offset` therefore cuts the box in proportion along the direction and
  marks both parts `cut: estimated`; the code says why in its own docstring.
- ALTO export (`formats/alto.py`) writes a `String` per existing word segment and invents an
  implicit one for a line with none; it writes no `Glyph` and nothing from character positions.
  PAGE export writes `Word` and `Glyph` from existing segments only.
- Apple Vision's word boxes exist (packed per line) and are a separate source of word geometry,
  not character positions.

**What the engine must expose** (all behind `segment-editor.char-positions-kept`):

1. `kraken_runtime.ReadLine` gains `cuts`: per character, its start and end along the line in
   the page pixels of the frame read (from `record.cuts`; Kraken gives each as a small polygon
   in page coordinates, and the engine takes its extent projected onto the baseline). Both
   paths (`_read_given_raw` and the full-page read) fill it; a reader that gives none leaves it
   `None`.
2. The writers that turn a `ReadLine` into a reading (`llm/working_lines.write_readings` and the
   Kraken branches in `workflows/tools/vision_base.py` and `economy_htr.py`) pass
   `char_positions` to `representation.create`: the start of each character as a fraction of the
   baseline's arc length, carried to the photograph frame like every shape. A migration is not
   needed; the column exists.
3. `segment.split(at_offset)` reads the positions when the counting reading has them and cuts
   at the midpoint between the two characters, marked `cut: measured`; it keeps the proportional
   estimate only when it has none.
4. `segment.cut_words` and `segment.cut_characters` (new actions) derive the pieces from the
   positions and the outline, with the ink-gap fallback and the provenance keys above.
5. `GET /api/segments/{id}/readings` already serves the field; the generated client gets it on
   the next contract sync; the app's `Reading` model reads it for the cut marks.

Limits to say out loud in the manual: the positions are the recogniser's alignment, not a
measurement of the ink, and on cursive and notarial hands they drift by a character or two;
they exist only for lines a positional reader read (Kraken; not a vision model); and a
corrected reading typed by a person has no positions until the line is read again or cut by
hand, so the cut marks on such a line are the fallback's and say so.

## Build order

### Stage 1 — Structure: merge, split, regenerate (engine first)
#### Step 1.1 — Merge joins geometry and readings (#TBD)
- Behaviours: `segment-editor.merge-lines`, `segment-editor.merge-regions`
- Tests: test_segment_merge_lines.py, SegmentJoinTests.swift
- Size: M
#### Step 1.2 — Regenerate an outline from a baseline (#TBD)
- Behaviours: `segment-editor.regenerate-polygon-from-baseline`, `segment-editor.edge.no-baseline`, `segment-editor.edge.self-intersecting`
- Tests: test_regenerate_outline.py, RedrawOutlineTests.swift
- Depends on: 1.1
- Size: M
#### Step 1.3 — The knife (#TBD)
- Behaviours: `segment-editor.split-knife`, `segment-editor.split-at-a-point`, `segment-editor.edge.knife-through-words`, `segment-editor.edge.rtl-vertical`
- Tests: test_segment_split_knife.py, KnifeStrokeTests.swift
- Depends on: 1.2
- Size: M

### Stage 2 — Selecting, moving, reassigning
#### Step 2.1 — Selection: shift, lasso, all, same kind (#TBD)
- Behaviours: `segment-editor.select-marquee-lasso`, `segment-editor.select-shift-toggles`
- Tests: SegmentSelectionGesturesTests.swift
- Size: S
#### Step 2.2 — Group move, nudge, vertices and simplify (#TBD)
- Behaviours: `segment-editor.group-drag`, `segment-editor.nudge`, `segment-editor.vertices`
- Tests: test_segment_simplify.py, GroupMoveAndNudgeTests.swift
- Size: M
#### Step 2.3 — Reassign a line by drag (#TBD)
- Behaviours: `segment-editor.reassign-by-drag`, `segment-editor.edge.overlapping-regions`
- Tests: test_segment_reassign_by_drag.py, ReassignDragTests.swift
- Size: M
#### Step 2.4 — Brush selection (#TBD)
- Behaviours: `segment-editor.select-brush`
- Tests: BrushSelectTests.swift
- Size: S

### Stage 3 — Drawing tools
#### Step 3.1 — The marker (#TBD)
- Behaviours: `segment-editor.marker`
- Tests: test_segment_create_from_stroke.py, MarkerToolTests.swift
- Size: M
#### Step 3.2 — The paintbrush (#TBD)
- Behaviours: `segment-editor.paintbrush`
- Tests: test_segment_create_from_brush.py, PaintbrushToolTests.swift
- Depends on: 3.1
- Size: M
#### Step 3.3 — Tools, modes, cursors and the shortcut map (#TBD)
- Behaviours: `segment-editor.shortcuts-for-everything`, `segment-editor.every-edit-lands-at-once`
- Tests: fichero/Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift, ToolModesTests.swift
- Size: S

### Stage 4 — Order, kinds, layers
#### Step 4.1 — Order by clicking and the overlay (#TBD)
- Behaviours: `segment-editor.order-by-clicking`, `segment-editor.order-overlay`
- Tests: test_reading_order_renumber_by_clicks.py, OrderToolTests.swift
- Size: M
#### Step 4.2 — Kinds by key and layers (#TBD)
- Behaviours: `segment-editor.type-by-key`, `segment-editor.layers`, `segment-editor.edge.empty-region`
- Tests: KindKeysAndLayersTests.swift
- Size: S

### Stage 5 — Words and characters
#### Step 5.1 — Keep Kraken's character positions (#TBD)
- Behaviours: `segment-editor.char-positions-kept`
- Tests: test_kraken_char_positions.py
- Size: S
#### Step 5.2 — Cut words and characters, with provenance (#TBD)
- Behaviours: `segment-editor.cut-words-from-positions`, `segment-editor.cut-characters`, `segment-editor.cut-fallback-ink-gaps`, `segment-editor.cut-records-source-and-confidence`, `segment-editor.edge.word-across-lines`
- Tests: test_segment_cut_words.py
- Depends on: 5.1
- Size: L (split: positions path / ink-gap path)
#### Step 5.3 — Cut marks and the word view (#TBD)
- Behaviours: `segment-editor.cut-marks-editable`, `segment-editor.word-view`
- Tests: CutMarksTests.swift, WordViewSelectionTests.swift
- Depends on: 5.2
- Size: M

### Stage 6 — Helpers and integration
#### Step 6.1 — Validate before export, and export carries every edit (#TBD)
- Behaviours: `segment-editor.validate-before-export`, `segment-editor.export-carries-every-edit`
- Tests: test_segments_validate.py, test_cuts_in_page_and_alto.py
- Size: M
#### Step 6.2 — Coordinates: draw on a rendition, store on the photograph (#TBD)
- Behaviours: `segment-editor.coordinates-one-frame`, `segment-editor.provenance-on-every-segment`
- Tests: test_segment_drawn_on_a_rendition.py, DrawnFrameTests.swift
- Size: M
#### Step 6.3 — Find lines here, the low-confidence lens (#TBD)
- Behaviours: `segment-editor.rerun-on-area`, `segment-editor.low-confidence-lens`
- Tests: test_find_lines_scoped.py, DoubtfulLensTests.swift
- Size: M
#### Step 6.4 — Templates and training (#TBD)
- Behaviours: `segment-editor.batch-apply-template`, `segment-editor.corrections-train`
- Tests: test_region_template_proposals.py, test_kraken_set_words_and_regions.py
- Size: M

### Stage 7 — iPad
#### Step 7.1 — One input seam (#TBD)
- Behaviours: `segment-editor.one-input-seam`, `segment-editor.touch-pinch-pan`
- Tests: InputSeamTests.swift, SegmentEditorTouchTests.swift
- Size: L (split: the seam / the iOS layer)
#### Step 7.2 — Pencil, palm, two-finger undo (#TBD)
- Behaviours: `segment-editor.pencil-draws-finger-pans`, `segment-editor.palm-rejection`, `segment-editor.two-finger-tap-undo`
- Tests: SegmentEditorPencilTests.swift
- Depends on: 7.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | tool decisions, plans, gesture-to-request | `fichero/Tests/Unit/general/Views/Source/*Tests.swift` |
| Availability (Swift) | y | every verb reachable in Edit Segments | same |
| Backend (pytest) | y | every new action and parameter, inverses, refusals | `fichero-server/tests/unit/api/test_segment_*.py` |
| MCP | y | the new actions map | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | y | the new actions wire | `test_segments.py` |
| Click-around (XCUITest, Mac) | y | merge, knife, redraw end to end | `SegmentEditorUITests.swift` |
| iPhone (iOS) | n (iPad first) | — | — |
| iPad | y | Pencil and finger paths | `fichero/Tests/UI/ipad/` |
| Load (#4634) | y | regenerate over a page, cut words over a page, bounded | `test_segment_editor_load.py` |

## Accessibility identifiers

- `segment-editor.tool.<select|brush|knife|marker|paintbrush|order|shape>` — the tool buttons
- `segment-editor.tool.<name>.popover` — a tool's settings popover
- `segment-editor.verb.<merge|split|redraw|simplify|cut-words|cut-characters|find-lines-here|validate>` — the head's verbs
- `segment-editor.segment.<id>` / `segment-editor.cut.<id>` — a drawn segment / a cut mark
- `segment-editor.layer.<regions|lines|baselines|words|characters|order>` — the layer toggles
- `segment-editor.lens.doubtful.row.<id>` — a row in the low-confidence lens

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `segment-editor.tool.knife` | Knife | Cut every line the stroke crosses (K; hold for one stroke) | `segmentEditor.tool.knife` | [MISSING] |
| `segment-editor.verb.merge` | Join | Join the selected lines into one (⌘J) | `segmentEditor.verb.merge` | [MISSING] |
| `segment-editor.verb.redraw` | Redraw Outline | Draw the outline again from the baseline (⌘⇧R) | `segmentEditor.verb.redraw` | [MISSING] |
| `segment-editor.verb.cut-words` | Cut Words | Make word boxes from the reading's character positions (⌘⇧W) | `segmentEditor.verb.cutWords` | [MISSING] |
| (every other control above) | its name | its one-line rule above with its key | `segmentEditor.*` | [MISSING] |

## Rulings (owner 2026-11-13; the twelve questions of the first draft, all answered)

1. **Merge across regions:** move the other lines into the first line's region and merge, one action, one undo (`segment-editor.merge-lines`).
2. **A Marker or Paintbrush line takes the kind last used** (`segment-editor.marker`, `segment-editor.paintbrush`).
3. **Paintbrush pressure on the iPad is off by default**; an option turns it on.
4. **Kraken's character positions win over Apple Vision's words** when a line has both (`segment-editor.cut-words-from-positions`).
5. **Cut Words runs after every Kraken read**; its words are a machine's, marked as such.
6. **The ink-gap fallback stays**, marked with its source and a low confidence (`segment-editor.cut-fallback-ink-gaps`).
7. **Export offers both frames now**, the original photograph and the prepared image, chosen at export, the loss report naming the frame (`segment-editor.coordinates-one-frame`).
8. **Kinds are set from a menu whose shortcuts carry a modifier** (⌃⌥1 …), listing the project's kinds; never bare number keys (`segment-editor.type-by-key`).
9. **The Order tool commits on leaving the mode**, one undo for the sequence.
10. **Templates match by the page layout box only** (`segment-editor.batch-apply-template`).
11. **The touch stage is iPad only** (Stage 7).
12. **The build order stands as written**: merge, then redraw from baseline, then the knife, first.

## Open questions for the creative director

None outstanding; all twelve are answered (see Rulings).
