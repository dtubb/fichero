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

    /// Local vs remote for the ready glyph (#4391) — the SAME derivation the
    /// accessibility label and popover already use (#4400's one table), so the
    /// glyph, the spoken label and the popover text cannot disagree.
    private var isRemote: Bool {
        ConnectionPresentation.EngineOwnership.current() == .remote
    }

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
                    Image(systemName: ToolbarSymbols.engineProblem)
                        .foregroundStyle(.orange)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Server status")
                .help("Engine connection problem — click for details and Retry")
            case .setupNeeded, .ready:
                // `.setupNeeded` never actually reaches this view (the root
                // gate routes it to `setup()`, not `content()`); `.ready`
                // shows a subtle persistent glyph so the status island always
                // has its left button — click for connection details.
                Button {
                    showPopover = true
                } label: {
                    // #4391: `.secondary` (no colour) alongside an outline
                    // glyph is what made a HEALTHY connection read as
                    // disconnected — the problem state gets `.orange` and a
                    // filled triangle; ready gets its own colour now instead
                    // of a shrug. The glyph also names the TRANSPORT: a UDS
                    // engine on this Mac and an engine on another machine
                    // differ in who can restart it and whether work survives
                    // a network drop, and one symbol hid that entirely.
                    Image(systemName: isRemote
                        ? ToolbarSymbols.engineReadyRemote
                        : ToolbarSymbols.engineReadyLocal)
                        .foregroundStyle(.green)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Server status")
                .help(isRemote
                    ? "Connected to a remote server — click for details"
                    : "Connected to this Mac — click for details")
            }
        }
        .popover(isPresented: $showPopover) {
            // Reuse BackendConnectionView wholesale (its diagnosis text +
            // Retry / reset-sign-in / reset-certificate / port-conflict /
            // show-log actions all live in BackendConnectionView+Actions and
            // +Status) rather than re-implementing any of that chrome here.
            // #4380: the popover is now a title, one sentence and one action —
            // it no longer needs 340pt of illustration and cycling copy.
            BackendConnectionView(appState: appState, onRetry: engineRetry)
                .frame(width: 380, height: 200)
        }
        .accessibilityLabel(accessibilityLabel)
    }

    /// The same mapped title the popover and the island show — VoiceOver must
    /// not be told a third version of the story, and must never be read a
    /// multi-line shell command (#4380).
    private var accessibilityLabel: String {
        ConnectionPresentation.status(
            phase: phase,
            ownership: ConnectionPresentation.EngineOwnership.current(),
            accessError: appState.backendAccessError,
            authBroken: appState.authBroken
        ).title
    }
}
