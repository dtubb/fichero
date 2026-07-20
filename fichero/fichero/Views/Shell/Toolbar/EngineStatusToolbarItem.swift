import SwiftUI

// MARK: - engineRetry environment key

private struct EngineRetryKey: EnvironmentKey {
    static let defaultValue: (@MainActor () async -> Void)? = nil
}

extension EnvironmentValues {
    /// The one retry entry point (#3108), threaded down from the app root
    /// alongside `BackendRootGate`'s own `onRetry` so any toolbar chrome can
    /// offer Retry without re-implementing the platform's connect sequence.
    /// Set once in `FicheroApp.swift` / `FicheroApp_iOS.swift`, right next to
    /// `BackendRootGate(onRetry:)`. `nil` by default (e.g. in previews).
    var engineRetry: (@MainActor () async -> Void)? {
        get { self[EngineRetryKey.self] }
        set { self[EngineRetryKey.self] = newValue }
    }
}

// MARK: - EngineStatusToolbarItem

/// Leading (Xcode-style) toolbar status for the engine connection
/// (startup-transport-ux S1). `BackendRootGate` no longer full-window-gates
/// on `.starting` / the failure phases — `content()` (this toolbar's host)
/// renders immediately in every phase but `.setupNeeded` — so this is the
/// ONLY chrome that tells the user the engine isn't ready yet or needs
/// attention. Mirrors Xcode's own build-status item: a small glyph, tap for
/// detail.
///
/// The `ToolbarItem` that hosts this view is declared unconditionally in
/// `ContentView+Toolbar.swift` — only this view's CONTENT varies by phase.
/// Never gate the `ToolbarItem` itself on phase: doing so re-triggers
/// NSToolbar's first-layout insert path and risks the #3163 double-insert
/// crash the same way a phase-gated sheet did.
struct EngineStatusToolbarItem: View {
    @Environment(AppState.self) private var appState
    @Environment(\.engineRetry) private var engineRetry

    @State private var showPopover = false

    private var phase: EngineSession.Phase { appState.engine.phase }

    var body: some View {
        Group {
            switch phase {
            case .starting:
                ProgressView()
                    .controlSize(.small)
            case .portConflict, .authRejected, .unreachable, .failed:
                Button {
                    showPopover = true
                } label: {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Engine status")
                .help("Engine connection problem — click for details and Retry")
            case .setupNeeded, .ready:
                // `.setupNeeded` never actually reaches this view (the root
                // gate routes it to `setup()`, not `content()`); `.ready`
                // means nothing to show. Both render nothing — the stable
                // `ToolbarItem` just goes empty, it is never removed.
                EmptyView()
            }
        }
        .popover(isPresented: $showPopover) {
            // Reuse BackendConnectionView wholesale (its diagnosis text +
            // Retry / reset-sign-in / reset-certificate / port-conflict /
            // show-log actions all live in BackendConnectionView+Actions and
            // +Status) rather than re-implementing any of that chrome here.
            BackendConnectionView(appState: appState, onRetry: engineRetry)
                .frame(width: 360, height: 340)
        }
        .accessibilityLabel(accessibilityLabel)
    }

    private var accessibilityLabel: String {
        switch phase {
        case .starting:
            return "Connecting to engine"
        case .portConflict, .authRejected, .unreachable, .failed:
            return appState.engine.diagnosis ?? "Engine connection problem"
        case .setupNeeded, .ready:
            return "Engine ready"
        }
    }
}
