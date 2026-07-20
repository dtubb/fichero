import SwiftUI

/// The window's root switch (#2864/#3107/startup-transport-ux S1). Real
/// content renders in every phase except `.setupNeeded`, so the real UI is
/// visible immediately instead of sitting behind a full-window splash while
/// the engine boots or recovers from a failure:
///
///   • `.setupNeeded`  → `setup` (first-run pairing on iOS; unused on macOS)
///   • everything else → `content` (the library window / workspace root),
///                        including `.starting` and every failure phase
///                        (`.portConflict` / `.authRejected` / `.unreachable`
///                        / `.failed`) — those are now surfaced as toolbar
///                        chrome (`EngineStatusToolbarItem`) rather than a
///                        window takeover. `BackendConnectionView` itself is
///                        NOT deleted: its status text + Retry / reset /
///                        port-conflict actions are reused inside that
///                        toolbar item's popover.
///
/// This is deliberately the *root* gate and switches on the single `phase` sum
/// type (not three ANDed booleans, #3107): there is exactly one authoritative
/// place that decides "is the backend usable", and the compiler forces every
/// phase to have a screen — no representable phase maps to "render nothing".
///
/// Both the macOS (`FicheroApp`) and iOS (`FicheroApp_iOS`) roots use this SAME
/// gate, replacing the divergent hand-rolled iOS session handling.
struct BackendRootGate<Content: View, Setup: View>: View {
    @Bindable var appState: AppState
    /// The ONE retry entry point (#3108): re-run the platform's connect
    /// sequence. macOS respawns the embedded engine, iOS re-adopts the paired
    /// remote host — and the launch task calls the SAME function, so the Retry
    /// button never re-implements `start()`. `setup()`'s `BackendConnectionView`
    /// fallback still receives it directly; `content()` no longer does (this
    /// gate never instantiates `BackendConnectionView` for the non-setup
    /// phases anymore), so the app root additionally publishes the same
    /// closure via `EnvironmentValues.engineRetry` for `EngineStatusToolbarItem`
    /// to read (see `FicheroApp.swift` / `FicheroApp_iOS.swift`).
    var onRetry: (@MainActor () async -> Void)?
    @ViewBuilder let setup: () -> Setup
    @ViewBuilder let content: () -> Content

    var body: some View {
        // `appState.engine` is the single owner; observe it via appState, which
        // re-publishes its phase changes (#3107).
        switch appState.engine.phase {
        case .setupNeeded:
            setup()
        case .ready, .starting, .portConflict, .authRejected, .unreachable, .failed:
            // The library content root (#3919/startup-transport-ux S1). Named so
            // a UI test can assert the app reached real content, rather than
            // inferring it from the absence of a full-window connection view —
            // content now renders during `.starting` and every failure phase
            // too; `EngineStatusToolbarItem` (in the toolbar `content()`
            // provides) is what surfaces those phases, not this gate.
            content()
                .accessibilityIdentifier("library.content.ready")
        }
    }
}
