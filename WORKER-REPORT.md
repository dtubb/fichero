## #2810 compact reader push flow — verify + title polish — 2026-07-03, f_fichero_claude_swiftui

Commit-only, NOT built (manager gates). Authored as Claude (Opus 4.8), no Daniel co-author.

### Core flow: ALREADY IMPLEMENTED (verified, not rebuilt)
The iPhone/iPad compact "library list → reader as a NavigationStack push" flow already ships
(#2551/#2666), and macOS/iPad-regular keep the unchanged split:
- `ContentView+ViewBuilders.swift:548 compactLibraryReaderStack` — `NavigationStack` with the
  library/search LIST as root; `.navigationDestination(item: $pushedReaderDocument)` pushes the
  reader (`previewView`, the same EditorView the regular content pane shows — no parallel reader).
  Push fires off real `@State` (#2666); Back/pop clears the selection so the list returns clean.
- Compact-only via `usesCompactReaderFlow` (:503 → `shouldUseCompactNavigationFlow`), so the
  macOS/iPad-regular split path (`centerContent` else-chain) is untouched.
Per iterate-never-replace I did NOT rebuild it. "preview" and "reader" are one unified
`previewView` by design (#2551), not two screens.

### Polish added (this commit)
Two real gaps in the existing stack, fixed additively:
- The NavigationStack ROOT (the compact library/search list) had NO `navigationTitle` — a blank
  bar, and the pushed reader's Back button showed a generic "Back". Added
  `.navigationTitle(toolbarTitle)` so the list is titled and Back names the section.
- The pushed reader used the default LARGE title. Added `.navigationBarTitleDisplayMode(.inline)`
  (a pushed detail should have a compact title bar). Both display-mode modifiers are
  `#if !os(macOS)`-guarded (UIKit-only; the view compiles on macOS even though it only renders on
  iOS). Matches the existing precedent at `ContentView.swift:917`.

### Deferred (unchanged, code-flagged at :560)
Explicit stage-to-stage edge-swipe paging (library↔preview↔reader) is the `ponytail:`-marked
follow-up in #2551 — deferred; EditorView already hosts `SwipeSiblingNavigator` for sibling
paging. Not built here (a new gesture is not safe to add blind without a build; flag for Daniel).

### Coordination
- Did NOT touch EmbeddedBackendService/AppState (opus-connection) or Settings/sidebar-sharing
  (opus-features). Change is confined to `compactLibraryReaderStack` (my #2810 area); the file's
  last edit was the merged #2811, so low collision risk.

### Not built
Machine-load rule respected. Verified by reading: `toolbarTitle` exists (ContentView+State:19);
`.navigationBarTitleDisplayMode` precedent at ContentView:917; `#if` guards compile-correct.
NOT pushed.
