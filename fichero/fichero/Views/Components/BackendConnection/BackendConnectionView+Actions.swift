#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import SwiftUI

extension BackendConnectionView {
    /// Route a broken connection into engine Settings (host / sharing / login) —
    /// the way OUT when the primary action isn't enough (wrong host, needs a
    /// remote/login, or the engine must be configured). Available on every
    /// failure phase, since the app stays usable behind the non-modal popover.
    @ViewBuilder
    var settingsButton: some View {
        Button {
            appState.openSettings(tab: .backend)
        } label: {
            Label("Settings…", systemImage: "gearshape")
        }
        .accessibilityIdentifier("backend.action.openSettings")
    }

    /// The ONE primary action, chosen by `ConnectionPresentation` (#4380).
    ///
    /// There is exactly one of these on screen, its label is short enough not
    /// to truncate (#4366), and it agrees with the sidebar's "Live updates
    /// paused / Reconnect" pill because both read the same mapping. Reconnect
    /// and Restart Engine both run the single retry entry point (#3108) — the
    /// difference is only what the app can honestly claim it is doing.
    @ViewBuilder
    func primaryActionButton(_ action: ConnectionPresentation.Action) -> some View {
        Button {
            perform(action)
        } label: {
            Label(action.title, systemImage: action.systemImage)
                .lineLimit(1)
        }
        .buttonStyle(.borderedProminent)
        .disabled(backendService.isStarting)
        .accessibilityIdentifier(Self.accessibilityIdentifier(for: action))
    }

    /// Stable per-action identifiers so the launch UI tests can assert that a
    /// specific recovery is ABSENT on a healthy launch (#3919/#3944).
    static func accessibilityIdentifier(
        for action: ConnectionPresentation.Action
    ) -> String {
        switch action {
        case .reconnect: return "backend.action.reconnect"
        case .restartEngine: return "backend.action.restartEngine"
        case .resolvePortConflict: return "backend.action.resolvePortConflict"
        case .resetSignIn: return "backend.action.resetSignIn"
        case .resetCertificate: return "backend.action.resetCertificate"
        case .forgetPairing: return "backend.action.forgetPairing"
        }
    }

    /// Every action ends in the one retry entry point (#3108) except
    /// `forgetPairing`, which has nothing to retry until the user re-pairs.
    func perform(_ action: ConnectionPresentation.Action) {
        switch action {
        case .reconnect, .restartEngine:
            break
        case .resolvePortConflict:
            // Adopt the process already holding :8765 — still gated on the
            // authenticated probe (#3111).
            backendService.pendingPortConflictResolution = .useIt
        case .resetSignIn:
            // Clearing the session token forces the next connect to recover
            // auth instead of retrying the same rejected token forever (#2864).
            AuthTokenMiddleware.clearSessionToken()
        case .resetCertificate:
            RemoteCertificatePinning.clearPersistedSPKIPin(hostString: EngineConfig.hostString)
        case .forgetPairing:
            // The pairing escape hatch (#3971): clear the pairing, then flip the
            // session to `.setupNeeded` so `BackendRootGate` re-renders the QR /
            // Bonjour / manual-invite screen. No retry — there is no host left.
            RemoteClientPairing.forgetPairing()
            appState.engine.markSetupNeeded()
            return
        }
        Task { await onRetry?() }
    }

    /// The in-window replacement for the old pre-window port-conflict NSAlert
    /// (#3111): Stop it (SIGTERM + respawn) / Use it (adopt, still gated on the
    /// authenticated probe) / Quit (a user-chosen terminate — allowed; only an
    /// app-chosen terminate is not, #3042). Each choice records the resolution
    /// on the service, then runs the one retry path.
    var useExistingEngineButton: some View {
        Button {
            backendService.pendingPortConflictResolution = .useIt
            Task { await onRetry?() }
        } label: {
            Label("Use the Existing Server", systemImage: "link")
                .lineLimit(1)
        }
        .disabled(backendService.isStarting)
    }

    @ViewBuilder
    var portConflictActions: some View {
        // "Stop it" needs a PID to SIGTERM. The App Store build cannot learn one
        // (and could not signal it anyway), so the button is absent there rather
        // than present-and-broken — the remaining choices still resolve the
        // conflict, so this never leaves an empty box (#3749).
        if portConflictPID != nil {
            Button {
                backendService.pendingPortConflictResolution = .stopIt
                Task { await onRetry?() }
            } label: {
                Label("Stop It & Restart", systemImage: "stop.circle")
                    .lineLimit(1)
            }
            .buttonStyle(.borderedProminent)
            .disabled(backendService.isStarting)
        }

        // Promoted to the prominent action when "Stop it" isn't offered, so the
        // conflict box always has exactly one obvious default.
        if portConflictPID == nil {
            useExistingEngineButton.buttonStyle(.borderedProminent)
        } else {
            useExistingEngineButton.buttonStyle(.bordered)
        }

        #if canImport(AppKit)
        Button {
            // User-chosen quit is fine — only an app-chosen terminate is banned
            // (#3042).
            NSApplication.shared.terminate(nil)
        } label: {
            Label("Quit Fichero", systemImage: "xmark.circle")
                .lineLimit(1)
        }
        .buttonStyle(.bordered)
        #endif
    }

    /// Opens the full engine log — where the developer detail belongs. The
    /// popover deliberately shows no raw transport error and no shell command
    /// (#4380/#4269); this button is the way to both. macOS only.
    @ViewBuilder
    var showLogButton: some View {
        #if canImport(AppKit)
        Button {
            let logURL = FileManager.default
                .urls(for: .libraryDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("Logs/Fichero/engine.log")
            NSWorkspace.shared.open(logURL)
        } label: {
            Label("Show Log", systemImage: "doc.text.magnifyingglass")
        }
        .buttonStyle(.bordered)
        #endif
    }
}
