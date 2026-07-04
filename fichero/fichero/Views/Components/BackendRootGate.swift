import SwiftUI

/// The window's root switch (#2864/#3107). Real content renders in exactly ONE
/// phase — `EngineSession.phase == .ready` — where the engine is running,
/// health-checks pass, and the token is accepted. Every other phase renders
/// explicit full-window UI, so the app can never present a blank window with
/// silent 401s behind the chrome:
///
///   • `.ready`        → `content` (the library window / workspace root)
///   • `.setupNeeded`  → `setup` (first-run pairing on iOS; unused on macOS)
///   • everything else → `BackendConnectionView` (splash while `.starting`,
///                        or the diagnosis + Retry for portConflict / authRejected
///                        / unreachable / failed)
///
/// This is deliberately the *root* gate and switches on the single `phase` sum
/// type (not three ANDed booleans, #3107): there is exactly one authoritative
/// place that decides "is the backend usable", and the compiler forces every
/// phase to have a screen — no representable phase maps to "render nothing".
///
/// Both the macOS (`FicheroApp`) and iOS (`FicheroApp_iOS`) roots use this SAME
/// gate, replacing the divergent hand-rolled iOS session handling.
struct BackendRootGate<Content: View, Setup: View>: View {
    @ObservedObject var appState: AppState
    /// Optional reconnect run when the connection view's Retry succeeds (iOS
    /// re-adopts its paired remote host). macOS restarts the embedded engine
    /// inside the connection view, so it passes nil.
    var onReconnect: (@MainActor () async -> Void)?
    @ViewBuilder let setup: () -> Setup
    @ViewBuilder let content: () -> Content

    var body: some View {
        // `appState.engine` is the single owner; observe it via appState, which
        // re-publishes its phase changes (#3107).
        switch appState.engine.phase {
        case .ready:
            content()
        case .setupNeeded:
            setup()
        case .starting, .portConflict, .authRejected, .unreachable, .failed:
            BackendConnectionView(appState: appState, onConnected: onReconnect)
        }
    }
}
