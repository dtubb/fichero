# Sidebar Code Review — Hookup Audit (2026-04-17)

Scope: `fichero-swiftui/fichero-swiftui/Views/Sidebar/*.swift` and `Components/*.swift`.
Skipped: `Modes/` (transitional). Review-only — no changes applied.

## 1. Hookup Gaps (declared but never called / only from disabled code)

- **[HIGH] `handleInsertBetweenChildren` is completely orphaned.**
  `SidebarItemRow+DropHandlers.swift:67` — defined, ~60 lines of real logic (file + internal-drag routing, plus `moveItemToFolder` fallback). Grep finds **zero call sites** anywhere in the app. Its only in-code reference is inside the docs/plan. Every `.onInsert(of:)` the function was meant to back has been explicitly disabled with the "HomogeneousCollection index -1" comment (`SidebarItemRow.swift:192-202`, `SidebarView+ViewComponents.swift:319-324`). Until #580 lands the custom `DropDelegate`, this is dead code plus two dead private helpers (`loadURL`, `loadString` at lines 126 and 140 in the same file — neither is used by any live path because `handleProvidersDrop` uses its own `Self.loadURL` defined elsewhere… wait — see below).

- **[HIGH] Two different `loadURL` statics exist, only one is live.**
  `SidebarItemRow+DropHandlers.swift:126` (`private static func loadURL`) and `SidebarItemRow+DropHandlers.swift:140` (`private static func loadString`) are only called from `handleInsertBetweenChildren`. The live `handleProvidersDrop` path at line 37 also says `try? await Self.loadURL(from: provider)` — this resolves to the same static at line 126 (both statics are on `SidebarItemRow`). So `loadURL` IS used; `loadString` is **not**. Remove `loadString` along with `handleInsertBetweenChildren`.

- **[HIGH] `handleLibraryRootInsert` in `SidebarView+DropHandlers.swift:18` is orphaned.**
  Grep for the function name across the entire repo returns only the definition. The file's own doc-comment says it's the handler for `.onInsert(of: [.fileURL])` on the top-level documents ForEach — and that surface is disabled (same macOS 14 crash). The private helper `loadURLForRootInsert` at line 51 dies with it. That is essentially the whole file (64 LOC). The 16-line file size of `SidebarView+Environment.swift` isn't the suspicious one — `SidebarView+DropHandlers.swift` is.

- **[HIGH] `handleDropOntoItem` in `SidebarItemRow+DropHandlers.swift:297` has no callers.**
  Only returns `false` and logs. No production code references it. Safe to delete.

- **[HIGH] `SidebarServices` / `SidebarServicesKey` / `.sidebarServices` in `SidebarEnvironment.swift` are unused.**
  Grep for any of those three identifiers returns only the definitions (`SidebarEnvironment.swift:11,16,25`). The comment claims it solves the "9-parameter problem in SidebarItemRow" — but `SidebarItemRow` still takes the services individually via `libraryManager.getLibrary(...)`. The environment key is never set or read by anything. Entire 42-line file is dead.

- **[MED] `sidebarToolbar(config:)` / `SidebarToolbarConfig` (`SidebarViewExtensions.swift:137,147`) are unused.**
  No call sites anywhere — the app uses `SidebarBottomToolbar` (a struct, not the `.toolbar` modifier) built inside `sidebarContent`. Remove both the config struct and the `View` extension.

- **[MED] `sidebarCacheMonitoring(config:)` / `SidebarCacheMonitoringConfig` (`SidebarViewExtensions.swift:206,218`) are unused.**
  Cache monitoring now flows through `setupServiceObservers()` (Combine `$publishers`) in `Components/SidebarObservers.swift`. The `.onChange` version in the extension is stale from a previous architecture and never mounted on any view. ~40 LOC of dead code.

- **[MED] `selectedItemLibrary` in `SidebarView+Helpers.swift:18` has two callers but one is questionable.**
  Used in `SidebarActions.importFiles` and `SidebarCreationHandlers.createFolder`. Correct and live — noting here only because the design choice to derive "target library for import" from the sidebar-selected item (rather than the window's current library) is subtle. If the user has no selection the fallback is global library, which matches Finder semantics.

- **[LOW] `automationRefresh` environment key in `SidebarView+Environment.swift:12` has no live reads.**
  Grep for `automationRefresh` returns only the definition and a comment. Some editor somewhere was supposed to call this to trigger `loadAutomationData()`. Either wire it up from the automation editors or delete.

- **[LOW] `SidebarConstants` has stale design tokens.**
  `itemLeadingPadding`, `sectionHeaderVerticalPadding`, `sectionHeaderHorizontalPadding`, `dropTargetOpacity`, `dropTargetNonFolderOpacity`, `sectionDropTargetOpacity` — grep finds none of these referenced. Only `minimumWidth`, `cornerRadius`, and `maxNameLength` are live. Prune.

- **[LOW] `onCreateChatWithDocuments` callback declared on `SidebarView.swift:28` and stored (`self.onCreateChatWithDocuments = …`) but never invoked from inside the sidebar.**
  No grep hit inside the sidebar dir for `onCreateChatWithDocuments?(` or `.onCreateChatWithDocuments(`. Either a disabled chat-creation-from-drop flow, or an old entry point for ContentView.

## 2. Disabled Code Paths

- **[HIGH] Every `.onInsert(of:)` surface is disabled in the comment but still referenced by orphaned handlers.**
  The three in-code comments explicitly say disabled (`SidebarItemRow.swift:192`, `SidebarView+ViewComponents.swift:319`, `SidebarView+DropHandlers.swift:12`). Confirmed via `grep '\\.onInsert\\(of:'` — zero live call sites in production. This means `handleInsertBetweenChildren`, `handleLibraryRootInsert`, and their private loaders are all dead. See Section 1.

- **[MED] `acceptsFileInsert` parameter on `unifiedRows` at `SidebarView+ViewComponents.swift:292` does nothing.**
  Passed as `sectionKey == "library"` at line 344, received but never read inside the function body. It was presumably the flag that used to gate `.onInsert` — with the insert disabled, the parameter is vestigial. Delete the parameter and the callsite.

## 3. State Cache Drift

- **[MED] `handleImportedFiles` calls `rebuildCaches()` manually (`SidebarActions.swift:37`).**
  The Combine observer on `documentStore.$collections` (`SidebarObservers.swift:20`) already rebuilds on collection mutation. Manual rebuild is fine but means the cache gets rebuilt **twice** — once by the observer, once here. Harmless perf only; flagging for cleanup.

- **[MED] `performDelete` in `SidebarActions.swift:95` also calls `rebuildCaches()` manually.**
  Same double-rebuild pattern. `documentStore.deleteDocument` mutates `$collections`, which fires the observer. Redundant.

- **[HIGH] Chain / schedule / trigger caches may drift after rename.**
  `SidebarItemRow+Rename.swift:95-110` mutates `chain.name` and calls `chainService.updateChain(chain)`, and similarly for schedules/triggers via `automationService.updateSchedule` — but **there is no Combine observer on `automationService.$schedules` / `$triggers`** in `setupServiceObservers()` (lines 17-55). Only document-store / search / conversation / workflow / chain (line 49) are observed. A rename on a schedule or trigger updates the backend but the sidebar `@State var schedules/triggers` isn't refreshed until the user leaves and re-enters automation mode (the `onChange(of: sidebarMode)` at `SidebarView.swift:166`). Symptom: "I renamed it but the sidebar still shows the old name until I click away." — Daniel may have seen this.

- **[MED] `cachedLibraryHeaders` not invalidated on `FeatureManager` flag toggles.**
  Sections are gated by `FeatureManager.shared.is*Enabled` inside `unifiedLibrarySection` (`SidebarView+ViewComponents.swift:83,86,92` etc.). `FeatureManager` is `@ObservedObject` somewhere else, but `SidebarView` doesn't observe it — so flipping a feature flag at runtime doesn't trigger `rebuildCaches()`. Cache still has stale items from the disabled feature until the next service mutation.

- **[MED] `setupServiceObservers()` clears `cancellables` but not `cachedLibraryHeaders`.**
  On `onChange(of: libraryManager.openLibraries.count)` (`SidebarView.swift:159`) we call `rebuildCaches()` then `setupServiceObservers()`. Correct. But there's a tiny window where the cache has the removed library's data until `rebuildCaches` runs. Minor.

## 4. Selection Tracking

- **[HIGH] Creation handlers mutate `selectedItemId` as a side-effect.**
  `SidebarCreationHandlers.swift:30, 82, 127, 161, 206` each assign `selectedItemId = ...`. That's intentional (select the just-created item). Concern: a race where the observer-triggered `rebuildCaches` hasn't inserted the new item into `cachedLibraryHeaders` yet — `handleSelection` in `onChange(of: selectedItemId)` then calls `findItemById` which returns nil. Not obviously a defect (the mode/viewMode is set explicitly in the creation handler before the assignment) but worth knowing.

- **[HIGH] `handleUnifiedRowTap` unconditionally writes `selectedItemId = item.id` (lines 384, 390).**
  This fires every single tap, including re-taps of the already-selected row. The `onChange(of: selectedItemId)` handler short-circuits via `lastHandledSelectionId` (`SidebarView.swift:144-147`), but `selectedActivityItemIds.removeAll()` at line 389 still fires on every non-activity tap even when the current selection IS activity — that's fine, but a multi-select activity drag into a non-activity area would clear the selection. Confirm intended.

- **[MED] `performDelete` sets `selectedItemId = nil` (`SidebarActions.swift:96`).**
  Only called from the confirmation alert flow, so the user is clearly deleting. Fine. But it's done before the observer rebuilds caches — so the UI momentarily has nothing selected, then refreshes. Cosmetic.

- **[LOW] Drop handlers do NOT mutate `selectedItemId`.**
  Grep of `SidebarItemRow+DropHandlers.swift` + `SidebarItemRow+Helpers.swift` for `selectedItemId` returns zero hits — good. #598's symptom ("drops go to current selection") is NOT caused by drop code writing to `selectedItemId`. If the symptom is real, the path is elsewhere — likely SwiftUI's `.dropDestination` associating with the wrong row due to the overlapping draggable regions, not a selection mutation. Flagging as clean.

- **[MED] `renameDocument` and friends don't touch selection.**
  Rename flow in `SidebarItemRow+Rename.swift` is clean — no selection mutation. Good.

## 5. `bodyContent` Branch Symmetry

Three branches in `SidebarItemRow.swift:187-242`:

- **[MED] Branch A (has-children) wraps `fullWidthLabel` in a `DisclosureGroup` and puts modifiers on the LABEL CLOSURE.**
  The `.draggable`, `.dropDestination`, `.onDrop`, `.contextMenu` all attach to `fullWidthLabel` **inside** the DisclosureGroup label. Drops on the chevron/indent area specifically will NOT hit these modifiers because the chevron is a sibling of the label inside the DisclosureGroup, not a child of the labeled view. The `sidebarDropHighlight` overlay on the OUTER body compensates visually, but the actual drop hit-testing is label-only. Possible cause of "drop on folder row doesn't fire" reports.

- **[MED] Branch B (empty folder) and Branch C (leaf) attach the same four modifiers directly to `fullWidthLabel` — no DisclosureGroup wrap.**
  Symmetric to each other. Inconsistent with branch A in that the whole row is the drop target (no chevron to fight with).

- **[MED] Branch C uses `handleDropBesideItem` and passes `parentFolderItem(of: item)` to `handleProvidersDrop`, but branches A and B use `handleDropIntoFolder` + `targetFolder: item`.**
  That asymmetry is intentional (file-drop-onto-leaf means "import into leaf's parent"), but it means an internal drag-of-text-item drop onto a leaf routes through `handleDropBesideItem` → `moveItemToFolder` (documents-only). Dragging a saved search ID onto a non-folder saved-search leaf would fall through to `moveItemToFolder` and silently fail (`documentStore.moveDocument` with a non-doc ID). Not a Daniel bug yet, but a cross-section drop-beside hole.

- **[LOW] Branch A's `DisclosureGroup { ... }` content closure (`childrenList(children)`) uses `.onTapGesture` to call `onItemTapped` (line 258), but branches B/C rely on the OUTER `.onTapGesture` in `unifiedRows` (`SidebarView+ViewComponents.swift:308-311`).**
  Two different tap paths; the inner one recurses via `SidebarItemRow(…, onItemTapped: onItemTapped)`. Works, but the gesture layering is tricky — double-click-to-rename (Step 8 change in `SidebarItemRow+Label.swift:19`) only lives on the `Text`, not on the row, so nested-child double-click may not rename if the hit misses the Text.

## 6. pbxproj

- **[PASS] All sidebar files present in pbxproj.** Verified via grep: `SidebarItemRow+Label.swift`, `+DropHandlers.swift`, `+Helpers.swift`, `+Rename.swift`, `SidebarView+*`, `SidebarSectionHeader.swift`, `SidebarCreationHandlers.swift`, `SidebarActions.swift`, `SidebarObservers.swift`, `SidebarModeBar.swift`, `SidebarModeIcon.swift` — all have PBXBuildFile + PBXFileReference + group + Sources-build-phase entries. No MEMORY.md:11 violation in this directory.

## 7. Threading / Concurrency

- **[HIGH] `NSItemProvider.loadObject` completions in `SidebarItemRow+DropHandlers.swift:128` and `:142` do not hop to MainActor.**
  `withCheckedThrowingContinuation` resumes on whatever thread the completion fires on — probably a background queue. `handleProvidersDrop` calls the awaited result inside a `Task` (line 34), but the Task is inherited-actor (non-Sendable closure on an isolated `SidebarItemRow` struct). Works today because only URLs come back, but any side-effect downstream (e.g. logging from `sidebarRowLogger`) touches OSLog which is fine — `documentStore.refresh()` is `@MainActor`, compiler will warn if misaligned. Run `swiftc -strict-concurrency=complete` to verify.

- **[MED] `AutomationRefreshKey.defaultValue` is `nonisolated(unsafe)` (`SidebarView+Environment.swift:7`).**
  OK for a `nil` default, but any caller setting this must guarantee main-actor reads. Since the key is unused (Section 1), moot — but if revived, double-check.

- **[LOW] `setDropTargeted` mutates `@State var isDropTargeted` from the dropDestination closure.**
  SwiftUI `.dropDestination` fires on MainActor, so this is fine — flagging only because the same pattern elsewhere in the app has bit people.

## 8. Code Smells / Complex Expressions

- **[MED] `SidebarSectionHeader.swift:44-48`: conditional Text within HStack.** The SourceKit timeout Daniel hit was on this very file. The `if library.id == LibraryManager.globalLibraryId { Text("Global") } else { Text(library.displayName) }` compiles but the whole HStack with 5 conditional branches (`isCurrentLibrary` checkmark, globalId text, itemCount text) is exactly the expression-type-checker cliff. Hoist into `@ViewBuilder private var headerContent`.

- **[MED] `unifiedLibrarySection` (`SidebarView+ViewComponents.swift:63`) — the big one with `swiftlint:disable`.** The function builds 7 `let` arrays via nested `.filter { if case ... }` and then branches on `library.id == globalLibraryId` to choose Section vs DisclosureGroup, and **each branch re-declares the same onFileDrop closure inline** (lines 150-173 and 200-223). 23 lines of `onFileDrop` logic literally duplicated. Factor `makeHeaderDropClosure(library:) -> ([URL]) -> Bool` and call it once; the function body drops under the 100-line lint threshold naturally.

- **[MED] `handleSelection` in `SidebarView+SelectionHandling.swift` — the two `swiftlint:disable` overrides (cyclomatic + function body length).** Nested switch on `item.itemType` → switch on `item.category`. Extract the folder-category sub-switch into a helper `modeForCategoryFolder(_:)` returning `(SidebarMode, AppViewMode)`.

- **[LOW] `chain-\(newChain.id)` at `SidebarCreationHandlers.swift:161`.** Inline comment says "Match the tag format in WorkflowsSidebarContent" — but every other creation handler in the same file produces `chain:\(…)` / `workflow:\(…)` / `search:\(…)` **colon-separated**. The hyphen form breaks `extractActualId(from:)` which splits on `:` — it will return the whole `"chain-…"` string unchanged, then `SidebarItemKind(prefixedId:)` classifies it as `.document` (because it has no colon). Any drop handling, rename, or lookup by this ID goes through the wrong path. Fix to `"chain:\(newChain.id)"` and verify WorkflowsSidebarContent (which is in `Modes/`, scheduled for removal) against the new format.

- **[LOW] Two separate `Logger` category strings: `"com.fichero.app"` (most files) and `"com.tubb.Fichero"` (`SidebarModeBar.swift:4`, `SidebarView+ViewComponents.swift:167` log subsystem).** Inconsistent subsystem makes filtering `log stream` painful. Pick one.

## Recommendations (ranked)

1. **Delete dead code in one PR.** `handleInsertBetweenChildren` + `handleLibraryRootInsert` + `handleDropOntoItem` + `loadString` + `SidebarServices`/`SidebarServicesKey` + `sidebarToolbar`/`SidebarToolbarConfig` + `sidebarCacheMonitoring`/`SidebarCacheMonitoringConfig` + unused `SidebarConstants` tokens + `acceptsFileInsert` parameter. ~200 LOC gone, zero runtime risk (all proven unreferenced), less noise when investigating the real drop flow. The `.onInsert` comments become inaccurate once the handlers are deleted — update them to reference #580 only.

2. **Fix `chain-\(id)` → `chain:\(id)` in `SidebarCreationHandlers.swift:161`.** Tiny change, high payoff — right now newly-created chains have the wrong ID shape and silently misroute through `SidebarItemKind` classification and `extractActualId`. Likely explains any "new chain doesn't respond to drag / rename" bug you'd see.

3. **Add Combine observers for `automationService.$schedules` and `$triggers`.** Parallel to the existing `$chains` observer. Removes the "rename doesn't refresh until you leave the mode" class of drift, and lets you remove the redundant manual `rebuildCaches()` in `handleImportedFiles` and `performDelete`.

4. **Refactor `unifiedLibrarySection` to stop duplicating the `onFileDrop` closure.** Cuts the function in half, removes the `swiftlint:disable`, makes the Section-vs-DisclosureGroup branch easy to read. Same patch can hoist `SidebarSectionHeader.swift:44`'s conditional Text into a sub-ViewBuilder to avoid the SourceKit timeout.

5. **Add explicit rejection for cross-section drops in `handleDropBesideItem`.** Today a saved-search ID dropped on a saved-search LEAF falls through to `moveItemToFolder` (documents-only) and silently fails. Compute `SidebarItemKind(prefixedId: itemID)` and compare against `SidebarItemKind` of `targetItem` before moving — mirror the check `handleDropIntoFolder` already does at line 269.
