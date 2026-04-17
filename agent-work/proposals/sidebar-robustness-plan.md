# Sidebar Robustness Overhaul — Architecture Plan

**Target milestone:** 0.0.3 (or later, per two-ahead rule)
**Status:** Research complete, ready for Daniel's review before implementation begins
**Prepared:** 2026-04-17 by feature-dev:code-architect (Claude Sonnet 4.6)
**Scope:** Plan only — no code written. Daniel must approve before implementation.

---

## A. Current-State Analysis

### What Works Today

Based on reading all 35 sidebar source files, the current sidebar can:

1. **Rename any item inline.** `SidebarItemRow+Rename.swift` handles documents, searches, conversations, workflows, chains, schedules, triggers, and library headers. `RenameStateManager` (`SidebarStateManagers.swift:6`) coordinates the shared editing state.

2. **Reparent documents via drag-drop (on-folder drop).** `.draggable(item.id)` + `.dropDestination(for: String.self)` in `SidebarItemRow.swift:174-185` handles internal sidebar reparenting. `moveItemToFolder` calls `documentStore.moveDocument(_:toParent:)` which hits `PUT /api/documents/{id}/move` (`documents.py:347`). Circular-drop detection exists via `isDescendant` (`SidebarItemRow+Helpers.swift:5`).

3. **Accept Finder file drops.** All drop targets use `.onDrop(of: [UTType.fileURL], isTargeted:, perform: ([NSItemProvider]) -> Bool)` — the NSItemProvider path that preserves folder URLs intact (`SidebarItemRow+DropHandlers.swift:8`). This was fixed from the Transferable/`.dropDestination(for: URL.self)` approach after MEMORY.md lesson #587.

4. **Folder drops import recursively.** `ImportServiceGenerated.importFiles` detects `isDirectory` via `FileManager` and routes to `importFolderAndWait` (`ImportServiceGenerated.swift:68`).

5. **Drop onto library header.** `LibrarySectionHeader` (`SidebarSectionHeader.swift:64`) accepts `.onDrop(of: [.fileURL])` and calls `importService.importFiles(..., parentId: nil)` for library-root imports.

6. **Hierarchical folder rendering in all section types.** `SidebarItemBuilder.buildHierarchyFromPath` (`SidebarItemBuilder.swift:126`) builds folder trees for searches, chats, workflows, and chains using the `folderPath` field. Document hierarchy uses `parentId`.

7. **Expansion persistence.** `SidebarState` stores `expandedItems` and `unifiedSectionExpansionStates` keyed by library+section.

8. **Cross-view drag (grid → sidebar) is half-wired.** `LibraryView+DisplayModes.swift:25,110` applies `.draggable(doc.id)` to both icon-grid thumbnails and list rows, emitting a `String` (doc ID). The sidebar's `.dropDestination(for: String.self)` on folder rows can receive these IDs. However there is no end-to-end test confirming this works across views.

### Known Breaks and Tech Debt

**#572 — sort_order not persisted for Documents.** `SidebarItem.swift:87` has the comment `// Documents don't have sort_order (yet)`. The Swift `Document` struct (`Document.swift`) has no `sortOrder` field. The Python `Document` model (`models.py:439`) has `sort_order: int = 0`. The `/documents/reorder` route (`documents.py:276`) accepts a list of IDs but the field is never read back by the Swift client. The drag reorder UX drops the offset entirely — `handleLibraryRootInsert` (`SidebarView+DropHandlers.swift:18`) explicitly ignores `offset` with a comment referencing #572.

**#580 — between-row drops disabled.** The `ForEach` children inside every `DisclosureGroup` inside `List` cannot use `.onInsert(of:)` without triggering `SwiftUICore/HomogeneousCollection.swift:179: Fatal error: index -1 out of bounds` on macOS 14+. Comments referencing this are at `SidebarItemRow.swift:162-171` and `SidebarView+ViewComponents.swift:319-325`. The result: there is no visual insertion-line drop target between rows. Drops only land ON folders, not between them.

**#583 — missing unit test coverage.** No tests exist for: case-insensitive extension detection, `handleProvidersDrop`, `handleInsertBetweenChildren`, `parentFolderItem(of:)`, `handleDropBesideItem`, the `RenameStateManager` focus/blur flow, or the `SidebarItemBuilder.buildLibraryHierarchy` Inbox-first ordering with mixed types.

**#584 — zero accessibility coverage.** No `.accessibilityLabel`, `.accessibilityHint`, or `.accessibilityAction` on `SidebarItemRow`, `LibrarySectionHeader`, or the rename `TextField`. The sidebar is not operable with VoiceOver.

**#585 — SidebarItemRow is a monolith.** At 217 lines, `SidebarItemRow.swift` has three distinct branch shapes (has-children, empty-folder, leaf) that share state unnecessarily. Splitting into `FolderRow`, `LeafRow`, and a shared `RowLabel` would isolate drop logic per shape and enable targeted unit tests.

**JPG uppercase bug.** The Python backend already handles uppercase extensions: `ingest.py:154` calls `path.suffix.lower()` before looking up `_FILE_TYPE_MAP`. The bug is therefore in the Swift layer. Finder drag-drop uses `UTType.fileURL` as the type identifier, which is extension-agnostic — so that path is safe. The most likely failure point is in the file picker path (`SidebarActions.swift:22-38`), where files selected via `fileImporter` may go through a different UTType conformance check on the SwiftUI side. The `.fileImporter(allowedContentTypes:)` filter on `SidebarView.swift:219` must include `UTType.jpeg` (not just `UTType.image`) or be set to `[UTType.item]` to avoid silently filtering uppercase-extension files that resolve to `public.jpeg` vs `public.image`. This needs reproduction tracing — a `sidebarViewLogger` breadcrumb inserted before the `fileImporter` callback would confirm which path drops the file.

**Searches/Workflows/Chats folders use string paths, not parent_id.** The `folderPath` convention (`"/"`, `"/production/images"`) works for the current flat-rename flow but does not support arbitrary nesting without touching both the Python model and the `SidebarItemBuilder.buildHierarchyFromPath` logic. Reparenting a search into a folder currently has no backend route — only the `SavedSearch.folderPath` string would need updating, but there is no "move search" API endpoint.

**No `sort_order` update on Documents after reparent.** `move_document` (`documents.py:347`) only updates `parent_id`. It does not assign a `sort_order` based on the drop position. Sidebar order therefore resets to server-side insertion order after every drop.

### Architectural Boundaries

`SidebarItemBuilder` (`SidebarItemBuilder.swift`) is the single source of truth for which documents enter the sidebar tree. Its `visibleDocs` filter (`line 63`) uses `Document.isNavigableContainer`, which gates on `docType == .folder || fileType == .pdf` (`Document.swift:305`). Changing what appears in the sidebar means changing exactly this one filter.

The boundary between builder and renderer: `SidebarItemBuilder` produces a `[SidebarItem]` tree; `SidebarView.rebuildCaches` stores it in `cachedLibraryHeaders`; `SidebarView+ViewComponents.unifiedContent` renders from that cache. Drop and rename handlers in `SidebarItemRow` operate on the cache (for local lookups like `isDescendant`) and call services (for persistence). The cache is rebuilt via `Combine` observers in `SidebarObservers.swift` when service data changes.

---

## B. Target Architecture

### Data Model Changes

**Backend — add `sort_order` to Document (issue #572).**
The Python `Document` model already has `sort_order: int = 0` (`models.py:439`) but the field is not returned by the `/documents/reorder` endpoint in a form the Swift client reads. The `/documents/reorder` route (`documents.py:276`) takes `doc_ids: list[str]` and sets `sort_order = i`. This is the right shape; what is missing is the Swift client calling it after a drag-drop reorder.

The `PUT /{doc_id}/move` route should also accept an optional `sort_order: int` query parameter so a drag-and-drop reparent can simultaneously assign a position.

**Swift — add `sortOrder` to Document.**
`Document.swift` needs `var sortOrder: Int = 0` with CodingKey `"sort_order"`. This is a non-breaking additive change. `SidebarItem.fromDocument` (`SidebarItem.swift:72`) currently hardcodes `sortOrder: 0` — change to `sortOrder: doc.sortOrder`.

**Backend — add `folder_path` update to non-document entity move routes.**
Saved searches, conversations, workflows, and chains all use `folderPath` for their folder hierarchy. A "move search into folder" action currently has no API endpoint. Add `PATCH /search/saved/{id}/move` (accepting `folder_path: str`) and equivalent routes for conversations, workflows.

**No new SidebarFolder entity needed.** The existing `folder_path` + `parent_id` convention is sufficient. Document folders are already first-class `DocType.folder` documents with `parent_id` nesting. Virtual folders (for searches, workflows) use the string `folderPath` field. No new database table is needed.

### Backend API Changes (summary)

| Route | Change | Reason |
|---|---|---|
| `PUT /documents/{id}/move` | Add `sort_order: int?` query param | Position-aware reparent |
| `POST /documents/reorder` | Existing, call from Swift on drag-complete | Persist document order |
| `PATCH /search/saved/{id}/move` | New | Move saved search to folder path |
| `PATCH /chat/conversations/{id}/move` | New | Move chat to folder path |
| `PATCH /workflows/{id}/move` | New | Move workflow to folder path |
| `POST /search/saved/{id}/folders` | New (or use reorder) | Create search folders |
| `POST /workflows/folders` | New | Create workflow folders |

Each new endpoint follows the existing pattern in `documents.py` — thin route, `Depends(get_library_database)`, Pydantic request body, returns updated entity.

### SwiftUI View Changes

**Split `SidebarItemRow` into three views (issue #585).**
- `SidebarFolderRow` — handles `DisclosureGroup` shape. Has both `dropDestination(for: String.self)` (internal drags) and `.onDrop(of: [.fileURL])` (Finder drags). No between-row `.onInsert`.
- `SidebarLeafRow` — leaf files and non-folder items. Has `.draggable` + `.dropDestination` for "beside" semantics. No `.onDrop(of: [.fileURL])` is needed here; it can fall through to the parent folder's drop.
- `SidebarRowLabel` — the `Label { Text; Icon }` with rename field, shared by both row types. Pure display, no drop logic.

This split reduces each file to under 100 lines and makes the drop logic testable in isolation.

**DropDelegate adoption for between-row drops (issue #580).**
The `.onInsert` crash is Apple's bug in nested `ForEach` inside `DisclosureGroup` inside `List`. The fix is to implement `DropDelegate` on the `SidebarFolderRow`'s children `ForEach`. A `DropDelegate` provides `dropUpdated(info:)` to compute the hover region (above/on/below based on `info.location.y` vs row height), `validateDrop(info:)` to accept `UTType.fileURL` + `UTType.utf8PlainText`, and `performDrop(info:)` to fire the insert at the computed position. The native blue insertion line is replicated by a thin `Rectangle().fill(Color.accentColor)` overlay shown at the computed insertion point during hover.

**Inline rename trigger: F2 and double-click label.**
The rename `TextField` in `SidebarItemRow+Label.swift:39` already exists and responds to `onSubmit` and `onExitCommand`. The missing piece is the keyboard trigger. Add `.onKeyPress(.f2)` on `SidebarView`'s `List` to fire `handleRenameSelectedItem()` when the selected row has keyboard focus. Double-click on the label text (not the disclosure triangle) should also trigger rename: use `.onTapGesture(count: 2)` on `fullWidthLabel` inside `SidebarFolderRow` and `SidebarLeafRow`.

**Cross-view drag (grid → sidebar folder).**
Grid thumbnails already emit `.draggable(doc.id)` as a `String` (`LibraryView+DisplayModes.swift:25`). The sidebar folder rows already accept `.dropDestination(for: String.self)`. The issue is that IDs dragged from the grid are bare doc UUIDs (e.g. `"abc-123"`) while the sidebar expects `"doc:abc-123"` prefixed IDs for its `extractActualId` helper. This mismatch must be resolved either by (a) emitting `"doc:\(doc.id)"` from the grid's `.draggable`, or (b) making `extractActualId` handle both forms. Option (b) is safer — add a guard in `extractActualId` (`SidebarItemRow+Helpers.swift:37`) that if there is no `:` separator, the string is a bare doc ID and should be treated as such.

**Case-insensitive file picker (JPG fix).**
The `fileImporter` modifier on `SidebarView.swift:219` passes `allowedContentTypes`. Audit this list to ensure it includes `UTType.jpeg`, `UTType.tiff`, `UTType.heic`, `UTType.png`, and their uppercase-filename-safe equivalents, or switch to `[UTType.item]` (all files) and let the backend reject unsupported types. The latter is simpler and more future-proof.

**Accessibility pass (issue #584).**
- `SidebarItemRow` needs `.accessibilityLabel(item.name)` + `.accessibilityHint` describing available actions (rename, delete, move).
- `LibrarySectionHeader` needs `.accessibilityLabel(library.displayName)`.
- The rename `TextField` needs `.accessibilityLabel("Rename \(item.name)")`.
- Folder expansion chevron needs `.accessibilityValue(isExpanded ? "expanded" : "collapsed")`.

### Drag-Drop Architecture (full picture)

Four distinct drop surfaces and their mechanisms:

| Surface | Drop types | API used | Notes |
|---|---|---|---|
| Library section header | Finder files/folders | `.onDrop(of: [.fileURL])` NSItemProvider | Already works; `parentId: nil` |
| Folder row (on-folder) | Sidebar items (String) + Finder files | `.dropDestination(for: String.self)` + `.onDrop(of: [.fileURL])` | Already works |
| Between rows | Sidebar items + Finder files | `DropDelegate` | Needs #580 fix |
| Library grid → sidebar folder | Sidebar items (String) | `.dropDestination(for: String.self)` | Needs `extractActualId` fix |

The unified `handleProvidersDrop` (`SidebarItemRow+DropHandlers.swift:20`) should remain as the single NSItemProvider loading path. The `DropDelegate` implementation should reuse the same loading logic.

### Test Architecture

Unit-testable (pure logic, no SwiftUI instantiation needed):
- `SidebarItemBuilder.buildLibraryHierarchy` — already has tests in `SidebarItemTests.swift`; extend with `sortOrder` ordering tests
- `detectFileType` (Python) — test uppercase extensions produce the same `FileType` as lowercase (already works per code review, but add explicit test)
- `extractActualId` — already tested in `DragDropTests.swift`; extend for bare-UUID input
- `isDescendant` / `containsDescendant` — already tested
- `RenameStateManager` — partial tests exist (`SidebarTests/StateManagerTests.swift`); add focus-blur cancel flow
- `DropDelegate.dropUpdated` y-threshold logic — extract the "is cursor in top/middle/bottom third" calculation into a free function and unit-test

Integration/UI tests (require `XCUITest`):
- Drag a grid thumbnail onto a sidebar folder and confirm `moveDocument` is called
- Drag from Finder with a `.JPG` file and confirm it imports
- Rename via F2 and confirm persistence
- Reorder within a section and confirm `sort_order` persists after app restart

---

## C. Implementation Plan (12 commits)

Each commit must include unit tests in the same commit (project rule — `AGENTS.md` Hard Rule #5).

**Step 1: `fix: case-insensitive file picker allowedContentTypes (JPG bug)`**
- Files: `SidebarViewExtensions.swift` (or wherever the `fileImporter` modifier is constructed), `SidebarView.swift:219`
- Change: Replace the current `allowedContentTypes` list with `[UTType.item]`
- Tests: Add a Python test confirming `detect_file_type(Path("photo.JPG"))` returns `FileType.image`
- Acceptance: Import a `.JPG` file (uppercase) via the file picker without it being rejected
- Dependencies: None

**Step 2: `fix: extractActualId handles bare doc UUIDs for cross-view drag`**
- Files: `SidebarItemRow+Helpers.swift:37`
- Change: If `prefixedId` contains no `:`, treat as a bare doc ID (equivalent to `doc:<id>`)
- Tests: Extend `IDPrefixStrippingTests` in `DragDropTests.swift` with a bare-UUID case
- Acceptance: Drag a grid thumbnail onto a sidebar folder and confirm the correct document ID is used in `moveDocument`
- Dependencies: None

**Step 3: `feat: add sortOrder to Swift Document model (#572 partial)`**
- Files: `Document.swift`, `SidebarItem.swift:87`
- Change: Add `var sortOrder: Int = 0` to `Document` with `CodingKey "sort_order"`. Update `SidebarItem.fromDocument` to use `doc.sortOrder` instead of `0`
- Tests: Extend `SidebarItemBuilderTests` to verify sortOrder propagation from Document to SidebarItem
- Acceptance: `SidebarItem.sortOrder` reflects the backend value
- Dependencies: None

**Step 4: `feat: wire document reorder API after drag-drop sort (#572)`**
- Files: `SidebarItemRow+DropHandlers.swift`, `DocumentServiceGenerated.swift`, `SidebarView+DropHandlers.swift`
- Change: After a successful `moveItemToFolder` or root-insert, call `documentStore.reorderDocuments(idsInOrder:withinParent:)`. Add `reorderDocuments` to `DocumentStore` calling `POST /documents/reorder`
- Tests: Unit test that `reorderDocuments` constructs the correct API request body
- Acceptance: Drag a document to a new position; after app restart, the document appears at that position
- Dependencies: Step 3

**Step 5: `feat: add move routes for searches, chats, workflows (backend)`**
- Files: `fichero-api/src/fichero/api/routes/search.py`, `chat.py`, `workflows.py`
- Change: Add `PATCH /search/saved/{id}/move`, `PATCH /chat/conversations/{id}/move`, `PATCH /workflows/{id}/move` — each accepts `folder_path: str` and updates the entity
- Tests: Python unit tests for each new route
- Acceptance: All three routes return the updated entity with the new `folder_path`
- Dependencies: None

**Step 6: `feat: split SidebarItemRow into FolderRow + LeafRow (#585)`**
- Files: Create `SidebarFolderRow.swift`, `SidebarLeafRow.swift`, `SidebarRowLabel.swift`; gut `SidebarItemRow.swift` to a thin dispatcher
- Change: Extract the three `bodyContent` branches into dedicated views. Move drop logic to each dedicated file. `SidebarRowLabel` holds `itemLabel` and `renameField`
- Tests: Verify each row type renders with the correct `isFolder` / `isFolder == false` shape via model-layer assertions
- Acceptance: SwiftUI builds cleanly; no visual regression; existing drag-drop still works
- Dependencies: Step 2 (so extractActualId is robust before splitting)

**Step 7: `feat: DropDelegate between-row drops (#580)`**
- Files: New `SidebarBetweenRowDropDelegate.swift`, update `SidebarFolderRow.swift`
- Change: Implement `DropDelegate` on the children `ForEach` inside `SidebarFolderRow`. The delegate tracks the current drag position, shows a blue insertion-line overlay, and calls `handleInsertBetweenChildren` on drop. Remove all comments referencing the `.onInsert` crash as "still broken"
- Tests: Unit test the y-threshold calculation: extract `insertionRegion(for:rowHeight:)` into a standalone function and test above/middle/below cases
- Acceptance: Dragging an item between two folder children shows a blue line and drops at the correct offset
- Dependencies: Step 6

**Step 8: `feat: F2 keyboard rename + double-click rename trigger`**
- Files: `SidebarFolderRow.swift`, `SidebarLeafRow.swift`, `SidebarView+ViewComponents.swift`
- Change: Add `.onKeyPress(.f2) { handleRenameSelectedItem(); return .handled }` on the outer `List`. Add `.onTapGesture(count: 2) { renameState.startRename(...) }` on `SidebarRowLabel`
- Tests: Unit test `RenameStateManager.startRename` is idempotent (calling it twice with a new name replaces the previous)
- Acceptance: Pressing F2 on the selected row activates the inline rename field; double-clicking a label activates rename
- Dependencies: Step 6

**Step 9: `feat: cross-section folder support for searches and workflows`**
- Files: `SidebarItemRow+DropHandlers.swift`, new `SidebarSearchFolderManager.swift`, `SidebarWorkflowFolderManager.swift`
- Change: Extend the drop handler to detect when the dragged item is a `savedSearch`, `conversation`, or `workflow` (by ID prefix: `"search:"`, `"chat:"`, `"workflow:"`) and call the corresponding move API from Step 5 instead of `documentStore.moveDocument`. Folder creation for these types uses `buildHierarchyFromPath` which already works — the missing piece is the API call.
- Tests: Unit test that the prefix dispatcher routes to the correct service
- Acceptance: Dragging a saved search onto a search-folder row updates the search's `folderPath` and the sidebar rebuilds correctly
- Dependencies: Steps 5, 6

**Step 10: `feat: accessibility pass (#584)`**
- Files: `SidebarFolderRow.swift`, `SidebarLeafRow.swift`, `SidebarRowLabel.swift`, `LibrarySectionHeader.swift`
- Change: Add `.accessibilityLabel`, `.accessibilityHint`, `.accessibilityValue` (for expansion state), and `.accessibilityAction` (rename, delete) on all interactive elements
- Tests: Add `SidebarAccessibilityTests.swift` with Swift Testing assertions verifying `.accessibilityLabel` is non-empty on `makeFolder(...)` items. (ViewInspector or a model-layer proxy test — no XCUITest needed for this level.)
- Acceptance: VoiceOver reads row names, expansion states, and available actions without extra developer annotation
- Dependencies: Step 6

**Step 11: `test: sidebar test coverage sprint (#583)`**
- Files: `fichero-swiftui-tests/SidebarTests/` — add new test files
- Change: Add the 10 missing unit tests: `handleProvidersDrop` URL filter, `parentFolderItem` resolution, `handleDropBesideItem` sibling semantics, `handleInsertBetweenChildren` with mixed provider types, `RenameStateManager` blur-cancel, `SidebarItemBuilder` sort_order sorting, case-insensitive extension (Python), `DropDelegate` insertion region, `extractActualId` bare-UUID, `isDescendant` with cross-tree IDs
- Tests: This step IS the tests
- Acceptance: All 10 new tests pass; overall coverage increases per #583 target
- Dependencies: Steps 2–8

**Step 12: `feat: cross-view drag grid→sidebar confirmation + UX polish`**
- Files: `LibraryView+DisplayModes.swift`, `SidebarFolderRow.swift`
- Change: Confirm `.draggable(doc.id)` on grid items interoperates with the sidebar's `.dropDestination(for: String.self)`. If a mismatch still exists after Step 2, emit `"doc:\(doc.id)"` from the grid. Add a brief success toast when a document is moved via cross-view drag.
- Tests: Extend `DragDropTests` with a test that simulates a bare ID drop on a folder and confirms `moveDocument` is called with the correct UUID
- Acceptance: Dragging an image or PDF from the grid into a sidebar folder moves it; the grid refreshes to reflect the new parent
- Dependencies: Steps 2, 6

---

## D. References to Research Before Starting

**`DropDelegate` protocol (AppKit/SwiftUI interop).**
Why: The `.onInsert` crash fix (#580) requires `DropDelegate`. Study `dropUpdated(info:) -> DropProposal` — specifically `DropInfo.location` which gives the CGPoint needed for above/on/below thresholding.
Ref: `mcp__xcode__DocumentationSearch` for "DropDelegate" and WWDC 2019 session 231 "Mastering Xcode Previews" (tangentially useful) and WWDC 2020 session 10028 "What's new in SwiftUI" (DropDelegate introduction).

**`NSItemProvider` async loading patterns.**
Why: The current `withCheckedThrowingContinuation` wrapper (`SidebarItemRow+DropHandlers.swift:120`) is correct but has a silent failure mode when `loadObject` calls neither completion block. Add a `withTimeout` wrapper. MEMORY.md notes NSItemProvider vs Transferable as a recurring bug class.
Ref: Apple's `NSItemProvider` documentation; search for `loadObject(ofClass:completionHandler:)`.

**`@FocusState` + `TextField` patterns for inline rename.**
Why: `SidebarItemRow+Label.swift:39` uses `@FocusState var isRenameFocused` to auto-focus the rename field. The current `.task { isRenameFocused = true }` can race with the row appearing in the list. Study the proper placement of focus assignment in SwiftUI lists.
Ref: `mcp__xcode__DocumentationSearch` for "FocusState" on macOS; WWDC 2021 "Direct and reflect focus in SwiftUI".

**`List` identity and `DropDelegate` interaction.**
Why: Step 7 requires a `DropDelegate` attached to a `ForEach` inside a `DisclosureGroup` inside a `List`. Verify the `DropDelegate` approach is crash-free in this nesting shape before committing (the `.onInsert` crash may hint at a deeper `List` homogeneity constraint).
Ref: `mcp__xcode__DocumentationSearch` for "DropDelegate macOS"; the SwiftUI forums thread on `HomogeneousCollection` crash.

**SwiftUI `List` selection and `.draggable` across view hierarchy.**
Why: Confirm that `String` Transferable items emitted by `.draggable(doc.id)` in `LibraryView` are receivable by `.dropDestination(for: String.self)` in `SidebarView` (they are in different branches of the view tree, potentially in different `NSView` hierarchies if the split view creates separate `NSScrollView`s).
Ref: WWDC 2022 "Bring multiple windows to your SwiftUI app"; Apple's Food Truck sample project drag-drop section.

---

## E. Risks and Open Questions

**Risk 1 — DropDelegate nesting crash.** The `.onInsert` crash is in `SwiftUICore/HomogeneousCollection`. `DropDelegate` avoids `.onInsert`'s internal path but uses the same `List`-level hit-testing machinery. If the crash root is in how macOS 14's `List` handles drop events in nested groups, `DropDelegate` may also trigger it. Mitigation: test with a minimal repro (`DisclosureGroup { ForEach { view.dropDelegate(...) } }`) in a throwaway project before writing the full implementation.

**Risk 2 — Cross-view drag String identity.** SwiftUI's `Transferable` for `String` uses `UTType.utf8PlainText`. If the grid and sidebar are in separate AppKit view hierarchies (possible with `NavigationSplitView` or `HSplitView`), the drag pasteboard may not propagate correctly. Mitigation: add a logging breakpoint in `handleDropIntoFolder` to confirm receipt.

**Risk 3 — pbxproj for new Swift files.** Per MEMORY.md, the main `Fichero` target is not file-system synchronized. Creating `SidebarFolderRow.swift`, `SidebarLeafRow.swift`, `SidebarRowLabel.swift` requires explicit `pbxproj` entries. Mitigation: prefer appending to existing files (`SidebarItemRow.swift`) until Xcode MCP's `XcodeGlob` confirms the new files compile.

**Risk 4 — Sort order races.** After a reparent-then-reorder sequence, if the first `moveDocument` response hasn't refreshed the cache before the reorder call fires, the `sort_order` update may reference stale IDs. Mitigation: perform the reorder call inside the `.task` after `documentStore.refresh()` completes, not in parallel.

### Open Questions — NEED DANIEL'S DECISION BEFORE IMPLEMENTATION

1. **Folder nesting depth cap.** Should folders be unlimited depth or capped at 2 levels? The `buildHierarchyFromPath` function already supports unlimited nesting via recursion, but deep nesting in a narrow sidebar column becomes unreadable. **Recommendation:** unlimited, with a visual indent cap at 3 levels (further nesting still works but doesn't indent further).

2. **Should images appear in the sidebar?** Currently only folders and PDFs satisfy `isNavigableContainer`. Daniel's request mentions dragging images into folders from the grid — that works without images being sidebar items. But "folders for images" implies image-containing folders are navigable, which they already are. **Confirm:** images stay in the grid only, folders appear in the sidebar. No change needed unless Daniel wants top-level images to appear as sidebar leaves.

3. **Move vs Copy on grid drag to sidebar folder.** When a user drags an image from the grid onto a sidebar folder, should this MOVE the document (change `parent_id`) or COPY it? Move is the Finder-consistent semantic. **Confirm** this is the intended behavior.

4. **Folder-type items in Searches/Workflows sections.** Currently these use `folderPath` strings (`"/production"`) for virtual folders. Should these become first-class backend records (a new `SearchFolder` entity) or remain virtual (computed from the `folderPath` string)? Virtual is simpler and already works for display; the gap is that you can't rename a virtual search folder — you'd have to rename it by updating all searches within it. **Recommendation:** stay virtual for 0.0.3, promote to first-class records in 0.0.4 if users request individual folder rename.

5. **Multi-select drag.** Daniel's list does not explicitly mention multi-select drag, but the grid already supports multi-select (`selection: Set<String>` in `LibraryView`). Should a multi-select drag from the grid move all selected items simultaneously? This is out of scope for the first pass but should be noted in the issue for later.

---

## F. Scope Boundary (Explicitly Out of Scope for This Plan)

- Tags and colour-coding of sidebar items
- Smart folders (dynamic queries shown as sidebar items)
- Multi-select drag within the sidebar
- Sidebar search/filter (typing to filter sidebar items)
- Library merge or folder migration across libraries
- iCloud/sync of sidebar state
- Drag from sidebar to external apps (e.g. dragging a PDF from Fichero sidebar to Finder)
- Promoting virtual search/workflow folders to first-class backend entities (0.0.4+)
- Batch reorder (drag multiple items at once within a section)

---

*Plan prepared by: feature-dev:code-architect (Claude Sonnet 4.6)*
*Based on codebase read: 2026-04-17*
*Ready for Daniel's review. Implementation starts on 0.0.3 branch only after 0.0.2 testing is approved.*
