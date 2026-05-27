# opus lane — status

## 2026-05-26 — reading-surface bug sweep (f_opus, Opus 4.7)
Committed to `opus` (NOT merged — manager reviews+merges; green-before-merge):
- **#1230** `4297740c` — FicheroUITests XCUITest target + launch & view-mode smoke tests. **HELD: keep issue OPEN.** Target builds+signs; `testLaunch` passes, but `testViewModeRailIsPresentAndSwitches` fails (`viewMode-List` not found) and the suite needs a one-time macOS automation TCC grant (now grantable in the Xcode-GUI/MCP context — see local BLOCK.md). Flows 2–4 deferred to #1242.
- **#1247** `4a4ad3cd` — blank PDF on page-click. `ContentView.detailPDFPath` returned a stale `pdf_path` (no existence check) → `PDFView` blank. Now resolves only to an on-disk parent PDF, else falls through (mirrors `EditorView.resolvedParentPDFPath`).
- **#1245** `d9ec347d` — Page Content panel: always-expanded (no DisclosureGroup) + `.clipped()` so the AppKit editor stops overdrawing the attribute strip.
- **#1243** `deae1172` — content-list pane min clamped to `ContentView.contentListMinWidth = 240` (view-mode rail width) so rows/rail can't clip.

Key files touched (reading surface): `Views/Library/DocumentInspector.swift` (ArtifactPanel, DisplayAttributesStrip), `Views/ContentView+ReadingLayout.swift` (detailPDFPath/resolvedParentPDFPath), `Views/ContentView.swift` + `ContentView+ViewBuilders.swift` (pane widths), `Views/Library/PDFPageView.swift`, `Services/UITestSupport.swift`.

Swift gotchas for the merger:
- SourceKit shows phantom "Cannot find type" errors for SPM/cross-file symbols — ignore; only `xcodebuild` is authoritative.
- The parent-PDF resolver is duplicated 3× (detailPDFPath, EditorView, LibraryListRow) and has drifted — worth a shared-helper follow-up.
- Three-leg run per commit: swiftlint 0 + Xcode build OK + unit suite TEST SUCCEEDED. I skipped `CrossLanguageGateTests`/`AppEngineContractTests` (spawn a backend → pollute dev library; no view coverage).
- Active Xcode scheme is now `FicheroUITests` (opus = windowtab3); run unit tests via `xcodebuild test -scheme Fichero`.

Queue remaining (NOT started): #1244 (+extended blurb removal), #1246 (+value highlighting), #1253 (scroll sync), #1230 flow-5 debug.
