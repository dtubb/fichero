# Segment editor review: CRUD on every surface, no mode gate, the lost creates (2026-11-08)

Fable review (spec-writer) of `docs/contributor_manual/specs/source/segment-editor.md` and the editor-in-Preview behaviours it holds (`source.editor.preview-crud` #6181, `source.editor.make-new-in-the-preview` #6183, `source.editor.draw-shapes`, `source.editor.selection-shared`, the 2026-10-04 rulings on #5114 and #5115), against the code at origin/integration, for #6413 (owner 2026-11-08), #6412 (N marquees, N audit rows) and the manager's rulings of 2026-11-08 (Edit › Segments submenu; full CRUD, one audited action each; every door on every surface; the mode gate goes). Read-only: nothing here closes an issue. The steps are in the spec's new Build order (Stage 1, Steps 1.1–1.4).

## 1. What the spec already says, and where it is thin

- **Rulings hold.** 2026-10-04 (#5114): "the segment focus is the tool bar the Preview already has; there is no new mode." 2026-10-04 (#5115): "shapes are drawn in the Preview, readings are typed in the Reader, and the Inspector shows the selection and may run the same one-path verbs, never a second implementation." Both are the right frame for #6413; neither is honoured by the code's `isEditingSegments` gate (section 3).
- **CRUD is described but not as one table.** Create is `draw-shapes` (PARTIAL) and `make-new-in-the-preview` (MISSING); delete is `SegmentDeleter`'s one batch (`source.editor.delete-selected-lines`, named in code, no bullet found under that id in the spec: a gap); update is reshape, nudge, attributes (`SegmentEdit.Attribute`), join (`join-is-easy` MISSING); select is `selection-shared` (PARTIAL). No bullet says "each operation is one audited action with one undo, reachable from the same doors on every surface". Added as `source.editor.crud-one-action-each-every-door`.
- **Select all is absent.** The Preview has `RegionSelection.selectAll` (used by its own ⌘A path in `ZoomableImagePreviewMac+Regions.swift:134`); the Inspector, the Segments pane and the Reader have no select-all over a document's segments, and no bullet asks for one. Added as `source.editor.select-all-then-one-delete`.
- **The create grain (#6412), corrected 2026-11-08 after lane-ie's run.** Boxes drawn as regions ARE kept: the app sends one `PUT /api/artifacts/{id}/regions` `op=add` per marquee and that route converts the page and writes segment rows through `segment.convert_and_edit` (`artifacts.py` `edit_artifact_regions`); three marquees gave three segment rows. Not a loss. The gap is one action and one audit row per box: N marquees should be one batch, one audit row, one ⌘Z (`source.editor.n-marquees-one-audit-one-undo`). Unverified: a page whose shown pass has a RESULT artifact, where `RegionEditTarget`'s refusal clause applies; reproduce on a scratch library before any claim.
- **Menu placement.** The spec's Compare and hierarchy sections say nothing about a menu; the code has Page › Segments (`SegmentMenuCommands.swift`, "was the Segment menu, #5652"). Ruled 2026-11-08: Edit › Segments ▸ (a submenu, not a top-level menu); the same items, shortcuts and icons in every context menu. Added as `source.editor.edit-segments-submenu-and-doors`.
- **The editor-in-Preview behaviours (#6181, #6183) stand** and become Steps 1.4's content; their "Preview's Edit Segments mode (#5114)" wording is read as the ruling says: the tool bar, not a gate.

## 2. The operations × doors table (checked against `ui/menus-and-commands.md`)

Every operation: ONE audited engine action, ONE undo, ONE Swift component rendered by every door (`menus.no-hand-rolled-duplicates`, `menus.context-matches-bar`). Shortcuts are PROPOSED; `MenuShortcutUniquenessTests` and the system-chord audit (`menus.shortcut-uniqueness`) decide. ⌘A, ⌫, ⌘Z stay routed to text when a text field has focus (`UndoRouting`, `MenuShortcutBoundaryTests`).

| Operation | Engine action (exists) | Edit › Segments ▸ item | Context menus (Preview, Inspector, Segments pane, Reader lines) | Shortcut (proposed) | Icon (SF Symbol) |
|---|---|---|---|---|---|
| Select All Segments (on this page) | none (selection is app state, `RegionSelection.selectAll`) | Select All Segments | yes, on the page/empty area | ⌥⌘A outside the Reader; in the Reader ⌘A itself selects the lines (owner 2026-11-08) | `checkmark.rectangle.stack` |
| New Region | `segment.create_many` (one region) | New Region | yes | ⌥⌘N | `rectangle.dashed.badge.plus` |
| New Line | `segment.create_many` (one line, in the region under the pointer or selected) | New Line | yes | ⌥⇧⌘N | `text.badge.plus` |
| Edit Shape (handles on the selection) | `segment.update` per drag, `segment.convert_and_edit` first on a result-only page | Edit Shape | yes | a free chord from the uniqueness test (⌥⌘E is show/hide zoom controls) | `pencil.and.outline` |
| Nudge | `segment.update` | (arrow keys, no item) | no | ←↑↓→, ⇧ ×10 | — |
| Set Kind / Direction / Furniture | `segment.update_many` (`SegmentAttributeMenu.Items`, exists) | Kind ▸, Direction ▸, Furniture | yes | none | `tag` |
| Join | `segment.merge` (exists) | Join | yes | ⌘J (exists) | `arrow.triangle.merge` |
| Delete | `segment.delete` batch (`SegmentDeleter`, exists) | Delete N Segments | yes | ⌫ on every surface but the menu bar (the existing rule: a bare ⌫ in the menu bar would take it from text) | `trash` |
| Undo | the action's audit id | Edit › Undo | — | ⌘Z | — |

Collision check: ⌘J is already Join; ⌥⌘1–5 are workspaces, ⌥⌘L the loupe, ⌥⌘0 Activity, ⌥⌘F Find in Page, ⌥⌘H Hide Others (system), ⌃⌘F/⌃⌘S system; ⌥⌘R is proposed for Run the Recipe (#6411, pending the same test); none of ⌥⌘A, ⌥⌘N, ⌥⇧⌘N, ⌥⌘E is used in the spec's table or the tests' list as read today. The uniqueness test is the arbiter, not this table.

## 3. The mode gate: every site, and what "Edit Segments" still means

`WindowState.isEditingSegments` gates (toggle: `ZoomableImagePreviewMac+Overlays.swift:144`, the metadata strip's Edit Segments):
- `App/Menus/FocusedCommands/SegmentMenuCommands.swift`: Delete, Join and the attribute items `.disabled(!editing …)`; the reason "Turn on Edit Segments to change segments".
- `Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift:92, 102, 163, 195` (`isEditing:` passed to the layer; ⌫ on persisted regions only in the mode; marquee handling `!isEditingSegments`).
- `Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+SegmentEdits.swift:85` (nudge only in the mode).
- `Views/Preview/ImageViewer/Regions/RegionInteractionLayer+Reshape.swift:11` (`isEditing` from the window).
- `Views/Preview/PDFViewer/PDFPageWithToolbar+SegmentEdits.swift:18`.

Ruling to record (owner 2026-11-08): a SELECTION is the edit state. Select, delete, join, attributes and nudge act whenever segments are selected, with no mode first. What "Edit Segments" still means, recommended: it is the SHAPE tool only, the one thing that must not fire from a plain click or drag on a page (a drag selects or pans): drawing a new shape by hand and the reshape handles on the selection. It is a tool-bar state like the markup tools, named Edit Shape, never a precondition for the verbs. New Region and New Line from the menu or context menu need no tool: they make the segment where the pointer or the selection is, then select it (`make-new-in-the-preview`).

## 4. The #6412 grain for the steps

N marquees added at once are ONE create batch through the existing segment path (`segment.create_many` after the page's one conversion), one audit id, one ⌘Z; a single marquee stays as today. Red test on base: N adds, N audit rows. The regions route is not replaced.

## 5. Order for lane-ie

1.1 N marquees, one audit row, one undo (#6412); 1.2 the gate goes, Edit › Segments ▸ and the doors; 1.3 select all and one delete in the Inspector, Segments pane and Reader; 1.4 New Region, New Line, Edit Shape, and seeing them saved. The manager reads the steps before approval.

## 6. The hierarchy note (owner 2026-11-08, #6413, #6415)

The model is stroke › character › word › line › region › page ("segment" is any level, owner 2026-11-08), and ALL of it must be editable: the Inspector shows the selection's place in that hierarchy, up to the page and down to the children, and acts on any level with the same verbs. Later steps (readers, page readers, normalisation, names) tie their output back to a segment, never floating on the page (#6415, its step in `source/models-chains-and-projects.md`).

## 7. Design look: labelled tools and Paint-to-shape (owner 2026-11-08)

**What exists.** ONE Shape tool with a kind menu shown only in Edit Segments (`PreviewMarkupToolsRow.swift`, "Shape kind — Box: drag. Polygon: click points…"; `SegmentShapes.DrawKind` box, polygon, baseline; `RegionInteractionLayer+DrawShape.swift`, `ShapeDrawing.swift`); a finished polygon is `segment.create` of a REGION by its outline, a finished baseline a LINE by its open path (`source.editor.draw-shapes`, PARTIAL); `source.editor.make-new-in-the-preview` (#6183, MISSING) wants one gesture of the kind last used. No brush exists. The engine already binarises ink and takes connected components for other reasons (`media/blank_page.py` ink share, `media/flatten_curve.py` `_baselines`, `media/find_page.py` contours), and `refine-shapes` is a job kind with no runner.

**Why it is unclear.** The kinds are hidden in a menu of a tool that is itself hidden behind a mode; "Box" does not say it makes a region; a polygon takes a click per point, a baseline too, so selecting a line of text means clicking along it.

**Proposed tools on the Editing bar** (Step 1.7's bar), each a labelled button with an icon, a one-letter key while the bar has focus (never in a text field), a crosshair cursor, Escape cancelling, the kind REMEMBERED (#6183):

| Tool | Makes | Gesture | Icon (SF Symbol) | Key |
|---|---|---|---|---|
| Region | a REGION as a box | drag a rectangle | `rectangle.dashed` | R |
| Polygon | a REGION by its outline | click points; first point or double-click closes | `pentagon` | P |
| Line | a LINE by its baseline | click points along the writing; double-click finishes | `underline` | L |
| Paint | a LINE or a REGION FITTED to the ink | brush over the writing; release fits | `paintbrush.pointed` | B |
| Split (Step 1.6) | two from one | click the cut | `scissors` | S |
| Edit Shape (Step 1.2) | handles on the selection | drag a handle | `pencil.and.outline` | E in the bar; the menu chord is a free one from the uniqueness test |

**Paint-to-shape rule.** The brush is a stroke (a polyline with a width, the width adjustable with [ and ] and shown as the cursor's circle). On release the app sends ONE `segment.create` whose anchor is the stroke (an anchor kind `stroke` with points and width; no new field, no new route); the engine, in a pure function of the stroke and the page's current image (`media/paint_fit.py`, tested on synthetic ink), binarises the image under the stroke's mask, keeps the ink components whose centre lies inside it, and fits: for **Line**, the baseline as the lower envelope of the ink per column, smoothed, and the outline as the ink's hull padded by the stroke's half-width; for **Region**, the outline as the concave hull of the components (a box when Paint is used with Region chosen); nothing fitted (no ink under the stroke) refuses in words and draws nothing. The result is created on the shown pass as the Shape tool's results are, selected, with Edit Shape's handles shown at once so the fit is adjusted by hand; one ⌘Z removes it. A stroke across two lines of writing fits two LINES in one create batch (one audit row) when the ink falls into two rows; across text and margin it fits what it covers, the person trims with the handles. What Paint fits is a starting shape, never ground truth: the segment's `made_by` says "painted, fitted by Fichero" until a person edits it.

**Relation to the existing behaviours.** `source.editor.draw-shapes` keeps its three gestures, now as three labelled tools (Region, Polygon, Line) and no kind menu; `source.editor.make-new-in-the-preview` (#6183) is satisfied by the remembered tool plus New Region / New Line without drawing (Step 1.4); Paint is new (`source.editor.paint-fits-a-shape`). The two Edit Segments toggles go (Step 1.7). The owner reads this before Step 1.11 is approved.
