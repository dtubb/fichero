# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Entity Platform — SwiftUI implementation of five-pane reading layout, KG inspector modes, bidirectional sync.

## In Progress

Nothing. All loops stopped. Working interactively with Claude directly.

## Next Session — Start Here

1. **Start with #1188** — `PDFReadingView` + `selectedPageIndex` skeleton already committed (`ecd25614`). Needs: editable `PageContentPane` with auto-save wired to the existing `savePageContent()` in DocumentInspector, plus claim highlighting. Read `fichero/fichero/Views/Library/PDFThumbnailView.swift:637` and `fichero/fichero/Views/ContentView+ViewBuilders.swift`.
2. **Then #1197** — bidirectional 3-pane sync via `ClaimFocusState` at window level
3. **Then #1196** — page-scoped KG graph in Map tab
4. **Do NOT use cheap OpenRouter cascade for SwiftUI/backend work** — run Claude directly (interactive or `--agent claude` loop). See MEMORY.md cascade model selection.
5. **Build gate**: swiftlint + xcodebuild + RunAllTests before marking any issue done.

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
