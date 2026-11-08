# Source Model — The segment editor: CRUD on every surface, no mode gate, nothing lost — Design Spec (#6413, #6412)

> Milestone: segment-editor
> Manual: the user manual's "Editing the lines" section (tracked by `segment-editor.md`) gains the Edit › Segments ▸ submenu, the context menus and the shortcuts once built.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it; code makes them pass.
> **Status: DRAFT — written 2026-11-08 by the spec writer from the owner's dev-build findings (#6413), the marquee grain finding (#6412) and the manager's rulings of 2026-11-08; the manager reads the steps before approval.** A companion to `segment-editor.md` (APPROVED 2026-10-26), which it does not change: it adds behaviours for what the owner found missing and cuts them into steps. The review that produced it is `agent-work/status/briefs/segment-editor-review-2026-11-08.md`.

## Intent

A person selects regions or lines anywhere, the Preview, the Inspector, the Segments pane or the Reader, and can create, edit, join and delete them from the same menu, context menu, shortcut and icon, each as one audited action with one undo, with no mode to enter first. Several marquees added at once are one action with one undo.

## Rulings (2026-11-04 to 2026-11-08)

- **Owner 2026-11-08:** full CRUD for regions and segments, each one audited action with one undo, reachable from context menus on every surface, a menu-bar home, a keyboard shortcut and an icon each; a table of operations × doors checked for shortcut uniqueness.
- **Owner 2026-11-08:** segment verbs act whenever segments are selected; no mode first.
- **Manager 2026-11-08:** the menu-bar home is Edit › Segments ▸, a submenu, not a top-level menu; the same items, shortcuts and icons in the context menus on every surface.
- Inherited from `segment-editor.md`: 2026-10-04 (#5114) no new mode, the tool bar; 2026-10-04 (#5115) the Inspector runs the same one-path verbs, never a second implementation.

## Behaviors

- `source.editor.n-marquees-one-audit-one-undo` — **[GAP]** (#6412, #6413; owner 2026-11-08 and lane-ie's run 2026-11-08: boxes drawn as regions ARE kept. The app's flow is one `PUT /api/artifacts/{id}/regions` with `op=add` per marquee, and that route already converts the page and writes SEGMENT rows through `segment.convert_and_edit` (`artifacts.py` `edit_artifact_regions`, "one audited, undoable action per edit"), so three marquees gave three segment rows, three audit rows and three undos. Not a loss; the gap is the grain) adding N marquees at once (▶ on a set of marquees, or New Region over several) is ONE create batch on the page's segment pass through the existing segment path (`segment.create_many`, after the page's one conversion when it is result-only), ONE audit row and ONE ⌘Z for the N regions, never N calls and N audit rows; a single marquee stays one action as today. The Segments store is re-read once after the batch and the N regions are drawn, listed and selected together. Unverified, to reproduce on a scratch library before any claim of loss: a page whose shown pass has a RESULT artifact (not a bare regions artifact), where `RegionEditTarget`'s third clause may refuse or route differently; if regions vanish there it is a separate finding, recorded on #6412 with the steps that show it. Acceptance: draw three marquees and press ▶ once: three segments appear in the Segments pane and the Inspector, the audit shows ONE row naming three, one ⌘Z removes all three; the red test on base shows N adds give N audit rows. *Test:* `test_n_marquees_one_audit_row_6412.py` (not yet written; fails on base: N adds, N audit rows), `PreviewSegmentCrudTests.swift` (not yet written).

- `source.editor.no-mode-gate-selection-is-the-edit-state` — **[GAP]** (#6413; owner 2026-11-08: segment editing and Join show only after the metadata icon and Edit Segments; ruled: available whenever segments are SELECTED. Code: `WindowState.isEditingSegments` gates the menu (`SegmentMenuCommands.swift`, Delete, Join and the attributes `.disabled(!editing)`, "Turn on Edit Segments to change segments"), the Preview handlers (`ZoomableImagePreviewMac+Regions.swift:92, 102, 163, 195`, `+SegmentEdits.swift:85` nudge, `RegionInteractionLayer+Reshape.swift:11`), the PDF page (`PDFPageWithToolbar+SegmentEdits.swift:18`), toggled at `ZoomableImagePreviewMac+Overlays.swift:144`) a selection IS the edit state: select, delete, join, the attributes and nudge act on the selected segments with no mode first, on every surface, and the menu's reason reads "Select segments on the page" and nothing about a mode; the gate is removed at every site above. What remains of Edit Segments is the SHAPE tool, renamed Edit Shape: drawing a new shape by hand and the reshape handles on the selection, a tool-bar state like the markup tools (the 2026-10-04 ruling on #5114: the tool bar, no new mode), never a precondition for a verb; New Region and New Line need no tool. Acceptance: click a region on a fresh page, press ⌫: it is deleted with one ⌘Z and no mode was entered; select two lines, ⌘J joins them; with nothing selected the items are disabled with "Select segments on the page". *Test:* `SegmentVerbsNeedNoModeTests.swift` (not yet written; the menu's enabled state and reason as a pure function of selection count with no editing flag; each handler's guard gone), the existing `RegionSelectionTests.swift`.
- `source.editor.crud-one-action-each-every-door` — **[GAP]** (#6413; owner addition 2026-11-08) the segment editor has full CRUD for regions and segments, each operation ONE audited engine action with ONE undo (Select All: app state; New Region and New Line: `segment.create_many`; Edit Shape and Nudge: `segment.update`; Kind, Direction, Furniture: `segment.update_many`; Join: `segment.merge`; Delete: `segment.delete`, `SegmentDeleter`'s one batch), each ONE Swift component rendered by every door: the Edit › Segments ▸ submenu, the context menus of the Preview, the Inspector, the Segments pane and the Reader's lines, one keyboard shortcut and one icon each, as the table in `agent-work/status/briefs/segment-editor-review-2026-11-08.md` lists them (shortcuts proposed: ⌥⌘A Select All Segments, ⌥⌘N New Region, ⌥⇧⌘N New Line, ⌥⌘E Edit Shape, ⌘J Join as today, ⌫ Delete on every surface but the menu bar; the uniqueness test decides); a disabled item says why under it, as Page › Segments already does. Acceptance: the same eight items, in the same order with the same icons, appear in Edit › Segments ▸ and in the four context menus; each acts on the focused surface's selection through the one component; one ⌘Z after any of them. *Test:* `SegmentDoorsAgreeTests.swift` (not yet written; the item list is one table rendered by every door; the shortcut set is unique by `MenuShortcutUniquenessTests`' rule), the existing `MenuShortcutUniquenessTests.swift`.
- `source.editor.edit-segments-submenu-and-doors` — **[GAP]** (#6413; ruled by the manager 2026-11-08) the segment operations live in the Edit menu as a SUBMENU, Edit › Segments ▸, not a new top-level menu and no longer under Page (Page › Segments' `SegmentMenuContent` moves, one component); the submenu is the same `SegmentMenuContent` the context menus render; `menus.context-matches-bar` and `menus.no-hand-rolled-duplicates` hold. Acceptance: Edit › Segments ▸ lists the operations; Page has no Segments item; a context menu on a segment in the Reader shows the same list. *Test:* `SegmentDoorsAgreeTests.swift` (not yet written), the existing `PageMenuTests.swift`.
- `source.editor.select-all-then-one-delete` — **[GAP]** (#6413; owner 2026-11-08: the document Inspector has no way to select ALL its segments and delete them in one action) Select All Segments selects every segment of the page (regions and lines, the working pass) from the Inspector, the Segments pane, the Reader's lines and the Preview (`RegionSelection.selectAll`, the one shared selection, `source.editor.selection-shared`), and Delete on that selection is `SegmentDeleter`'s ONE audited `segment.delete` batch, one audit id, one ⌘Z, with the Inspector's count ("Delete 112 Segments") and the engine's refusal in words when a line cannot go. Acceptance: in the Inspector of a page with 112 segments, Select All Segments then Delete removes all 112 in one step, the Preview and Segments pane empty together, one ⌘Z brings all 112 back. *Test:* `SelectAllThenDeleteTests.swift` (not yet written; through the real `RegionSelection` and `SegmentDeleter.ids`), the existing `RegionSelectionSelectAllTests.swift`.
- `source.editor.add-region-and-line-from-anywhere` — **[GAP]** (#6413; owner 2026-11-08: editing and making segments in the Preview is hard; wanted clear ways to ADD a region and a segment, edit, and see them saved) New Region and New Line are offered everywhere the doors are (`source.editor.crud-one-action-each-every-door`): from the Preview a drag with the Shape tool draws the shape (`source.editor.draw-shapes`, `source.editor.make-new-in-the-preview`), from a menu or the Inspector New Region makes a region at the page's centre or around the selected lines and New Line a line inside the selected or pointed region, each selected at once with its handles shown for Edit Shape, each saved through the existing segment path (`segment.create_many`, one batch for several) and SEEN saved: the new row appears in the Segments pane and the Inspector with "saved" state from the store, never from the view's memory. Acceptance: Inspector › New Region adds a region that is listed, selected, reshapeable, and still there after reopening; New Line inside it adds a line in reading order. *Test:* `PreviewMakeNewSegmentTests.swift` (not yet written, the planned one), `PreviewSegmentCrudTests.swift` (not yet written).

## Build order

Written 2026-11-08 for #6413 and #6412 after the Fable review (`agent-work/status/briefs/segment-editor-review-2026-11-08.md`). For lane-ie, in order. The manager reads the steps before approval.

### Stage 1 — CRUD on every surface, no mode gate, nothing lost

#### Step 1.1 — N marquees, one audit row, one undo (#6412)
- Behaviours: `source.editor.n-marquees-one-audit-one-undo`
- Tests: fichero/Tests/Unit/general/Models/RegionSelectionTests.swift, test_n_marquees_one_audit_row_6412.py (not yet written), PreviewSegmentCrudTests.swift (not yet written)
- Size: S

The regions route already lands segments (`segment.convert_and_edit`); this step changes the grain: ▶ over N marquees sends ONE create batch through the existing segment path (`segment.create_many`) and the Preview re-reads the store once. Red test first: on base, N adds give N audit rows. Unverified and NOT claimed: loss on a page whose shown pass has a result artifact; reproduce on a scratch library before saying so.

- test (to write): `test_n_marquees_one_audit_row_6412.py` in fichero-server/tests/unit/api/ (three regions in one batch: three segment rows, one audit row, one undo removes three; a single region unchanged)

#### Step 1.2 — the gate goes; Edit › Segments ▸ and the same doors on every surface (#6413)
- Behaviours: `source.editor.no-mode-gate-selection-is-the-edit-state`, `source.editor.edit-segments-submenu-and-doors`, `source.editor.crud-one-action-each-every-door`
- Tests: fichero/Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift, fichero/Tests/Unit/general/App/PageMenuTests.swift, fichero/Tests/Unit/general/Models/RegionSelectionTests.swift, SegmentVerbsNeedNoModeTests.swift (not yet written), SegmentDoorsAgreeTests.swift (not yet written)
- Depends on: 1.1
- Size: M

Swift only. Order: the guards at the seven sites named on the bullet go, the menu's reason loses its mode clause; Edit Segments becomes the Edit Shape tool-bar state; `SegmentMenuContent` moves under Edit › Segments ▸ and is rendered by the four context menus with the table's icons and the proposed shortcuts, the uniqueness test run before any chord is kept.

- test (to write): `SegmentVerbsNeedNoModeTests.swift` in fichero/Tests/Unit/general/App/ (enabled state and reason from the selection count alone; Edit Shape is a tool, not a precondition)
- test (to write): `SegmentDoorsAgreeTests.swift` in fichero/Tests/Unit/general/App/ (one item table rendered by the submenu and the four context menus; icons and shortcuts equal; no chord repeats another in the app)

#### Step 1.3 — Select All Segments, then one Delete, from the Inspector, the Segments pane and the Reader (#6413)
- Behaviours: `source.editor.select-all-then-one-delete`
- Tests: fichero/Tests/Unit/general/Models/RegionSelectionSelectAllTests.swift, fichero/Tests/Unit/general/Models/RegionSelectionTests.swift, SelectAllThenDeleteTests.swift (not yet written)
- Depends on: 1.2
- Size: S

Swift only: Select All Segments over the shared `RegionSelection` from every surface; Delete through `SegmentDeleter` as today, with the count on the item.

- test (to write): `SelectAllThenDeleteTests.swift` in fichero/Tests/Unit/general/Models/ (all the page's segments selected from the Inspector; one delete plan with every id; one audit id; the refusal in words)

#### Step 1.4 — New Region, New Line, Edit Shape, and seeing them saved (#6413, #6181, #6183)
- Behaviours: `source.editor.add-region-and-line-from-anywhere`, `source.editor.preview-crud`, `source.editor.make-new-in-the-preview`
- Tests: fichero/Tests/Unit/general/Models/RegionSelectionTests.swift, PreviewMakeNewSegmentTests.swift (not yet written), PreviewSegmentCrudTests.swift (not yet written)
- Depends on: 1.1, 1.2
- Size: M

Swift on the engine's existing actions: New Region and New Line as items and from the Inspector, the drawn shape through the same create, the handles under Edit Shape, the saved state read from the store.

- test (to write): `PreviewMakeNewSegmentTests.swift` and `PreviewSegmentCrudTests.swift` in fichero/Tests/Unit/general/Views/Source/ (the create call built from a menu press and from a drawn shape; the new segment selected; the store re-read; one undo)

## Open questions

1. The proposed chords (⌥⌘A, ⌥⌘N, ⌥⇧⌘N, ⌥⌘E) stand only if `MenuShortcutUniquenessTests` and the system-chord audit accept them; a collision picks another chord, never a second meaning for one.
2. Whether Edit Shape stays a tool-bar state or becomes handles that appear on any single selection with no tool at all (recommended later, once a drag on a selected shape is told apart from a pan).
