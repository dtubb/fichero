#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import FicheroAPIClient
import SwiftUI

extension BackendConnectionView {
    /// Route a broken connection into engine Settings (host / sharing / login) —
    /// the way OUT when Retry isn't enough (wrong host, needs a remote/login, or
    /// the engine must be configured). Available on every failure phase, since the
    /// app now stays usable behind the non-modal toolbar popover.
    @ViewBuilder
    var settingsButton: some View {
        Button {
            appState.openSettings(tab: .backend)
        } label: {
            Label("Settings…", systemImage: "gearshape")
        }
        .accessibilityIdentifier("backend.action.openSettings")
    }

    static func showsRetryButton(usesAppManagedEmbeddedEngine: Bool) -> Bool {
        !usesAppManagedEmbeddedEngine
    }

    var showsRetryButton: Bool {
        Self.showsRetryButton(usesAppManagedEmbeddedEngine: usesAppManagedEmbeddedEngine)
    }

    /// The single retry entry point (#3108) — reconnect (remote / debug-local).
    @ViewBuilder
    var retryButton: some View {
        Button {
            // Reset the cycling copy, then delegate to the ONE retry entry
            // point (#3108). The retry flips the phase back to `.starting`,
            // which re-fires the booting UI — the view never probes health or
            // spawns an engine itself.
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label(retryButtonTitle, systemImage: "arrow.clockwise")
        }
        .buttonStyle(.borderedProminent)
        .disabled(backendService.isStarting)
        // Stable identifier for the user-managed retry action; app-managed
        // embedded engines hide it entirely (#3944).
        .accessibilityIdentifier("backend.action.restartEngine")
    }

    /// The in-window replacement for the old pre-window port-conflict NSAlert
    /// (#3111): Stop it (SIGTERM + respawn) / Use it (adopt, still gated on the
    /// authenticated probe) / Quit (a user-chosen terminate — allowed; only an
    /// app-chosen terminate is not, #3042). Each choice records the resolution
    /// on the service, then runs the one retry path.
    var useExistingEngineButton: some View {
        Button {
            backendService.pendingPortConflictResolution = .useIt
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label("Use the Existing Server", systemImage: "link")
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
                messageIndex = 0
                Task { await onRetry?() }
            } label: {
                Label("Stop It & Start Fichero's Server", systemImage: "stop.circle")
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
        }
        .buttonStyle(.bordered)
        #endif
    }

    static func showsResetSignInButton(
        accessError: AccessError?,
        usesAppManagedEmbeddedEngine: Bool
    ) -> Bool {
        accessError?.recovery == .signIn && !usesAppManagedEmbeddedEngine
    }

    var showsResetSignInButton: Bool {
        Self.showsResetSignInButton(
            accessError: failureAccessError,
            usesAppManagedEmbeddedEngine: usesAppManagedEmbeddedEngine
        )
    }

    static func showsResetCertificateButton(
        accessError: AccessError?,
        usesAppManagedEmbeddedEngine: Bool
    ) -> Bool {
        accessError?.recovery == .resetPin && !usesAppManagedEmbeddedEngine
    }

    var showsResetCertificateButton: Bool {
        Self.showsResetCertificateButton(
            accessError: failureAccessError,
            usesAppManagedEmbeddedEngine: usesAppManagedEmbeddedEngine
        )
    }

    /// Stale-credential recovery, shown only in the auth-rejected phase (#2864):
    /// the engine is up but refusing a user-managed token. Clearing the session token
    /// forces the next connect to recover remote/debug-local auth instead of retrying
    /// the same rejected token forever. App-managed embedded engines mint their own
    /// bootstrap credential, so they never show sign-in reset (#3944).
    @ViewBuilder
    var resetSignInButton: some View {
        Button {
            AuthTokenMiddleware.clearSessionToken()
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label("Reset Sign-In & Retry", systemImage: "person.badge.key")
        }
        .buttonStyle(.bordered)
        .disabled(backendService.isStarting)
        // #3919's assertion target: this button must be ABSENT for any failure
        // whose remedy isn't `.signIn` (a scoped 403, an unreachable engine).
        .accessibilityIdentifier("backend.action.resetSignIn")
    }

    @ViewBuilder
    var resetCertificateButton: some View {
        Button {
            RemoteCertificatePinning.clearPersistedSPKIPin(hostString: EngineConfig.hostString)
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label("Reset Certificate & Retry", systemImage: "lock.rotation")
        }
        .buttonStyle(.borderedProminent)
        .disabled(backendService.isStarting)
    }

    /// True only for the two iOS pairing dead-ends (#3971): a paired host that
    /// is `unreachable` or has `failed`. A permanently-broken pairing otherwise
    /// has no way back to the QR screen — Retry just re-probes the same dead
    /// host forever — so these phases (and only these) offer "Forget This Mac".
    /// Gated to platforms that pair to an external engine; macOS starts its own
    /// embedded engine and never pairs, so it must never show this.
    var showsForgetPairingButton: Bool {
        #if os(iOS) || os(visionOS)
        switch appState.engine.phase {
        case .unreachable, .failed:
            return true
        case .setupNeeded, .starting, .portConflict, .authRejected, .ready:
            return false
        }
        #else
        return false
        #endif
    }

    /// The pairing escape hatch (#3971): clears every trace of the current
    /// pairing, then flips the session to `.setupNeeded` so `BackendRootGate`
    /// re-renders `RemoteConnectionSetupView` (the QR / Bonjour / manual-invite
    /// screen). Unlike the sign-in / certificate buttons this is NOT tied to a
    /// specific `AccessError` — it is the last resort when the host itself is
    /// gone and re-pairing is the only fix.
    @ViewBuilder
    var forgetPairingButton: some View {
        Button {
            RemoteClientPairing.forgetPairing()
            appState.engine.markSetupNeeded()
        } label: {
            Label("Forget This Mac", systemImage: "xmark.circle")
        }
        .buttonStyle(.bordered)
        .accessibilityIdentifier("backend.action.forgetPairing")
    }

    /// Opens the full engine log so a failure has a next step beyond "try
    /// again" — the tail already appears inline (#2864). macOS only.
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
