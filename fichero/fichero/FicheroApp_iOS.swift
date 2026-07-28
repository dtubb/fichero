#if os(iOS) || os(tvOS) || os(visionOS)
import FicheroAPIClient
import OSLog
import SwiftUI

@main
struct FicheroAppIOS: App {
    @State private var backendService = EmbeddedBackendService()
    @State private var appState = AppState()
    @State private var viewSettings = ViewSettings()
    @State private var libraryManager = LibraryManager.shared
    @State private var windowState = WindowState(libraryId: LibraryManager.globalLibraryId)
    @State private var claimFocusState = ClaimFocusState.shared
    @State private var kgFocusState = KGFocusState.shared
    @State private var executionObserver = WorkflowExecutionObserver()
    @State private var captureQueue = MobileCaptureQueueStore()

    var body: some Scene {
        // `id: "main"` so `openWindow(id: "main")` (new-window / new-tab
        // affordances, WindowOpener) targets a registered scene on iPad instead
        // of being a silent no-op (#2815). Harmless on iPhone, which has no
        // multi-window support.
        WindowGroup(id: "main") {
            FicheroSharedPlatformRoot(
                windowState: windowState,
                executionObserver: executionObserver
            )
                .environment(windowState)
                .environment(backendService)
                .environment(appState)
                .environment(viewSettings)
                .environment(libraryManager)
                .environment(FeatureManager.shared)
                .environment(claimFocusState)
                .environment(appState.mcpService)
                .environment(captureQueue)
                .environment(kgFocusState)
                // Launch connects via the SAME entry point as the Retry button
                // and pairing (#3108): FicheroSharedPlatformRoot owns the single
                // `reconnectToConfiguredHost()` task.
        }

        // Detached document-detail scene, mirroring the macOS registration so
        // the inspector's "Open in Window" affordance (DetachInspectorButton →
        // openWindow(id: "document-detail")) resolves on iPad instead of being a
        // silent no-op (#2815). iPhone gates the button off (single-window).
        WindowGroup("Document", id: "document-detail") {
            DocumentDetailWindow()
                .environment(libraryManager)
                .environment(claimFocusState)
                .environment(kgFocusState)
        }
    }
}

private struct IdentifiableURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

private struct FicheroSharedPlatformRoot: View {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroSharedPlatformRoot")
    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(MobileCaptureQueueStore.self) private var captureQueue

    let windowState: WindowState
    let executionObserver: WorkflowExecutionObserver

    @State private var pendingPairURL: IdentifiableURL?

    private var activeLibrary: LibraryManager.LibraryReference? {
        LibraryWorkspaceSelection.activeLibrary(
            currentLibraryId: libraryManager.currentLibraryId,
            windowLibraryId: windowState.libraryId,
            libraryManager: libraryManager
        )
    }

    var body: some View {
        // The SAME root gate as macOS, switching on the single phase (#3107):
        // setupNeeded → pairing; ready → workspace; every other phase →
        // BackendConnectionView (splash/diagnosis + Retry). No blank screen, and
        // a configured-but-unreachable host shows the error, never the pairing
        // prompt (#2864). backendService flows in via @EnvironmentObject.
        BackendRootGate(
            appState: appState,
            onRetry: { await reconnectToConfiguredHost() },
            setup: {
                RemoteConnectionSetupView {
                    await reconnectToConfiguredHost()
                }
            },
            content: {
                if let library = activeLibrary {
                    LibraryWorkspaceRoot(
                        library: library,
                        windowState: windowState,
                        executionObserver: executionObserver
                    )
                        .environment(windowState)
                        .environment(library.apiClient)
                } else {
                    ContentUnavailableView(
                        "Library Unavailable",
                        systemImage: "externaldrive.badge.exclamationmark",
                        description: Text("Fichero could not load the Local library.")
                    )
                }
            }
        )
        // Same retry closure as `onRetry` above, threaded via the environment
        // so `EngineStatusToolbarItem` (inside `content()`, which now renders
        // during `.starting` / failures too — startup-transport-ux S1) can
        // offer Retry without re-implementing `reconnectToConfiguredHost()`
        // (#3108).
        .environment(\.engineRetry, { await reconnectToConfiguredHost() })
        .onOpenURL { url in
            // Account invite link (#3157): route to the redeem gate. The token
            // is a secret query param, so it is never logged.
            if let token = SessionStore.inviteToken(from: url) {
                appState.sessionStore.beginInviteRedemption(token: token)
                return
            }
            // Accepts both fichero://pair and the https://fichero.app/pair
            // universal link (#3791).
            guard RemoteClientPairing.isPairingInviteLink(url) else { return }
            pendingPairURL = IdentifiableURL(url: url)
        }
        .sheet(item: $pendingPairURL) { wrapper in
            PairingIncomingLinkSheet(url: wrapper.url) {
                await reconnectToConfiguredHost()
            }
            .environment(appState)
            .environment(libraryManager)
            .environment(captureQueue)
        }
        // Launch connects through the SAME entry point as the Retry button and
        // pairing (#3108) — one iOS connect path, no divergent launch task.
        .task { await reconnectToConfiguredHost() }
        // #2389: reconnectToConfiguredHost covers launch/Retry/pairing, but a
        // capture taken offline in the field must also flush when the connection
        // recovers on its own while the app stays foregrounded — the 5s heartbeat
        // or an endpoint failover (#3098) flipping the engine back to ready. That
        // path doesn't run reconnectToConfiguredHost, so observe the readiness
        // shim and flush the queue on the false→true edge. resumePendingUploads
        // reserves items synchronously before its first await, so overlapping this
        // with the launch flush uploads each capture exactly once (never dropped,
        // never doubled).
        .onChange(of: appState.isBackendRunning) { _, isRunning in
            guard isRunning else { return }
            Task {
                _ = await captureQueue.resumePendingUploads(
                    using: MobileCaptureBackendUploadClient(libraryManager: libraryManager)
                )
            }
        }
    }

    /// The ONE iOS connect entry point (#3108): launch, the connection view's
    /// Retry, and incoming-pair all call this. Pairing is checked FIRST so a
    /// fresh, unpaired install shows first-run setup instead of a pointless
    /// probe-then-unreachable flash.
    private func reconnectToConfiguredHost() async {
        // #3772: log WHICH of the four persisted pairing values survived this launch.
        // The bug is not "we forgot to save it" — all four are written — so the fix
        // depends entirely on which one is missing, and this names it instead of
        // making us guess. Secrets are never logged, only presence.
        PairingRestoreDiagnostics.logAtLaunch()

        // Pure phase decision (#3113): with no paired library the launch is
        // `setupNeeded` regardless of reachability — a fresh install shows
        // first-run pairing instead of probing localhost (#2465). Reachability
        // is unknown until the probe, so `isReachable: false` here only gates
        // the setupNeeded branch; the probe below resolves ready vs unreachable.
        guard EngineConfig.iosLaunchPhase(
            hasPairedLibrary: RemoteAccessConfig.hasPairedLibraryPath,
            isReachable: false
        ) != .setupNeeded else {
            appState.engine.markSetupNeeded()
            return
        }
        // checkBackendHealth resolves the phase to ready / unreachable /
        // authRejected. A configured-but-down host lands on `unreachable` and
        // the gate shows the diagnosis — NEVER the pairing prompt (#2807/#2864).
        await appState.checkBackendHealth()
        guard appState.isBackendRunning else {
            logger.error(
                "External backend is not reachable at \(EngineConfig.host.absoluteString, privacy: .public)"
            )
            return
        }
        appState.startBackendHeartbeat()
        // Proactively renew the device token if it is near expiry (#3096), before
        // it can lapse into a 401. No-op for local hosts / unknown expiry; a failed
        // renew keeps the old token (the expired → re-pair path is the safety net).
        await DeviceTokenRenewal.renewIfNeeded(host: EngineConfig.host)
        // The SAME shared post-ready block as macOS (#3113), then the iOS-only
        // capture-queue resume — which is a mobile concern, not a library one.
        await libraryManager.refreshAfterBackendBecameReady()
        _ = await captureQueue.resumePendingUploads(
            using: MobileCaptureBackendUploadClient(libraryManager: libraryManager)
        )
    }
}
#endif
