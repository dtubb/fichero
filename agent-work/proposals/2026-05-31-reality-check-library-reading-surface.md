# Reality Check: Library & Reading Surface Milestone — Open Issues
Generated: 2026-05-31  
Method: read-only code inspection via jCodemunch + GitHub issue list. No builds, no edits.

---

## Safe to Close Now (DONE — evidence in code)

| # | Title | Evidence |
|---|-------|----------|
| **#1261** | Add back/forward navigation arrows to top toolbar | `ContentView.mainToolbarContent` (line 392) has `navigateBack()` / `navigateForward()` buttons with ⌘[ / ⌘], disabled states wired to `navigationHistory.canGoBack/canGoForward`. Done. |
| **#1186** | Navigation history: back/forward toolbar + Cmd+' shortcut | `AppNavigationHistory` model + `ContentView+NavigationHistory.swift` + the toolbar buttons above. The shortcut uses ⌘[ / ⌘] (not ⌘') but the feature is shipped. |
| **#1229** | Inspector UX: move toggle to main toolbar + filterable attribute strip | Part 1 (inspector toggle in toolbar) is done — `mainToolbarContent` has `showInspectorSidebar.toggle()` button at `.automatic` placement with ⌘⌥I shortcut. The toolbar comment explicitly references #1229. Part 2 (filterable attribute strip) is NOT done — `DisplayAttributesStrip` is not filterable. See below for PARTIAL classification. |
| **#616** | Hide icon-grid list panel (focus mode) | `showDocumentGrid` `@SceneStorage` state + toolbar button `rectangle.split.2x1 / rectangle` wired with ⌘⇧G. `centerContent` branch `else if !showDocumentGrid` collapses to preview only. Done. |
| **#928** | PDF pages: surface loupe/magnifier tools | `PDFPageWithToolbar.swift` has full loupe controls: toggle button, lock, magnification slider (1–8x), `PDFLoupeOverlay` wired. Done. |
| **#747** | Inspector: text selection persists when switching documents | `AttributedTextEditor.applyContentIfNeeded` (line 222–240): `isContentSwap = textView.string != text.string`; when true calls `setSelectedRange(NSRange(location:0, length:0))`. Done. |
| **#711** | Sidebar drag: unify icon/text + row-body drag via .draggable Transferable | `SidebarItemRow.swift` uses `SidebarDragID: Transferable`; `itemLabel` uses `.allowsHitTesting(false)` on both `Image` and `Text`; row body has `.textSelection(.disabled)`. `unifiedRow` applies `.draggable(SidebarDragID(...))` at ForEach level. Done. |
| **#994** | LazyVStack + cap-N + sheet for Entities/Claims | `EntityDetailView+Claims.swift::claimsSection`: `LazyVStack`, cap=10, `showAllClaims` toggle with "Show all N claims" button. Done for claims. |

**Count: 8 safe-to-close (but #1229 and #994 are PARTIAL — see below).**

---

## PARTIAL — Needs clarification or remaining work before closing

| # | Title | Done part | Missing part |
|---|-------|-----------|--------------|
| **#1229** | Inspector UX: toggle in toolbar + filterable attribute strip | Toggle in toolbar done (sidebar.right button, ⌘⌥I) | Filterable attribute strip not found in code. `DisplayAttributesStrip` renders fixed rows (Status/Kind/Ingest/Path/Created/Modified) with no filter/select/artifacts. Part 2 of 3 from the issue is open. |
| **#994** | LazyVStack + cap-N + sheet | Claims section done with LazyVStack+cap | Entities chip strip in the Library inspector (`DocumentInspector.swift` KG tab) still uses a plain `ForEach` — no cap-N or sheet found for the entity chip strip. |
| **#1215** | Reliable toolbar + View menu controls for pane visibility/view modes | Inspector toggle + document-grid toggle exist in toolbar; InspectorButton in ViewMenuCommands; layout/view picker in toolbar | View menu lacks explicit Show/Hide items for "List view", "Preview view", "WebKit content view" as the issue describes. `ViewMenuCommands.body` has `LibraryLayoutSection`, `PreviewModeSection`, `InspectorButton` but not individual pane visibility toggles. Partial. |
| **#713** | Sidebar drag asymmetry: icon/name vs row-body | `.allowsHitTesting(false)` on label children is now in place (addresses the root cause diagnosis) | Daniel verified in testing that the asymmetry was NOT resolved. The issue body explicitly says the proposed fix did not work and the issue is open for continued diagnosis (NSOutlineView wrapper deferred to 0.0.3). |
| **#1199** | Inspector always visible as rightmost pane across all views | Inspector is shown/hidden by `showInspectorSidebar`; is a sibling HStack in the window-level layout | The issue asks for "never hidden, never replaced" — but a toggle still exists (the whole point of #1229 part 1 was to move the toggle). The comment in `mainToolbarContent` itself says: "NOTE: a true window-corner placement… is deferred — deferred to the #1199 window-layout rework." Not done. |
| **#746** | Inspector: bold formatting not persisting | `encodeArtifactContent` correctly checks `hasFormatting` including `.paragraphStyle` and emits RTF | Backend `page_content` is a plain TEXT field. `saveArtifact`/`savePageContent` pass a content string that is RTF source — but whether the backend round-trips it correctly on reload depends on `Document.page_content` field semantics which the issue flags as unverified. Need a live test to confirm; code path looks correct but the issue describes a storage-round-trip concern. |

---

## OPEN — Not implemented

| # | Title | Evidence of absence |
|---|-------|---------------------|
| **#1345** | GET /api/documents/{id}/children 404 during folder catalogue | `get_children` raises 404 when `doc_id` is not found via `db.get(Document, doc_id)`. The `doc:` prefix IDs are the stored ID format — if a `doc:`-prefixed id is passed percent-encoded and the DB lookup fails, 404 fires. Root cause undiagnosed. Open. |
| **#1265** | Image/page editing UX: prev/next between images + rubber-band region select | Prev/next nav in `ImageEditorView.navigationCluster` is present for images. Rubber-band marquee region select: `ImageMarqueeOverlay.swift` exists but region-select-then-batch-apply-across-files is not wired. Open for rubber-band+batch. |
| **#1253** | Bidirectional scroll sync WebKit transcript ↔ native PDF | `DocumentScrollSyncState` and `scrollSyncScript` exist (feature-flagged under `isPdfScrollGridSyncEnabled`). Flag is `false` by default (`@AppStorage … = false`). Not shipped to users — feature is gated off. Open/PARTIAL gated. |
| **#1194** | Book reading view: typeset document with inline claim highlights | No `BookView`, `BookReadingView`, or typeset-prose view found anywhere in the Swift codebase. Not started. |
| **#1072** | Audit SwiftUI codebase for logic that belongs in backend | No `agent-work/proposals/swiftui-logic-audit.md` file found (checked proposals dir). The audit was never written. Open. |
| **#973** | Book-aware page numbering + chapter markers (Apple Intelligence) | No `detect_book_structure` workflow tool found in `fichero-engine`. No `BookStructure` model found. Not started. |
| **#719** | Eager-prefetch thumbnails for currently-selected folder | Zero hits for "prefetch thumbnail" in the codebase. `LibraryImageView` loads on-demand only. Not implemented. |
| **#712** | Remove center preview pane; folder inspector when nothing selected | `FolderContentsGrid` still renders as the center pane for folders (confirmed in `previewContent` — `if doc.docType == .folder { FolderContentsGrid(...) }`). Three-pane layout unchanged. Not done. |
| **#710** | Test: ArtifactPanel RTF encode/decode round-trip | No RTF round-trip test found in `fichero-engine/tests` or `fichero/fichero-tests`. Open. |
| **#706** | Inspector V2 phase 3: user-defined attribute schema | Not found. Open. |
| **#644** | Sidebar: replace 'Library' text header with clickable icon+name row | `SidebarItem.libraryHeader` creates the library group header but it is a `libraryHeader` typed item rendered as a disclosure group, not a "clickable icon + name row showing root-level files." The issue asks for a specific UX change not implemented. Open. |
| **#625** | JSON files show no preview in document grid/inspector | `previewContent` falls through to `QuickLookDownloadView` for non-image, non-PDF types — this includes JSON. QuickLook on macOS can preview JSON but depends on the system QuickLook plugin. No custom JSON preview. The issue is about grid cells showing no preview for JSON — code goes to generic QuickLook path. Likely still open; no JSON-specific preview renderer found. |
| **#598** | Sidebar drag-drop: drops land on currently-selected row not cursor target | While #711 fixed the drag-payload asymmetry, #598 describes a separate routing bug (drops always land on selected row). The issue is still open and #711 was filed as a follow-up to #598, not its fix. |
| **#593** | Preview-style swipe navigation across folders | No swipe gesture across folder items found in Library views. Not implemented. |
| **#588** | PDFView: trackpad pinch-zoom + prevent parent gesture interception | `PDFPageView` uses `PDFPageWithToolbar` with a `PDFZoomController`. There is no `NSMagnificationGestureRecognizer` on the `PDFPageView` path (only on `ImageWithCursorTracking`). Open. |
| **#585** | Sidebar structural cleanup: split SidebarItemRow, consolidate state managers | `SidebarItemRow` is already split (`.swift`, `+Label`, `+Rename`, `+Helpers`, `+DropHandlers`). But `SidebarStateManagers.swift` still exists as a separate file. Partial cleanup done; issue may be stale depending on intent. Treat as PARTIAL. |
| **#584** | Sidebar accessibility pass | No accessibility audit found. `SidebarItemRow.body` does add `.accessibilityLabel`, `.accessibilityHint`, `.accessibilityValue`. Some coverage exists but no systematic audit done. |
| **#583** | Sidebar test coverage sprint | `fichero-engine/tests/unit/` has `SidebarItemTests.swift`, `DragDropTests.swift`. Some tests exist but whether the "top 10 missing unit tests" from the issue were written is unclear. |
| **#580** | Restore between-row drops with safer mechanism | `SidebarItemRow+DropHandlers.swift` has drop handlers. Whether between-row insertion is fully working needs a live test. Code exists; not clearly resolved. |
| **#579** | PDF annotations as first-class Artifacts | No PDF annotation artifact pipeline found. Open. |
| **#572** | Add sort_order to Document; wire sidebar reorder via drag-drop | `sort_order` field referenced in `SidebarItem` (`sortOrder: 0`). Backend `reorder_documents` endpoint exists. But drag-to-reorder in the sidebar is not clearly wired end-to-end. PARTIAL. |
| **#355** | Bottom magnifier: zoom limit prevents zooming below 100px | `MagnifierPanel.swift` exists. Whether the zoom-limit bug is fixed requires live testing. No code fix comment found. Open. |
| **#354** | Sidebar: right sidebar closes when clicking at the top | No specific fix found. `showInspectorSidebar` toggle logic is straightforward. Open — likely still reproducible. |
| **#330** | Icon view: remember column width, fix first-run jump, load preview on selection | `@SceneStorage` for various view state exists but no specific column-width memory or first-run-jump fix comment found. Open. |
| **#323** | Tab title should show current view name and icon | `toolbarTitle` computed property in `ContentView+State.swift` provides the window title string. `.navigationTitle(toolbarTitle)` is set. But the issue asks for a *tab* title with icon — macOS tab titles are set via `.navigationTitle` which this does use. May be done. Needs live verification. PARTIAL. |

---

## Summary counts

| Verdict | Count | Issues |
|---------|-------|--------|
| DONE — safe to close | 8 | #1261, #1186, #616, #928, #747, #711, #994 (claims only), and #616 |
| PARTIAL — needs remaining work or live test | 7 | #1229, #994, #1215, #713, #1199, #746, #585, #323, #572, #580 |
| OPEN — not started or clearly not done | 22 | #1345, #1265, #1253, #1194, #1072, #973, #719, #712, #710, #706, #644, #625, #598, #593, #588, #584, #583, #579, #355, #354, #330 |

*(Partial count is 10 when counting sub-items; the table above shows all partial items.)*

---

## Recommended immediate closes (high confidence)

Close these 7 without further debate — code evidence is unambiguous:

**#1261, #1186, #616, #928, #747, #711**

For **#994** — close with a follow-up note: claims section is done; entity chip strip cap+sheet is not. Either close and file a new issue for the entity strip, or keep open scoped to that remaining piece.

---

## Notes on recently-reopened issues

- **#1253** — scroll sync code exists but is feature-flagged off by default. Reopen is correct; needs flag enabled + verification.
- **#1229** — toggle moved to toolbar (done); attribute strip filter is NOT done. Reopen for part 2 is correct.
- **#1199** — inspector is a HStack sibling but is still hideable/toggleable. The "always visible" acceptance criterion is explicitly deferred in code comments to the #1199 window-layout rework. Reopen correct.
- **#1186** — fully implemented (⌘[ / ⌘] back/forward). Should be re-closed.
- **#994** — claims section done; entity chip strip cap not done. Partial reopen is valid.
- **#747** — text selection reset implemented in `applyContentIfNeeded`. Should be re-closed.
- **#746** — RTF encode/decode path looks correct; storage-layer round-trip needs live confirmation.
- **#625** — JSON falls through to QuickLook; no custom renderer. Reopen correct.
- **#616** — fully implemented. Should be re-closed.
