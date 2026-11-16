# Segment editor consistency matrix: operation × surface × door, EXISTS vs NEEDED (2026-11-08)

Fable review for #6413 (owner, widened 2026-11-08) and #6415, read from the code at origin/integration. Companion to `segment-editor-review-2026-11-08.md`; the manager reads this before further steps (Steps 1.2–1.4 of `source/segment-editor-crud.md` are approved in substance and stand; anything NEEDED here that they do not cover becomes a new step only on the manager's word). File references are the doors as they are; "—" means no door exists.

## 0. The two bars (owner question 1)

Today one Preview carries three rows of chrome and the owner cannot tell reading from editing:
- **Head controls** (`Views/Shell/PaneHead/PreviewHeadControls.swift`): up to the parent image, previous/next page, previous/next rendition, Renditions menu, show/hide zoom controls (⌘⌥E), and the **Edit Segments** toggle (line 125). Reading chrome with one editing switch inside it.
- **Reader toolbar** (`Views/Reader/ReaderToolbar.swift`, `+Controls.swift`): close, pages, renditions, zoom in/out/fit/actual, magnifier, loupe, **Edit image** (`canvasEditModeToggle`) and the image tools, pin, and a Display menu of toggles: Show Image, Annotations, Word Bounding Boxes, Regions, Text Inline, and **Edit Segments** again (line 268: "Draw, move, join and delete segments on this page").
- **Markup tools row** (`Views/Shell/PaneHead/PreviewMarkupToolsRow.swift`): highlight and its colour/mode, the **Shape kind** picker (box, polygon, baseline; line 370), tags (`Toolbar/AnnotationBar.swift`).

NEEDED (proposal for the spec, not yet a step): **two bars with two names.** A **Reader bar** (navigation, zoom, renditions, what is displayed) and an **Editing bar** (image tools, shape tool, markup) that shows when the pane is in an editing state or a segment is selected, so the eye knows which it is in; the segment VERBS are in neither bar: they are the selection's (Edit › Segments ▸, the context menus, the Inspector). "Edit Segments" leaves both bars and becomes the Edit Shape tool on the Editing bar (`source.editor.no-mode-gate-selection-is-the-edit-state`).

## 1. The matrix

Surfaces: **P** Preview image (`ZoomableImagePreviewMac*`, `Regions/*`), **PDF** Preview PDF page (`PDFViewer/PDFPageWithToolbar*`), **I** document Inspector (`Inspector/Source/SegmentInspectorView.swift` and its sections), **S** Segments pane (`Views/Segments/*`), **R** Reader lines (`Reader/Page/ReaderLinesView.swift`, `ReaderLineRow`), **M** menu bar (`App/Menus/FocusedCommands/SegmentMenuCommands.swift` Page › Segments; `…+LineVerbs.swift` Page › Segments › Open/Correct/Delete/Named order), **K** keyboard.
Doors per cell: c = click/gesture, x = context menu, m = menu-bar item, k = shortcut, b = bar button. EXISTS in plain text; **NEEDED** in bold.

| Operation | Engine action | P | PDF | I | S | R | M | K |
|---|---|---|---|---|---|---|---|---|
| Select one / add (⇧) | app state `RegionSelection` | c (`RegionInteractionLayer`, pointer feed) | c (`PDFPageView+OCRBoxes`) | c (rows; `InspectorPath.selectedSegmentIds`) | c (`SegmentsPictureGrid`) | c (`ReaderLineRow`) | — | ⇧-click |
| Select all segments | `RegionSelection.selectAll` | k ⌘A inside the mode (`+Regions.swift:134`) | — | **NEEDED x/m/k** | **NEEDED x/m/k** | **NEEDED x/m/k** | **NEEDED Edit › Segments ▸ Select All Segments** | **NEEDED ⌥⌘A** |
| Select the hierarchy (parent ↔ children, up to the page) | app state | selecting a parent lights children (ruled A, #5426; drawn) | partial | path up: `InspectorPath` walks parents; children: Order section (`parentSegmentId`, line 169) lists them, **NEEDED: select them, act on them, climb to the page as a row** | drill down only (`SegmentsPaneView.parentId`, Open) **NEEDED: up, and select a level** | — **NEEDED: region block selects its lines** | — | — |
| Create: draw box / polygon / baseline | `segment.create` (segment pass) or `PUT …/regions op=add` → `segment.convert_and_edit` (artifact pass) | c with the Shape tool (`RegionInteractionLayer+DrawShape`, `drawSegmentShape`), marquees ▶ (`+RegionEntry`) | — | — | — | — | — | — |
| Create: New Region / New Line without drawing | `segment.create_many` | **NEEDED x** | **NEEDED x** | **NEEDED b/x (Inspector "New Region", "New Line")** | **NEEDED x** | **NEEDED x (New Line after this one)** | **NEEDED m** | **NEEDED ⌥⌘N, ⌥⇧⌘N** |
| Create N at once, one audit | `segment.create_many` | ▶ over N marquees = N calls today (`+Regions.swift:192`) **NEEDED one batch** (Step 1.1) | — | — | — | — | — | — |
| Move | `segment.update` / artifact `moveRegion` | c drag (`moveSegment`, `+Regions.swift:263`), mode-gated | c | — | — | — | — | — |
| Reshape (handles) | `segment.update`, `segment.convert_and_edit` first | c (`RegionInteractionLayer+Reshape`), mode-gated | c (`reshapePDFSegment`) | — | — | — | — | — |
| Nudge | `segment.update` | k arrows (`nudgeSelectedShapePoint`), mode-gated | — | — | — | — | — | ←↑↓→, ⇧ |
| Attributes: kind, direction, furniture | `segment.update_many` | x (`SegmentAttributeMenu.Items`) | — | — | — | — | m, mode-gated | — |
| Attributes: hands, certainty, rights (bulk) | `segment.update_many` | — | — | b (`InspectorBulkSection`, N lines at once) | — | — | — | — |
| Text: correct a line | `POST /api/segments/{id}/correct` (no audit id yet, see `CorrectThisLine.swift`) | popover opens the Reader row (`+SegmentPopover`) | — | editor (`InspectorReadingEditor`) | x (`CorrectThisLineButton`) | c/x (field; `ReaderTextEdit`) | m Page › Segments › Correct | ⌘-return in field |
| Text: typing splits/joins lines | `segment.split`, `segment.merge` via the reader editor | — | — | — | — | c (`source.textedit.return-splits-the-line`, `backspace-joins-in-reading-order`, PARTIAL) | — | ⏎, ⌫ in text |
| Join / merge | `segment.merge` | x/m, mode-gated (`joinSelectedSegments`) | — | **NEEDED x/b** | **NEEDED x** | **NEEDED x** | m ⌘J, mode-gated | ⌘J |
| Split a shape (easy split) | `segment.split` exists (`segments.py:3155`), `segment.unsplit` | **NEEDED: a cut gesture (click a point on the line with the Split tool) and Split at Cursor** | **NEEDED** | **NEEDED b/x "Split…"** | **NEEDED x** | text ⏎ only | **NEEDED m** | **NEEDED ⌥⌘S (proposed)** |
| Delete | `segment.delete` batch (`SegmentDeleter`) | k ⌫ mode-gated, x | partial | b/x (`deleteLines`, count) | x (`LineVerbsTarget.delete`) | x (`ReaderLineRow` Delete), ⌫ | m Page › Segments › Delete, no key (rule) | ⌫ |
| Undo / restore a version | audit id; `segment.restore_version(s)` | ⌘Z | ⌘Z | Making section Restore (`InspectorSegmentMakingSection`) | ⌘Z | ⌘Z | Edit › Undo | ⌘Z |
| Open the segment (drill) | — | double-click popover | — | — | Open (`OpenSegmentMenuItem`) | — | m Page › Segments › Open | ⌘↓ (Finder) |
| Run a recipe on the next step (owner question 5) | Start plan `folder_id`, `redo_steps` | — | — | — | — | — | Project › Read › Reading ▸ Run the Recipe on This Folder…, Run a Step Again on This Folder (`FocusedRunRecipeOnFolderButton`, `RecipeSetupStore.redoSteps`), folder context menus; Set Up's stage page "Run this step" (`SetupStageSamples.runThisStep`) | — **NEEDED: a selection-scoped "Run <next step> on This" on every surface (#6411's scope rule), named from the recipe's next undone step for the selection** |

## 2. What the matrix says

1. **The gate is the biggest inconsistency**: move, reshape, nudge, attributes, join and ⌫ exist on the Preview but only inside `isEditingSegments`; the Inspector, Segments pane and Reader have Delete and Correct and nothing else. Step 1.2 (gate gone, one item table on every door) closes most cells at once.
2. **Hierarchy is drawn, not selectable** in the Inspector: `InspectorPath` can walk up and the Order section lists children, but there is no row for the page, no "select the children", and no verbs on a level. NEEDED (new step on the manager's word): an Inspector "Where it sits" section with the path up to the page and the children down, each row selectable and carrying the same context menu; the Segments pane gains "Up" beside its drill-down.
3. **Split has an engine action and no door** except typing ⏎ in the Reader. NEEDED: Split as a tool on the Editing bar (click the cut point on a selected line), Split… in the item table, ⌥⌘S proposed; `segment.unsplit` is its undo.
4. **Create without drawing** does not exist anywhere; Step 1.4 adds New Region / New Line.
5. **Run a recipe on the next step** exists only folder-scoped and in the Project menu and Set Up; nothing on a segment or page selection says what the next step is. NEEDED: one item, "Run <step name> on This Page/These Lines", from the recipe's steps-done for the selection's page (`compute.recipe.folder-shows-steps-done`), through #6411's selection-scoped start; on every surface's context menu and Project › Read › Reading ▸.
6. **Text correction has no audit id** (`CorrectThisLine.swift` ponytail note): it joins the undo story when the audited action lands; a cell to carry on the table, not a new step here.
7. **The hierarchy note (#6415)**: stroke › character › word › line › region › page ("segment" is any level, owner 2026-11-08), all editable; later steps tie output to segments. The matrix's rows are per level once the Inspector shows the levels (item 2).

## 3. Proposed next steps (for the manager to approve, not written)

- 1.5 Hierarchy in the Inspector and the Segments pane: path up to the page, children down, selectable, same verbs.
- 1.6 Split: the tool, the item, the chord; unsplit as undo.
- 1.7 Two bars: Reader bar and Editing bar, named; Edit Segments becomes Edit Shape on the Editing bar.
- 1.8 Run the next step on this selection: one item from the recipe's steps-done, through #6411's scope.

## 4. The Reader reviewed against the matrix (owner addition 2026-11-08)

What the Reader has today, by file:
- **Lines mode, the strip of line rows** (`Views/Reader/Page/ReaderLinesView.swift`, `ReaderLineRow`): each line's picture cut from the page above its text, editable in place; a click reveals the line in the Preview (one selection, `Knowledge/ReaderLineSelection.swift`). Context menu: **Correct This Line…** (`CorrectThisLineButton`) and **Delete** (`SegmentDeleter`, one batch, the why on the row). Focused line verbs for the menu bar (`App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+LineVerbs.swift`): Correct This Line…, Open, Delete Lines, Create Named Order. Nothing else: no Select All, no New Line, no Join, no Split, no attributes, no Edit Shape, no nudge.
- **Text mode** (`Knowledge/ReaderTextEdit.swift`, `ReaderTextEditRunner.swift`): typing is a new reading (`representation.create`), an edit across lines is one `representation.create_many`, a line emptied is marked left out (never deleted); ⏎ splits and ⌫ joins in reading order (`source.textedit.return-splits-the-line`, `backspace-joins-in-reading-order`); `ReaderLineMove.swift` moves a line's text between lines. No context menu verbs on a selected run of text beyond the system's; no segment verbs.
- **Reader toolbar** (`ReaderToolbar.swift`, `+Controls.swift`, `+Overflow.swift`): navigation, zoom, renditions, loupe, magnifier, Edit image and its tools, the Display menu (with the Edit Segments toggle), pin. No segment verb.
- **Keyboard**: no `onKeyPress` or shortcut for a segment verb in `Views/Reader/*`; ⌫ on a row is the system delete of text, not the line.

Missing, by the matrix: Select All Segments; New Line (after this one) and New Region; Join (two rows selected); Split (a cut point on the row's picture, or Split at Cursor in its text); the attributes (kind, direction, furniture); Edit Shape (handles on the row's picture, or Reveal in Preview to reshape); the hierarchy (a region header row over its lines, selectable); Run <next step> on These Lines; one icon and chord per item. The rule for the fix: the Reader renders the SAME `SegmentMenuContent` item table on its row context menu and under Edit › Segments ▸ for the focused Reader selection, and its existing Correct This Line… and Create Named Order join that table as Reader-only rows at the end; `LineVerbsTarget` stops being a second verb set and becomes the Reader's adapter onto the one table (Step 1.9).
