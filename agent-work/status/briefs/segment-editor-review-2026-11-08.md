# Segment editor review: CRUD on every surface, no mode gate, the lost creates (2026-11-08)

Fable review (spec-writer) of `docs/contributor_manual/specs/source/segment-editor.md` and the editor-in-Preview behaviours it holds (`source.editor.preview-crud` #6181, `source.editor.make-new-in-the-preview` #6183, `source.editor.draw-shapes`, `source.editor.selection-shared`, the 2026-10-04 rulings on #5114 and #5115), against the code at origin/integration, for #6413 (owner 2026-11-08), #6412 (lost creates, P1) and the manager's rulings of 2026-11-08 (Edit › Segments submenu; full CRUD, one audited action each; every door on every surface; the mode gate goes). Read-only: nothing here closes an issue. The steps are in the spec's new Build order (Stage 1, Steps 1.1–1.4).

## 1. What the spec already says, and where it is thin

- **Rulings hold.** 2026-10-04 (#5114): "the segment focus is the tool bar the Preview already has; there is no new mode." 2026-10-04 (#5115): "shapes are drawn in the Preview, readings are typed in the Reader, and the Inspector shows the selection and may run the same one-path verbs, never a second implementation." Both are the right frame for #6413; neither is honoured by the code's `isEditingSegments` gate (section 3).
- **CRUD is described but not as one table.** Create is `draw-shapes` (PARTIAL) and `make-new-in-the-preview` (MISSING); delete is `SegmentDeleter`'s one batch (`source.editor.delete-selected-lines`, named in code, no bullet found under that id in the spec: a gap); update is reshape, nudge, attributes (`SegmentEdit.Attribute`), join (`join-is-easy` MISSING); select is `selection-shared` (PARTIAL). No bullet says "each operation is one audited action with one undo, reachable from the same doors on every surface". Added as `source.editor.crud-one-action-each-every-door`.
- **Select all is absent.** The Preview has `RegionSelection.selectAll` (used by its own ⌘A path in `ZoomableImagePreviewMac+Regions.swift:134`); the Inspector, the Segments pane and the Reader have no select-all over a document's segments, and no bullet asks for one. Added as `source.editor.select-all-then-one-delete`.
- **The create path is split, and one half loses data (#6412).** `RegionEditTarget` sends an edit "to the result the SHOWN pass came from": on a page whose shown pass has an artifact the Preview's create and move go to the artifact regions route (`PUT /api/artifacts/{id}/regions`, `_edit_regions_impl`), which rewrites the artifact's region list and writes NO segment; the Segments store, which every surface draws from since #5235 (`reloadSegmentsAfterRegionEdit`), then shows the page without them. Only an artifact-less pass takes `segment.create` (`drawSegmentShape`: "only on a segment pass"). That is the likeliest cause of "added regions were never saved"; lane-ie confirms it on a scratch library. The spec never said which path a create takes. Added as `source.editor.create-is-segment-create-many` (the manager's rule: the audited `segment.create_many`, never the regions-artifact edit).
- **Menu placement.** The spec's Compare and hierarchy sections say nothing about a menu; the code has Page › Segments (`SegmentMenuCommands.swift`, "was the Segment menu, #5652"). Ruled 2026-11-08: Edit › Segments ▸ (a submenu, not a top-level menu); the same items, shortcuts and icons in every context menu. Added as `source.editor.edit-segments-submenu-and-doors`.
- **The editor-in-Preview behaviours (#6181, #6183) stand** and become Steps 1.4's content; their "Preview's Edit Segments mode (#5114)" wording is read as the ruling says: the tool bar, not a gate.

## 2. The operations × doors table (checked against `ui/menus-and-commands.md`)

Every operation: ONE audited engine action, ONE undo, ONE Swift component rendered by every door (`menus.no-hand-rolled-duplicates`, `menus.context-matches-bar`). Shortcuts are PROPOSED; `MenuShortcutUniquenessTests` and the system-chord audit (`menus.shortcut-uniqueness`) decide. ⌘A, ⌫, ⌘Z stay routed to text when a text field has focus (`UndoRouting`, `MenuShortcutBoundaryTests`).

| Operation | Engine action (exists) | Edit › Segments ▸ item | Context menus (Preview, Inspector, Segments pane, Reader lines) | Shortcut (proposed) | Icon (SF Symbol) |
|---|---|---|---|---|---|
| Select All Segments (on this page) | none (selection is app state, `RegionSelection.selectAll`) | Select All Segments | yes, on the page/empty area | ⌥⌘A (⌘A stays text / rows) | `checkmark.rectangle.stack` |
| New Region | `segment.create_many` (one region) | New Region | yes | ⌥⌘N | `rectangle.dashed.badge.plus` |
| New Line | `segment.create_many` (one line, in the region under the pointer or selected) | New Line | yes | ⌥⇧⌘N | `text.badge.plus` |
| Edit Shape (handles on the selection) | `segment.update` per drag, `segment.convert_and_edit` first on a result-only page | Edit Shape | yes | ⌥⌘E | `pencil.and.outline` |
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

## 4. The #6412 rule for the steps

Every create in the app goes through the audited `segment.create_many` (one batch, one audit id, one ⌘Z), on the page's segment pass, converting a result-only page first (`segment.convert_and_edit`, its own ⌘Z) exactly as reshape does; NEVER the regions-artifact edit (`PUT /api/artifacts/{id}/regions`), which stays for promoting words and for artifact-only pages that have no segment pass to write to, said so in words. A test fails on base: create on a page with an artifact, reload the Segments store, the segment is there.

## 5. Order for lane-ie (after the P1)

1.1 the create path (#6412, P1); 1.2 the gate goes, Edit › Segments ▸ and the doors; 1.3 select all and one delete in the Inspector, Segments pane and Reader; 1.4 New Region, New Line, Edit Shape, and seeing them saved. The manager reads the steps before approval.
