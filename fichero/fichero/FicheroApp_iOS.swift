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

    init() {
        // #4227: engine -> server rename; copy the saved host forward before
        // any store reads the canonical key.
        EngineConfig.migrateLegacyHostKeyIfNeeded()
    }

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
            documentDetailSceneRoot()
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
                // Daniel 2026-08-29: this edge is now the ONE owner of the
                // post-ready block. Every path that flips the backend ready —
                // launch probe, Retry, pairing, the 5s heartbeat recovering an
                // unreachable-at-launch host, endpoint failover (#3098) — lands
                // here, so library adoption/refresh (#3113) can never be skipped
                // by a recovery that bypassed `reconnectToConfiguredHost`, and
                // never runs twice for one flip.
                await libraryManager.refreshAfterBackendBecameReady()
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
        //
        // Daniel 2026-08-29 (device log: launch story resolved @ ~70.5s behind
        // serial ~60s NSURLError -1001 health timeouts): the paired Mac being
        // unreachable must not hold the launch narrative for the transport's
        // whole-request deadline. The workspace is already on screen with its
        // restored local state (BackendRootGate renders content in `.starting`),
        // so the probe runs to completion in the background while the STATUS
        // stops waiting after a short grace and says honestly that the host
        // hasn't answered yet. The probe's eventual verdict still lands — a
        // slow-but-alive host self-corrects to ready, a dead one refines the
        // diagnosis.
        let watchdog = Task {
            try? await Task.sleep(for: LaunchProbePolicy.firstProbeGrace)
            guard !Task.isCancelled else { return }
            // Both this task and the probe resolve phase on the main actor, so
            // the check-and-flip is serialized: a probe that already resolved
            // wins (`keepResolvedPhase`), and a probe that resolves later
            // simply overwrites this honest interim status.
            guard LaunchProbePolicy.actionOnGraceExpiry(phase: appState.engine.phase)
                == .markStillConnecting else { return }
            // Observable in the LaunchProfile timeline: this is the moment the
            // launch story stopped waiting for the transport deadline.
            LaunchProfile.milestone("launch probe grace expired — honest still-connecting status")
            appState.engine.markUnreachable(
                LaunchProbePolicy.stillConnectingDiagnosis(
                    host: EngineConfig.host.host ?? EngineConfig.host.absoluteString
                )
            )
        }
        await appState.checkBackendHealth()
        watchdog.cancel()

        // The heartbeat is BOTH halves of the connection watchdog (Daniel,
        // 2026-08-29): with the host up it watches for a mid-session drop; with
        // the host down it IS the background launch retry — the same 5s
        // readiness poll recovers through `warmContextThenMarkReady` (#4359)
        // and the ready flip below then runs the post-ready block. Started
        // unconditionally so a launch against a sleeping Mac keeps quietly
        // retrying instead of parking forever on the first probe's verdict.
        appState.startBackendHeartbeat()
        guard appState.isBackendRunning else {
            logger.error(
                """
                External backend is not reachable at \
                \(EngineConfig.host.absoluteString, privacy: .public) — retrying in the background
                """
            )
            return
        }
        // Proactively renew the device token if it is near expiry (#3096), before
        // it can lapse into a 401. No-op for local hosts / unknown expiry; a failed
        // renew keeps the old token (the expired → re-pair path is the safety net).
        await DeviceTokenRenewal.renewIfNeeded(host: EngineConfig.host)
        // The shared post-ready block (#3113) — refresh + capture resume — runs
        // off the `isBackendRunning` false→true edge (`onChange` above), which
        // this ready flip has just fired. Keeping ONE owner for that block means
        // launch, Retry, pairing, heartbeat recovery, and endpoint failover all
        // run the same side effects exactly once per recovery (Daniel,
        // 2026-08-29: a launch that failed and later recovered via the
        // heartbeat used to skip library adoption entirely).
    }
}

extension FicheroAppIOS {
    /// The document-detail scene's root, with the FULL boundary re-injection
    /// (#4513, the Mac crash class): a detached scene inherits NOTHING, and
    /// DocumentDetailWindow's subtree reads thirteen services non-optionally.
    /// The ONE shared list (libraryServiceEnvironment) — never a hand-copied
    /// subset. The window still resolves its own per-document library inside;
    /// this covers the first mount before FocusedDocument publishes.
    @ViewBuilder
    func documentDetailSceneRoot() -> some View {
        if let library = libraryManager.getLibrary(
            id: FocusedDocument.shared.libraryId ?? UUID()
        ) ?? libraryManager.globalLibrary {
            DocumentDetailWindow()
                .environment(libraryManager)
                .environment(claimFocusState)
                .environment(kgFocusState)
                .libraryServiceEnvironment(library)
        } else {
            // No library open at all — the window renders its own
            // "select a document" empty state and reads no services.
            DocumentDetailWindow()
                .environment(libraryManager)
                .environment(claimFocusState)
                .environment(kgFocusState)
        }
    }
}
#endif
