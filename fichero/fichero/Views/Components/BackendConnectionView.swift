#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import FicheroAPIClient
import SwiftUI

/// View shown while the embedded engine is booting (or when it failed to start).
///
/// The engine takes ~25-40s to boot on first launch (heavy ML imports — see
/// engine#743 for the lazy-import refactor that will fix this). To make that
/// wait feel less dead, we cycle through a few honest messages that match
/// what the engine is actually doing, and use the app icon instead of a
/// generic SF symbol.
struct BackendConnectionView: View {
    @Bindable var appState: AppState
    /// The single retry entry point (#3108), supplied by the root gate. The
    /// button just calls this; the view never probes health, writes backend
    /// status, or re-implements `start()` — it is render-only.
    var onRetry: (@MainActor () async -> Void)?
    @Environment(EmbeddedBackendService.self) var backendService

    /// Index into `Self.startupMessages`, advanced by a timer while `.starting`.
    @State private var messageIndex: Int = 0

    /// Animation phase for the connecting-dots between app + engine icons.
    @State private var dotPhase: Int = 0

    private var usesExternalBackendConnection: Bool {
        #if os(iOS) || os(visionOS)
        true
        #else
        EngineConfig.requiresExternalBackendConnection
        #endif
    }

    /// Messages cycled while the session is `.starting` (`engine.isChecking`).
    ///
    /// Honest phrasing only: the engine doesn't load models, prepare the
    /// graph, or index the library at startup — it imports Python libraries
    /// and initializes its database. Aspirational copy ("loading language
    /// models", "indexing your library") is a lie; users notice. Each line
    /// describes what the engine is *actually* doing in that window.
    private static let startupMessages: [String] = [
        "Connecting to the engine…",
        "Loading runtime libraries…",
        "Opening the database…",
        "Almost ready…"
    ]

    /// Engine icon resolved from the bundled Fichero Engine.app.
    /// Falls back to the system server icon if the engine icon isn't found.
    private var engineIconImage: PlatformImage {
        if let resourcePath = Bundle.main.resourcePath {
            let iconPath = "\(resourcePath)/Fichero Engine.app/Contents/Resources/engine.icns"
            if let image = PlatformImage(contentsOfFile: iconPath) {
                return image
            }
        }
        #if canImport(AppKit)
        return PlatformImage(systemSymbolName: "server.rack", accessibilityDescription: nil) ?? PlatformImage()
        #elseif canImport(UIKit)
        return PlatformImage(systemName: "server.rack") ?? PlatformImage()
        #else
        return PlatformImage()
        #endif
    }

    /// Fichero app icon loaded as a flat .icns from the app bundle, NOT
    /// via NSApp.applicationIconImage which on macOS Tahoe (26+) gets
    /// auto-wrapped in the system rounded-squircle treatment. The engine
    /// icon next to it renders flat (loaded the same way), so loading
    /// the Fichero side flat keeps the splash visually consistent (#793).
    private var ficheroIconImage: PlatformImage {
        if let resourcePath = Bundle.main.resourcePath {
            // The app's compiled icon catalog produces AppIcon.icns at
            // the bundle root. Loading it directly via PlatformImage avoids
            // the system squircle that NSApp.applicationIconImage applies.
            let iconPath = "\(resourcePath)/AppIcon.icns"
            if let image = PlatformImage(contentsOfFile: iconPath) {
                return image
            }
        }
        // Fallback to the Tahoe-treated app icon if the .icns isn't
        // findable (custom builds, dev sandbox).
        #if canImport(AppKit)
        return NSApp.applicationIconImage ?? PlatformImage()
        #elseif canImport(UIKit)
        return PlatformImage(systemName: "books.vertical") ?? PlatformImage()
        #else
        return PlatformImage()
        #endif
    }

    /// Red failure UI shows ONLY for an explicit terminal failure
    /// (`status == .failed`). During normal startup the service walks
    /// `.stopped → .starting → .running`, and `appState.isCheckingBackend`
    /// flips false in the 5 s gaps between health polls — keying failure off
    /// `(!isCheckingBackend && !isBackendRunning)` painted a misleading red
    /// "Engine Not Running" flash during those gaps while the engine was still
    /// cold-starting (#2664). Genuine failures still surface: external/custom
    /// hosts set `.failed` immediately, and the embedded poll loop below flips
    /// to `.failed` after the 60 s timeout.
    private var showsFailureState: Bool {
        // Driven by the single phase owner (#3107): any non-ready, non-starting,
        // non-setup phase is a failure the user can act on.
        switch appState.engine.phase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return true
        case .setupNeeded, .starting, .ready:
            return false
        }
    }

    private var titleText: String {
        usesExternalBackendConnection ? "Connect to Fichero" : "Starting Fichero"
    }

    /// The holding PID when the engine is in the `portConflict` phase (#3111),
    /// else nil. Drives the in-window Stop it / Use it / Quit actions.
    private var portConflictPID: Int? {
        if case .portConflict(let pid) = appState.engine.phase { return pid }
        return nil
    }

    private var failureTitle: String {
        if portConflictPID != nil {
            // Foreign holder of :8765 — the in-window replacement for the old
            // pre-window NSAlert (#3111).
            return "Port 8765 Is In Use"
        }
        if appState.authBroken {
            // Health-200-but-auth-broken: the specific state that used to blank
            // the window with silent 401s (#2864).
            return "Can't Authenticate to Engine"
        }
        return usesExternalBackendConnection ? "Backend Not Reachable" : "Engine Not Running"
    }

    /// Prefer the specific diagnosis (port occupied by PID / auth rejected /
    /// probe failed) over the generic error string (#2864).
    private var failureDetail: String? {
        appState.backendDiagnosis ?? appState.backendError
    }

    private var secondaryStatusText: String {
        usesExternalBackendConnection ? "Connect to a running Fichero engine to continue." : "This can take a moment."
    }

    /// The single retry entry point (#3108) — respawn (macOS) / re-adopt (iOS).
    @ViewBuilder
    private var retryButton: some View {
        Button {
            // Reset the cycling copy, then delegate to the ONE retry entry
            // point (#3108). The retry flips the phase back to `.starting`,
            // which re-fires the booting UI — the view never probes health or
            // spawns an engine itself.
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label(usesExternalBackendConnection ? "Retry Connection" : "Restart Engine", systemImage: "arrow.clockwise")
        }
        .buttonStyle(.borderedProminent)
        .disabled(backendService.isStarting)
    }

    /// The in-window replacement for the old pre-window port-conflict NSAlert
    /// (#3111): Stop it (SIGTERM + respawn) / Use it (adopt, still gated on the
    /// authenticated probe) / Quit (a user-chosen terminate — allowed; only an
    /// app-chosen terminate is not, #3042). Each choice records the resolution
    /// on the service, then runs the one retry path.
    @ViewBuilder
    private var portConflictActions: some View {
        Button {
            backendService.pendingPortConflictResolution = .stopIt
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label("Stop It & Start Fichero's Engine", systemImage: "stop.circle")
        }
        .buttonStyle(.borderedProminent)
        .disabled(backendService.isStarting)

        Button {
            backendService.pendingPortConflictResolution = .useIt
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label("Use the Existing Engine", systemImage: "link")
        }
        .buttonStyle(.bordered)
        .disabled(backendService.isStarting)

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

    /// Stale-credential recovery, shown only in the auth-rejected phase (#2864):
    /// the engine is up but refusing our token. Clearing the session token forces
    /// the next connect to fall back to the loopback/bootstrap credential (and, in
    /// multi-user, back to the sign-in gate) instead of retrying the same rejected
    /// token forever. Harmless no-op when no session token exists (single-user),
    /// so it is safe to offer whenever auth is broken.
    @ViewBuilder
    private var resetSignInButton: some View {
        Button {
            AuthTokenMiddleware.clearSessionToken()
            messageIndex = 0
            Task { await onRetry?() }
        } label: {
            Label("Reset Sign-In & Retry", systemImage: "person.badge.key")
        }
        .buttonStyle(.bordered)
        .disabled(backendService.isStarting)
    }

    /// Opens the full engine log so a failure has a next step beyond "try
    /// again" — the tail already appears inline (#2864). macOS only.
    @ViewBuilder
    private var showLogButton: some View {
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

    var body: some View {
        VStack(spacing: 24) {
            // Two icons side-by-side — Fichero (app) on the left, Engine
            // (Python helper) on the right — with three dots animating
            // between them to visualize "the app is talking to the engine".
            // The dots cycle through three phases on a 0.4s timer; the
            // single "active" dot lights up while the others dim.
            HStack(spacing: 16) {
                Image(platformImage: ficheroIconImage)
                    .resizable()
                    .interpolation(.high)
                    .frame(width: 72, height: 72)

                HStack(spacing: 6) {
                    ForEach(0..<3, id: \.self) { dotIndex in
                        Circle()
                            .fill(dotPhase == dotIndex ? Color.accentColor : Color.secondary.opacity(0.3))
                            .frame(width: 8, height: 8)
                    }
                }
                .frame(width: 50)

                Image(platformImage: engineIconImage)
                    .resizable()
                    .interpolation(.high)
                    .frame(width: 72, height: 72)
            }

            Text(titleText)
                .font(.title)
                .fontWeight(.semibold)

            // Decide which state to show. `.stopped` is a transient state
            // at app-launch (we haven't called `start()` yet) — UI-wise it
            // belongs with `.starting`, not in the red-error branch. Only
            // `.failed` triggers the red error text and the Retry button.
            // This prevents the "engine not running" flash that happens in
            // the ~100ms gap between view-mount and `start()` being called.
            let isFailed = showsFailureState
            let isBootingOrChecking = !isFailed

            if isBootingOrChecking {
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.2)

                    // Cycling status. The transition gives a soft fade so
                    // the message change isn't a jarring text-swap.
                    Text(Self.startupMessages[messageIndex])
                        .font(.headline)
                        .foregroundColor(.primary)
                        .id(messageIndex) // force re-render for transition
                        .transition(.opacity)

                    Text(secondaryStatusText)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            } else {
                VStack(spacing: 12) {
                    Text(failureTitle)
                        .font(.headline)
                        .foregroundColor(.red)

                    if let error = failureDetail {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                }
            }

            // Shown only after a failure phase — not during normal booting where
            // the user hasn't done anything wrong. Tapping it runs the single
            // retry entry point (#3108): macOS respawns the stuck engine, iOS
            // re-adopts its paired host. The button is absent while `.starting`,
            // so a retry can never SIGTERM a healthy cold-starting engine.
            if isFailed {
                HStack(spacing: 12) {
                    // A foreign holder of :8765 gets the three-way in-window
                    // decision (#3111); every other failure gets the single
                    // retry entry point (#3108).
                    if portConflictPID != nil {
                        portConflictActions
                    } else {
                        retryButton
                        // Auth-rejected (engine up, token refused) also gets the
                        // stale-credential reset so the taxonomy has a next step
                        // beyond respawning into the same rejection (F6).
                        if appState.authBroken {
                            resetSignInButton
                        }
                    }
                    showLogButton
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(platformColor: .windowBackgroundColor))
        .task(id: appState.engine.isChecking) {
            // Cycle the honest status copy while the session is `.starting`
            // (#3108). Render-only: readiness is owned by the session's single
            // poller (fast poll while starting, heartbeat while ready) — this
            // loop only advances the message index, it never probes or writes
            // backend state.
            guard appState.engine.isChecking else { return }
            while !Task.isCancelled, appState.engine.isChecking {
                try? await Task.sleep(for: .seconds(5))
                if Task.isCancelled { return }
                withAnimation(.easeInOut(duration: 0.4)) {
                    messageIndex = min(messageIndex + 1, Self.startupMessages.count - 1)
                }
            }
        }
        .task(id: appState.engine.isChecking) {
            // Dot animation — faster cadence so the splash stays alive between
            // message changes. Also purely visual; stops as soon as the session
            // leaves `.starting`.
            guard appState.engine.isChecking else { return }
            while !Task.isCancelled, appState.engine.isChecking {
                try? await Task.sleep(for: .milliseconds(450))
                if Task.isCancelled { return }
                withAnimation(.easeInOut(duration: 0.25)) {
                    dotPhase = (dotPhase + 1) % 3
                }
            }
        }
    }
}

#Preview {
    BackendConnectionView(appState: AppState())
        .frame(width: 600, height: 400)
}
