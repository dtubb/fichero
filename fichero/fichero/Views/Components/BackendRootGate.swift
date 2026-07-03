import SwiftUI

/// The window's root switch (#2864). Real content renders ONLY when the backend
/// is genuinely usable: the engine is running AND health-checks pass AND auth is
/// intact. Every other phase — starting, unreachable, authBroken, failed —
/// shows the full-window `BackendConnectionView` with its diagnosis, so the app
/// can never present a blank window with silent 401s behind the chrome.
///
/// This is deliberately the *root* gate rather than a per-tab one: a single
/// authoritative switch means no sidebar/toolbar chrome frames a broken state,
/// and there is exactly one place that decides "is the backend usable".
struct BackendRootGate<Content: View>: View {
    @ObservedObject var appState: AppState
    @ObservedObject var backendService: EmbeddedBackendService
    @ViewBuilder let content: () -> Content

    private var isUsable: Bool {
        backendService.status == .running
            && appState.isBackendRunning
            && !appState.authBroken
    }

    var body: some View {
        if isUsable {
            content()
        } else {
            // backendService flows in via @EnvironmentObject from the caller.
            BackendConnectionView(appState: appState)
        }
    }
}
