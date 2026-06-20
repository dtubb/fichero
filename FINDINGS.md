# Lane B — iOS multiple libraries + swipe navigation — FINDINGS

Branch `worker/ios-shell-nav`. Do NOT push. Manager integrates + Daniel builds.

## What the shell already had (no rebuild needed — iterate)
- iOS entry: `FicheroApp_iOS.swift` → pairs with Mac (QR) → `adoptPairedRemoteLibrary()`
  creates ONE remote `LibraryReference` (the paired path) → `FicheroSharedPlatformRoot`
  → `LibraryWorkspaceRoot(library:)` → `DocumentTabView` → `ContentView` (NavigationSplitView).
- Registry plumbing already exists: `KnownLibraryRegistryStore.shared` reads `/registry`
  and is refreshed on connect. It just had no iOS UI.
- Switching the whole app to another library = set `LibraryManager.currentLibraryId`;
  `LibraryWorkspaceSelection.activeLibrary` re-roots the workspace, `.task(id:)` syncs
  `windowState.libraryId`. (Same mechanism Mac uses.)
- Compact adaptivity already in place: `ContentView.shouldUseSplittablePane` is false on
  compact (#2333 — SplittablePane is desktop/regular-width only), inspector becomes a
  detented `.sheet` on compact (`InspectorPlacement.adaptiveDefault`), and
  `availablePreviewModes` drops `.widescreen` on compact so a phone never renders the
  fixed multi-pane HSplit. NavigationSplitView collapses to a stack natively.

## What I changed
### Chunk 1 — Multiple libraries on iOS (#2394)
- `LibraryManager+Operations.swift`: added `switchToRemoteLibrary(path:displayName:)` —
  iOS-safe switch that reuses an already-open library at that path or creates a remote
  `LibraryReference` (no security scope, no local file-exists check), inserts it after
  Global, sets `currentLibraryId`, and schedules a load. Mirrors `adoptPairedRemoteLibrary`
  but for an arbitrary registry path with a fresh UUID.
- NEW `fichero/Views/Library/iOSLibraryPickerMenu.swift` — a Menu listing the known-library
  registry (+ the active library), with a checkmark on the current one; tap switches via
  `switchToRemoteLibrary`. Refreshes the registry on appear.
- `LibraryWorkspaceRoot.swift` (iOS branch): surfaced the picker as a `.topBarLeading`
  toolbar Menu so it's the first thing reachable on every iOS screen — the "library list".

### Chunk 2 — Compact stack/swipe nav (#2329 / #2334 / #2100)
- `ContentView`: added `preferredCompactColumn` policy + binding on the NavigationSplitView
  so compact reliably lands on the content/detail column (the document list → reader) and
  the sidebar (folder tree + library picker) stays one swipe away. Pure additive arg to the
  existing split view — no new modifier in the type-check-sensitive chain.

## Needs an Xcode build to confirm (I did NOT run xcodebuild — per brief)
- New file `iOSLibraryPickerMenu.swift` must be registered: `ruby scripts/add-swift-file.rb
  fichero/fichero/Views/Library/iOSLibraryPickerMenu.swift` (done by me; manager re-verify).
- Verify the `.topBarLeading` Menu renders in the iOS nav bar alongside the existing
  Capture-Queue toolbar item.
- Verify `NavigationSplitView(columnVisibility:preferredCompactColumn:sidebar:detail:)`
  compiles against the current min-26 SDK.

## Mac-regression risk
- `switchToRemoteLibrary` is cross-platform but only called from the iOS picker.
- `preferredCompactColumn` is inert on macOS (split view never collapses); the binding just
  rides along. Policy returns `.detail` only for compact, `.automatic`-equivalent otherwise.
- No changes to SplittablePane, the Mac sidebar, or the desktop reading workspace.

## New files (manager: register with add-swift-file.rb)
- fichero/fichero/Views/Library/iOSLibraryPickerMenu.swift
