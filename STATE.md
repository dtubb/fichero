# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Entity Platform — SwiftUI implementation of five-pane reading layout, KG inspector modes, bidirectional sync, plus repository lint debt cleanup.

## In Progress

Nothing. All loops stopped. Working interactively with Claude directly.

## Next Session — Start Here

1. **Work through the remaining SwiftLint warnings in batches**. The current gate passes, but the repo still has pre-existing warnings in `WorkflowStore.swift`, `AISettingsView.swift`, `SidebarItemRow.swift`, `ContentView+Actions.swift`, `PDFThumbnailView.swift`, `DocumentInspector.swift`, `EntityDetailView.swift`, `ClaimSummaryCardView.swift`, `SearchResultsDisplay.swift`, `WorkflowEditor.swift`, `ViewMenuCommands.swift`, `EmbeddedBackendService.swift`, `APIClient.swift`, and a few `OntologyBrowser` files.
2. **Keep commits narrow**. Fix a batch of related warnings, rerun `bash scripts/verify_all.sh`, then commit that batch before moving to the next file cluster.
3. **Then resume feature issues**. After the lint backlog is reduced, continue with `#1197` bidirectional 3-pane sync via `ClaimFocusState`, then `#1196` page-scoped KG graph in Map tab.
4. **Do NOT use cheap OpenRouter cascade for SwiftUI/backend work** — run Claude directly (interactive or `--agent claude` loop). See MEMORY.md cascade model selection.
5. **Build gate**: swiftlint + xcodebuild + RunAllTests before marking any issue done.

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
