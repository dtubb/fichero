## #2810 — compact reader push flow + #2864 compact error fold — 2026-07-03, f_fichero_claude_swiftui

Commit-only, NOT built (manager gates). Two slices; one was already implemented, one was a real gap I fixed.

### Slice 1 — compact reader push flow: ALREADY IMPLEMENTED (verified, no code)
The "library list → reader as a NavigationStack push, macOS split unchanged" flow already
exists (#2551/#2666):
- `ContentView+ViewBuilders.swift:548 compactLibraryReaderStack` — `NavigationStack` with the
  library/search LIST as root; `.navigationDestination(item: $pushedReaderDocument)` pushes the
  reader (the same `previewView` EditorView the regular pane uses). Back/pop clears the selection.
- Gated compact-only by `usesCompactReaderFlow` (:503 → `shouldUseCompactNavigationFlow`), so
  macOS/iPad-regular keep the unchanged split (`centerContent` else-chain). Push fires reliably
  off real `@State` (#2666), not a computed binding.
Per iterate-never-replace I did NOT rebuild it. If Daniel wants explicit stage-to-stage edge
swiping (list↔preview↔reader), that's the deferred `ponytail:`-marked follow-up at :560.

### Slice 2 — #2864 compact connection error fold: FIXED (commit)
Gap: on iOS the root routed BOTH "not paired yet" AND "paired but unreachable/authBroken" to the
QR-pairing `RemoteConnectionSetupView` (via the old `needsConnectionSetup = !isBackendRunning ||
…unpaired`). A dropped/again-rejected connection therefore bounced to a first-run *setup* prompt
(and a local backend going down showed a QR-setup screen, which makes no sense).

Fix (`FicheroApp_iOS.swift` `FicheroSharedPlatformRoot` only): split the gate —
- `needsInitialConnectionSetup` = `requiresExternalBackendConnection && !hasPairedLibraryPath`
  → `RemoteConnectionSetupView` (genuine first-run pairing).
- else `!appState.isBackendRunning` → `BackendConnectionView(appState:) { reconnect }` — the same
  diagnostic error view the macOS `BackendRootGate` and `DocumentTabView` already use, surfacing
  the #2864 `authBroken`/`backendDiagnosis` cause. Never blank, never the wrong setup prompt.

### Coordination
- Did NOT touch `EmbeddedBackendService` or `AppState` (opus-connection). The fold READS
  `appState` state and REUSES the existing `BackendConnectionView` (which already runs on iOS via
  `DocumentTabView`); `backendService` resolves from the iOS root's existing
  `.environmentObject(backendService)` — I added no backend state and constructed no service.
- Did NOT touch Settings or sidebar-sharing (opus-features).
- ADJACENCY FLAG: the one edited file, `FicheroApp_iOS.swift`, is where opus-connection landed
  #2864. My change is isolated to the root gate's branch structure (rename one computed property +
  add one branch reusing their component), so a merge is trivial — but flag for the manager to
  sequence if opus-connection is still in that file.

### Not built
Machine-load rule respected — no xcodebuild. Verified by reading: `BackendConnectionView` init
(`appState` + optional `onConnected`) matches; it already renders on iOS via `DocumentTabView`;
`backendService` is in the iOS environment; `needsConnectionSetup` had only the two refs updated.
NOT pushed.
