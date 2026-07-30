#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import FicheroAPIClient
import SwiftUI

/// The engine connection status surface: a small popover hosted by
/// `EngineStatusToolbarItem`, and (on iOS first-run) the `.setupNeeded` screen.
///
/// It renders `ConnectionPresentation.status(…)` and nothing else (#4380).
/// That is the whole point: this view used to narrate a startup sequence it was
/// not observing ("Starting Fichero → Loading runtime libraries… → Opening the
/// database… → This can take a moment"), print a `PYTHONPATH=…` shell command
/// as the user's next step under a label truncated to "Start Exte…", and stack
/// two 72pt illustration icons above it — while the sidebar pill said something
/// else entirely. Now there is one state source, one honest sentence, one
/// small symbol, and one primary action that agrees with the pill.
///
/// Anything a developer needs and a user does not — the raw transport error,
/// the engine's own log lines, the command to start an external engine by hand
/// — lives behind Show Log (#4269).
struct BackendConnectionView: View {
    @Bindable var appState: AppState
    /// The single retry entry point (#3108), supplied by the root gate. The
    /// button just calls this; the view never probes health, writes backend
    /// status, or re-implements `start()` — it is render-only.
    var onRetry: (@MainActor () async -> Void)?
    @Environment(EmbeddedBackendService.self) var backendService

    var body: some View {
        content(connectionStatus)
    }

    /// Split from `body` so each piece stays a small, bounded expression — the
    /// LibraryWindow type-check timeout is a standing hazard in this codebase.
    @ViewBuilder
    private func content(_ status: ConnectionPresentation.Display) -> some View {
        VStack(spacing: 16) {
            header(status)
            detail(status)
            actionRow(status.action)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(platformColor: .windowBackgroundColor))
        .onChange(of: appState.isBackendRunning) { _, running in
            // The background heartbeat re-probes even while we're parked on a
            // startup failure (#3162/#4296). The moment it recovers readiness,
            // clear the failed status so this popover stops outliving the
            // failure it describes.
            if running, backendService.status == .failed {
                backendService.status = .running
                backendService.errorMessage = nil
            }
        }
    }

    /// One small symbol beside the title — consistent with the status island's
    /// error affordance. Never an illustration: this is status chrome, not an
    /// onboarding screen.
    private func header(_ status: ConnectionPresentation.Display) -> some View {
        HStack(spacing: 8) {
            Image(systemName: status.symbol)
                .font(.title3)
                .foregroundStyle(status.isError ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
            Text(status.title)
                .font(.title3)
                .fontWeight(.semibold)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
        }
        .accessibilityElement(children: .combine)
        // #3937/#3944's assertion target: this identifier renders IFF the
        // status is an error, so a UI test catches a failure screen appearing
        // on a healthy launch.
        .accessibilityIdentifier(status.isError ? "backend.connection.title" : "backend.connection.status")
    }

    @ViewBuilder
    private func detail(_ status: ConnectionPresentation.Display) -> some View {
        if !status.detail.isEmpty {
            Text(status.detail)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        if status.isRecovering {
            // Recovery is automatic — say so and let it happen (#4296).
            ProgressView()
                .controlSize(.small)
        }
    }

    /// Exactly one primary action, plus the two ways out. The port-conflict
    /// phase keeps its dedicated three-way box (#3111/#3749) because "resolve
    /// the conflict" genuinely is more than one choice.
    @ViewBuilder
    private func actionRow(_ action: ConnectionPresentation.Action?) -> some View {
        HStack(spacing: 12) {
            if action == .resolvePortConflict {
                portConflictActions
            } else if let action {
                primaryActionButton(action)
            }
            settingsButton
            showLogButton
        }
    }
}

#Preview {
    BackendConnectionView(appState: AppState())
        .frame(width: 360, height: 240)
}
