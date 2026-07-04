#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

/// View shown while the embedded engine is booting (or when it failed to start).
///
/// The engine takes ~25-40s to boot on first launch (heavy ML imports — see
/// engine#743 for the lazy-import refactor that will fix this). To make that
/// wait feel less dead, we cycle through a few honest messages that match
/// what the engine is actually doing, and use the app icon instead of a
/// generic SF symbol.
struct BackendConnectionView: View {
    @ObservedObject var appState: AppState
    var onConnected: (@MainActor () async -> Void)?
    @EnvironmentObject var backendService: EmbeddedBackendService

    /// Index into `Self.startupMessages`, advanced by a timer.
    @State private var messageIndex: Int = 0

    /// Animation phase for the connecting-dots between app + engine icons.
    @State private var dotPhase: Int = 0

    /// How many consecutive 5-second health-poll intervals have passed without
    /// the backend coming up. When this hits `maxPollAttempts` the view
    /// declares failure rather than spinning forever on "Almost ready…".
    @State private var pollCount: Int = 0

    /// Incremented each time the user taps "Restart Engine". Both `.task`
    /// blocks are keyed on this value so SwiftUI cancels and re-creates them
    /// on each restart, resuming the poll loop from scratch.
    @State private var restartCount: Int = 0
    @State private var completedConnectionForCurrentAttempt = false

    /// 12 × 5 s = 60 s before we give up and show the error state.
    private static let maxPollAttempts = 12

    private var usesExternalBackendConnection: Bool {
        #if os(iOS) || os(visionOS)
        true
        #else
        EngineConfig.requiresExternalBackendConnection
        #endif
    }

    /// Messages cycled while `backendService.status == .starting`.
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

    private var failureTitle: String {
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

    @MainActor
    private func completeSuccessfulConnection() async {
        guard !completedConnectionForCurrentAttempt else { return }
        completedConnectionForCurrentAttempt = true
        backendService.status = .running
        backendService.errorMessage = nil
        await onConnected?()
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

            // Shown only after startup failure or timeout — not during normal
            // booting where the user hasn't done anything wrong. Tapping
            // "Restart Engine" stops the current (likely stuck) engine
            // process and re-launches it, resetting the poll counter so
            // the 60-second window starts fresh.
            if isFailed {
                HStack(spacing: 12) {
                    Button {
                        Task {
                            pollCount = 0
                            messageIndex = 0
                            restartCount += 1
                            completedConnectionForCurrentAttempt = false
                            // Reset to the starting phase so a fresh spawn (which
                            // rewrites the token) gets a clean readiness check;
                            // clears any prior authRejected/failed diagnosis.
                            appState.engine.markStarting()

                            if usesExternalBackendConnection {
                                backendService.status = .starting
                                backendService.errorMessage = nil
                                await appState.checkBackendHealth()
                                if !appState.isBackendRunning {
                                    backendService.status = .failed
                                    backendService.errorMessage = appState.backendError
                                } else {
                                    await completeSuccessfulConnection()
                                }
                            } else {
                                // Reset view state before restarting so the re-keyed
                                // tasks resume from a clean boot state.
                                backendService.status = .stopped
                                backendService.stop()
                                do {
                                    try await backendService.start()
                                    await appState.checkBackendHealth()
                                    if appState.isBackendRunning {
                                        await completeSuccessfulConnection()
                                    }
                                } catch {
                                    appState.engine.markFailed(error.localizedDescription)
                                }
                            }
                        }
                    } label: {
                        Label(usesExternalBackendConnection ? "Retry Connection" : "Restart Engine", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(backendService.status == .starting)

                    #if canImport(AppKit)
                    // Show the engine log so a failure has a next step beyond
                    // "try again" — the tail already appears inline, this opens
                    // the full log (#2864).
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
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(platformColor: .windowBackgroundColor))
        .task(id: restartCount) {
            // Poll health every 5 s while the engine is booting. After
            // maxPollAttempts failures we give up and flip status to
            // .failed so the error UI appears — this prevents the view
            // from cycling "Almost ready…" forever if the engine hangs.
            while !appState.isBackendRunning && backendService.status != .failed {
                try? await Task.sleep(for: .seconds(5))
                if Task.isCancelled { return }
                if backendService.status == .starting {
                    withAnimation(.easeInOut(duration: 0.4)) {
                        messageIndex = min(messageIndex + 1, Self.startupMessages.count - 1)
                    }
                }
                await appState.checkBackendHealth()
                if appState.isBackendRunning {
                    await completeSuccessfulConnection()
                    return
                }
                if !appState.isBackendRunning && backendService.status != .failed {
                    pollCount += 1
                    if pollCount >= Self.maxPollAttempts {
                        let msg = "Engine did not respond after \(Self.maxPollAttempts * 5) seconds."
                        backendService.status = .failed
                        backendService.errorMessage = msg
                        appState.engine.markFailed(msg)
                    }
                }
            }
        }
        .task(id: restartCount) {
            // Dot animation — runs independently at a faster cadence so the
            // visual stays alive even while the message timer waits.
            // Stops when the backend is up or when failure is declared.
            while !appState.isBackendRunning && backendService.status != .failed {
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
