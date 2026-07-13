// The macOS app entry declares every top-level Scene (main window, duplicate
// window, five detail scenes, activity monitor, settings) plus the full command
// menu in one `body`, so it runs past the generic length heuristics. Splitting
// the Scene graph across files buys nothing but indirection. (#2381 added the
// Option-launch remote-chooser wiring.)
// swiftlint:disable file_length
#if canImport(AppKit)
import AppKit
import OSLog
import SwiftUI

// MARK: - App Delegate

/// Custom AppDelegate to handle app lifecycle events (especially termination)
final class FicheroAppDelegate: NSObject, NSApplicationDelegate, ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroAppDelegate")
    weak var backendService: EmbeddedBackendService?

    func applicationWillTerminate(_ notification: Notification) {
        logger.info("App will terminate - stopping backend...")
        backendService?.stop()
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        true
    }
}

@main
// swiftlint:disable:next type_body_length
struct FicheroApp: App {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroApp")
    @Environment(\.openWindow) private var openWindow
    // App delegate for lifecycle events
    @NSApplicationDelegateAdaptor(FicheroAppDelegate.self) private var appDelegate

    // Backend service - manages embedded Python backend
    @State private var backendService = EmbeddedBackendService()

    // Backend connection state
    @State private var appState = AppState()
    @State private var viewSettings = ViewSettings()
    @StateObject private var featureManager = FeatureManager.shared
    @State private var claimFocusState = ClaimFocusState.shared
    @State private var kgFocusState = KGFocusState.shared

    // Library manager - singleton managing all open libraries
    @State private var libraryManager = LibraryManager.shared

    // App-level fallback observer injected into secondary scenes (artifact-detail,
    // citation-detail, etc.) that don't go through LibraryWindow. Prevents
    // @Environment(WorkflowExecutionObserver.self) crashes if workflow-aware views
    // are ever embedded in those scenes (#1587). LibraryWindow's own per-window
    // observer overrides this for the main window tree.
    @State private var appExecutionObserver = WorkflowExecutionObserver()

    /// #2381: true when the app launched with Option held, so the remote-client
    /// connection chooser should be presented over the main window. Decided once
    /// at launch in `init()`; never set for non-interactive (preview/UI-test)
    /// hosts.
    @State private var showRemoteConnectionChooser: Bool

    init() {
        // #2381: decide the launch connection mode BEFORE any early return so
        // this @State is initialized on every path. A normal launch uses the
        // embedded local engine; holding Option surfaces the remote-host chooser.
        let env = ProcessInfo.processInfo.environment
        let interactiveLaunch = !(env["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
            || env["XCODE_RUNNING_FOR_PLAYGROUNDS"] == "1"
            || isRunningXCTests()
            || isUITesting())
        let optionHeld = interactiveLaunch && EngineConfig.optionKeyHeldAtLaunch()
        self._showRemoteConnectionChooser = State(
            initialValue: EngineConfig.macLaunchConnectionMode(
                optionKeyHeld: optionHeld,
                isInteractiveLaunch: interactiveLaunch
            ) == .remoteConnectionChooser
        )

        // Xcode Previews / Playgrounds host the app to render a single view —
        // skip everything that blocks (modal "Move to Applications?" prompt,
        // saved-library restore that opens DuckDB files). The preview canvas
        // doesn't need either; renders are pure SwiftUI tree walks against
        // mock data.
        if env["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
            || env["XCODE_RUNNING_FOR_PLAYGROUNDS"] == "1"
            || isRunningXCTests() {
            logger.info("FicheroApp.init: preview/playground/XCTest host — skipping installer + library restore")
            return
        }

        // XCUITest smoke run (#1230): the runner launches the real app, so this
        // boot path executes. Skip the modal "Move to Applications?" prompt (it
        // would block the runner) and the saved-library restore (it would open
        // the developer's real libraries). The isolated global library — rooted
        // under FICHERO_UITEST_HOME — still loads lazily via LibraryManager so
        // the window has something to show.
        if isUITesting() {
            openUITestLibraryOverrideIfNeeded()
            return
        }

        let startupClock = Date()
        AppInstaller.promptToMoveToApplicationsIfNeeded()
        let installerMs = Date().timeIntervalSince(startupClock) * 1000
        logger.info("⏱ AppInstaller check: \(installerMs, format: .fixed(precision: 1))ms")

        let restoreStart = Date()
        LibraryManager.shared.restoreSavedLibraries()
        let restoreMs = Date().timeIntervalSince(restoreStart) * 1000
        logger.info("⏱ restoreSavedLibraries: \(restoreMs, format: .fixed(precision: 1))ms")
    }

    // MARK: - File Opening

    private func handleOpenURL(_ url: URL) {
        logger.info("handleOpenURL: \(url.path)")

        // Account invite link (#3157): route to the redeem gate. The token is a
        // secret query param, so it is never logged.
        if let token = SessionStore.inviteToken(from: url) {
            appState.sessionStore.beginInviteRedemption(token: token)
            return
        }

        // Check if this library is already open
        if let existingLibrary = libraryManager.openLibraries.first(where: { $0.url == url }) {
            logger.info("Library already open: \(existingLibrary.displayName)")
            libraryManager.currentLibraryId = existingLibrary.id
        } else {
            // Open the library and add to list
            let library = libraryManager.openLibrary(at: url)
            libraryManager.currentLibraryId = library.id
            logger.info("Opened library: \(library.displayName)")
        }

        // Safari model: just switch the current window, don't open new ones
        // App auto-activates on URL handling
    }

    /// The ONE macOS connect sequence (#3108): used by the launch task AND the
    /// connection view's Retry button, so retry never re-implements `start()`.
    /// `restart` respawns a wedged embedded engine before probing; the launch
    /// path passes false. `start()`'s own re-entrancy guard makes a retry fired
    /// while a start is already in flight a no-op.
    @MainActor
    private func connectBackend(restart: Bool) async {
        // A new window OR native tab shares the app-level connection
        // (`backendService` / `appState` are one @State per app): both are opened
        // via `openWindow(id: "main")` (WindowOpener), so both re-run THIS `.task`
        // and must ATTACH to the already-connected engine, not re-run connect+auth
        // — otherwise the status flips back to `.starting` and the user sees a
        // reconnect spinner + token/registry churn on every surface (#3394/#3407).
        // Window SPLITS never reach here at all: a SplittablePane is an in-window
        // view, not a new scene, so it triggers no connect. Only a not-yet-
        // connected first window or an explicit Retry (`restart`) proceeds.
        if EmbeddedBackendService.shouldReuseExistingConnection(
            restart: restart,
            status: backendService.status,
            isBackendReady: appState.isBackendRunning
        ) {
            logger.info("connectBackend: already connected — new window/tab attaches, no reconnect (#3394/#3407)")
            return
        }
        // Consume the single provisioning decision (#3109) instead of
        // re-deriving the mode here. `connectsToRemoteHost` is the old
        // `requiresExternalBackendConnection` branch.
        let strategy = EngineConfig.engineProvisioningStrategy()
        let usesExternal = strategy.connectsToRemoteHost
        logger.info("Launch provisioning strategy: \(String(describing: strategy), privacy: .public) (#3109)")
        // Back to `.starting` so the connection view shows the booting splash
        // (and clears any prior failure diagnosis) while we probe.
        appState.engine.markStarting()
        backendService.status = .starting
        backendService.errorMessage = nil

        let backendStart = Date()
        do {
            if !usesExternal {
                // Respawn a stuck engine on an explicit retry; a fresh launch
                // just starts. The port pre-flight / orphan sweep lives in start().
                if restart {
                    backendService.stop()
                }
                try await backendService.start()
                let backendMs = Date().timeIntervalSince(backendStart) * 1000
                logger.info("⏱ backendService.start: \(backendMs, format: .fixed(precision: 1))ms")
            }

            // Health probe after the engine is up — re-probing with backoff
            // before parking, so a transient miss while the engine finishes
            // startup (it's often serving 200s a beat later) doesn't wall a
            // healthy engine (#3162).
            await appState.checkBackendHealthUntilReady()
            guard appState.isBackendRunning else {
                backendService.status = .failed
                backendService.errorMessage = appState.backendError
                logger.error(
                    "Backend not reachable at \(EngineConfig.host.absoluteString, privacy: .public)"
                )
                // Keep re-probing in the background so we recover to the workspace
                // the moment the engine answers — never park forever on a healthy
                // engine (#3162). The heartbeat's own guard makes this idempotent.
                appState.startBackendHeartbeat()
                return
            }

            backendService.status = .running
            backendService.errorMessage = nil
            // The heartbeat is the single ongoing poller once ready (#3108); its
            // own guard makes repeated calls idempotent.
            appState.startBackendHeartbeat()
            // Proactively renew the device token if near expiry (#3096), before it
            // can lapse into a 401. A Mac can pair as a remote client too, so this
            // belongs on the macOS connect path as well as iOS — no-op for the
            // embedded/local host (loopback has no stored expiry); a failed renew
            // keeps the old token (the expired → re-pair path is the safety net).
            await DeviceTokenRenewal.renewIfNeeded(host: EngineConfig.host)
            // The one shared post-ready side-effect block (#3113); adopt is a
            // no-op on an embedded/local host, so no `usesExternal` branch here.
            await libraryManager.refreshAfterBackendBecameReady()
        } catch BackendError.portConflict(let pid) {
            // A process we didn't spawn holds :8765 → surface the in-window
            // decision (#3111): Stop it / Use it / Quit. Never a pre-window
            // NSAlert, never self-terminate (#3042).
            logger.info("Port 8765 held by PID \(pid.map(String.init) ?? "unknown") — portConflict phase")
            appState.engine.markPortConflict(pid: pid)
            backendService.status = .failed
        } catch {
            // An adopted squatter that answers health but rejects our token is
            // authRejected, not a generic failure — the authenticated probe is
            // the gate (#2864/#3111).
            if backendService.lastReadiness == .authRejected {
                appState.engine.markAuthRejected(
                    "The engine already on port 8765 rejected this app's credentials."
                )
                backendService.status = .failed
            } else {
                logger.error("Failed to start backend: \(error.localizedDescription)")
                await showBackendError(error)
            }
        }
    }

    @MainActor
    private func showBackendError(_ error: Error) async {
        // Do NOT terminate the app (#3042). The window's BackendRootGate (#2864)
        // already renders the full-window BackendConnectionView — with the error
        // text AND a Retry/Restart button — for any non-usable backend state.
        // A modal Quit here fired BEFORE that gate could show, so a start failure
        // (e.g. Debug ⌘R with no external engine on :8765, where the engine is
        // deliberately not embedded) killed the window instead of surfacing an
        // actionable diagnosis. Flip the service to .failed and let the gate do
        // its job — the window stays up and the user can start the engine + retry.
        logger.error("Backend failed to start: \(error.localizedDescription, privacy: .public)")
        // The single phase owner drives the gate (#3107); service status is kept
        // in sync as secondary lifecycle bookkeeping.
        appState.engine.markFailed(error.localizedDescription)
        backendService.status = .failed
        backendService.errorMessage = error.localizedDescription
    }

    /// The shared library-window root + its environment. Used by BOTH the
    /// primary `id: "main"` window and the value-seeded Duplicate Window group
    /// (#2262), so there is exactly one LibraryWindow scene definition — the
    /// duplicate path reuses it rather than introducing a parallel one.
    @ViewBuilder
    private func libraryWindowRoot(seed: WindowSeed?) -> some View {
        // #2864: the root switches on backend usability. Until the engine is
        // running AND authenticated, the window shows BackendConnectionView
        // (full-window, with diagnosis) instead of LibraryWindow — never a
        // blank window with silent 401s behind the chrome.
        BackendRootGate(
            appState: appState,
            // The connection view's Retry runs the SAME connect sequence as
            // launch, respawning a wedged embedded engine (#3108) — the button
            // no longer re-implements start().
            onRetry: { await connectBackend(restart: true) },
            setup: {
                // `.setupNeeded` never occurs on macOS (the engine is embedded,
                // not paired); render the connection view for symmetry if it does.
                BackendConnectionView(appState: appState)
            },
            content: {
                LibraryWindow(seed: seed)
            }
        )
        .environment(backendService)
        .environment(appState)
        .environment(viewSettings)
        .environment(libraryManager)
        .environment(claimFocusState)
        .environment(kgFocusState)
        .environment(appState.mcpService)
        .frame(minWidth: 640, minHeight: 700)
        // ★ EVERY FRAME PERFECT (#3615): the semantic surface color is the BASE
        // layer under the whole window, so the BackendConnectionView → LibraryWindow
        // → ContentView handoffs (and any first-frame gap while content lays out)
        // read as the app surface, never a bare system-white flash. Matches
        // BackendConnectionView's own fill so the swap is seamless.
        .background(Color(platformColor: .windowBackgroundColor))
    }

    var body: some Scene {
        WindowGroup("Fichero", id: "main") {
            libraryWindowRoot(seed: nil)
                .onOpenURL { url in
                    handleOpenURL(url)
                }
                // #2381: Option-at-launch surfaces the remote-host connection
                // chooser over the main window. A normal launch never sets this,
                // so the embedded local engine path is unchanged.
                .sheet(isPresented: $showRemoteConnectionChooser) {
                    RemoteConnectionChooserSheet(
                        appState: appState,
                        backendService: backendService,
                        libraryManager: libraryManager
                    )
                }
                .task {
                    appDelegate.backendService = backendService
                    // Launch and the Retry button share ONE connect sequence (#3108).
                    await connectBackend(restart: false)
                }
        }
        .defaultSize(width: 1400, height: 900)
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: false))
        .commands {
            #if os(macOS)
            // Replace the default About item with one that opens the custom
            // About window (#2557).
            CommandGroup(replacing: .appInfo) {
                AboutWindowMenuButton()
            }
            #endif
            CommandGroup(after: .appInfo) {
                #if os(macOS)
                Button("Check for Updates...") {
                    SparkleUpdater.shared.checkForUpdates()
                }
                #endif

                // Log out of the multi-user session (#2021/#2022). Only shown
                // when a session is active; clears the Keychain token and drops
                // back to the login gate.
                if appState.sessionStore.phase == .authenticated {
                    Divider()
                    Button(appState.sessionStore.currentUser.map { "Log Out \($0.username)…" } ?? "Log Out…") {
                        Task { await appState.sessionStore.logout() }
                    }
                }

                // Feature Tier Legend — the active build's tier + a window listing
                // each feature's gate. Lives in the App menu: a top-level
                // `CommandGroup(after: .help)` would be the 11th CommandsContent
                // entry, exceeding @CommandsBuilder's 10-arity buildBlock (#3347).
                // Shown only in non-release builds.
                if featureManager.shouldShowTierChrome {
                    Divider()
                    Button(featureManager.buildTierStatusText) {
                        openWindow(id: "feature-tier-legend")
                    }
                }
            }

            // File menu - Database/Library management
            CommandGroup(replacing: .newItem) {
                FileMenuCommands()
                    .environment(libraryManager)
            }

            // Edit menu — ⌘Z drives the audited-action undo (#2015), replacing
            // SwiftUI's view-local UndoManager items so there's exactly one Undo.
            CommandGroup(replacing: .undoRedo) {
                UndoLastActionButton()
            }

            // Edit menu
            CommandGroup(after: .pasteboard) {
                Divider()

                FocusedRenameButton()

                FocusedDeleteButton()
                    .keyboardShortcut(.delete, modifiers: [.command])
            }

            // View menu items
            CommandGroup(after: .toolbar) {
                ViewMenuCommands()
                    .environment(viewSettings)
            }

            CommandGroup(after: .windowArrangement) {
                ActivityWindowMenuButton()
            }

            // View menu: back/forward history (#3581). Slotted into the emptied
            // `.sidebar` group so it costs no @CommandsBuilder arity (already at
            // the 10-entry limit, #3347). Surfaces the per-window AppNavigation
            // history that the toolbar's ⌘'/⌘⇧' buttons already drive.
            CommandGroup(replacing: .sidebar) {
                NavigateBackButton()
                NavigateForwardButton()
            }

            // Data menu — declared after View, before Format
            CommandMenu("Data") {
                FocusedNewFolderButton()

                FocusedImportFilesButton()

                if featureManager.isSearchEnabled
                    || featureManager.isChatEnabled
                    || featureManager.isWorkflowsEnabled {
                    Divider()
                }

                if featureManager.isSearchEnabled {
                    FocusedNewSearchButton()
                }

                if featureManager.isChatEnabled {
                    FocusedNewChatButton()
                }

                if featureManager.isWorkflowsEnabled {
                    FocusedNewWorkflowButton()
                }

                if featureManager.allFeaturesEnabled {
                    FocusedNewComparisonButton()
                    FocusedNewChainButton()
                }

                if featureManager.isAutomationEnabled {
                    Divider()
                    FocusedNewScheduleButton()
                }

                if featureManager.isWorkflowRunOnSelectionEnabled {
                    Divider()
                    FocusedRunWorkflowOnSelectionButton()
                }
            }

            TextFormattingCommands()

        }

        // Duplicate Window (#2262, reform master plan §J): a value-seeded
        // sibling of the primary "Fichero" window. `openWindow(value: WindowSeed)`
        // lands here; LibraryWindow seeds the cloned window's library + selection
        // + lens (the #2273 scene-storage keys) from the WindowSeed before its
        // content mounts. Reuses the exact same LibraryWindow root + environment
        // as the primary window — no parallel scene. Gated in the menu on
        // `@Environment(\.supportsMultipleWindows)`.
        WindowGroup("Fichero", for: WindowSeed.self) { $seed in
            libraryWindowRoot(seed: seed)
        }
        .defaultSize(width: 1400, height: 900)
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: false))

        // Track B (#2003): a detachable artifact-detail scene. Torn off from
        // the inspector's Artifacts tab, it follows the shared FocusedArtifact
        // selection by default (with a pin toggle to park on one artifact).
        // Read-only — it observes FocusedArtifact.shared's resolved snapshot,
        // so it needs no library-service environment plumbing.
        #if os(macOS)
        // Standard About window (#2557), opened from the App menu's About item.
        // Single-instance `Window`, sized to its content.
        Window("About Fichero", id: "about") {
            AboutView()
        }
        .windowResizability(.contentSize)
        .defaultPosition(.center)

        Window("Feature Tier Legend", id: "feature-tier-legend") {
            FeatureTierLegendWindow()
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 420, height: 520)
        .defaultPosition(.center)
        #endif

        WindowGroup("Artifact", id: "artifact-detail") {
            ArtifactDetailWindow()
                .environment(appExecutionObserver)
        }
        .defaultSize(width: 480, height: 620)

        // Track B (#2004): detachable citation detail scene, torn off from the
        // Citations inspector tab and following FocusedCitation.shared by default.
        // Read-only — no library-service environment plumbing needed.
        WindowGroup("Citation", id: "citation-detail") {
            CitationDetailWindow()
                .environment(appExecutionObserver)
        }
        .defaultSize(width: 480, height: 560)

        // Track B (#2010 / #2011): detachable annotation + note detail scenes,
        // each torn off from its inspector tab and following the matching shared
        // focus holder by default. Read-only in the detached scene, so they
        // need no library-service environment plumbing.
        WindowGroup("Annotation", id: "annotation-detail") {
            AnnotationDetailWindow()
                .environment(appExecutionObserver)
        }
        .defaultSize(width: 480, height: 620)

        WindowGroup("Note", id: "note-detail") {
            NoteDetailWindow()
                .environment(appExecutionObserver)
        }
        .defaultSize(width: 480, height: 620)

        WindowGroup("Document", id: "document-detail") {
            DocumentDetailWindow()
                .environment(libraryManager)
                .environment(claimFocusState)
                .environment(kgFocusState)
        }
        .defaultSize(width: 540, height: 720)

        // Activity monitor (#2546 / B2): the poppable live workflow monitor —
        // the window's root IS the hierarchical outline table. Resolves the
        // active library's shared WorkflowExecutionStore via LibraryManager and
        // observes it live; needs libraryManager + the app-level execution
        // observer injected here (env from the main window does not flow into a
        // separate scene). Opened via `openWindow(id: "activity-monitor")`.
        WindowGroup("Activity", id: ActivityWindowSelectionState.monitorWindowID) {
            ActivityMonitorWindow()
                .environment(libraryManager)
                .environment(appExecutionObserver)
        }
        .defaultSize(width: 480, height: 640)

        WindowGroup("Activity Detail", id: ActivityWindowSelectionState.detailWindowID) {
            ActivityDetailWindow()
                .environment(libraryManager)
                .environment(appExecutionObserver)
        }
        .defaultSize(width: 840, height: 640)

        // `Settings` is a SEPARATE Scene: environment objects injected into the
        // main WindowGroup do NOT flow into it. Every object a settings pane
        // reads via @EnvironmentObject must be re-injected here, or its body
        // traps with "No ObservableObject of type … found" the moment the pane
        // is constructed. TabView builds ALL tabs eagerly, so AI's Downloads
        // area (which needs LibraryManager) is constructed on open even when it
        // isn't the front segment — hence the crash guard from #2051.
        Settings {
            SettingsView()
                .environment(appState)
                .environment(backendService)
                .environment(libraryManager)
        }
    }
}

private struct FeatureTierLegendWindow: View {
    @ObservedObject private var featureManager = FeatureManager.shared

    private var orderedTiers: [FeatureTier] {
        FeatureTier.allCases.sorted { $0.rawValue < $1.rawValue }
    }

    private func features(for tier: FeatureTier) -> [FeatureDescriptor] {
        FeatureTiers.map.values
            .filter { $0.tier == tier }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(featureManager.buildTierStatusText)
                    .font(.headline)

                ForEach(orderedTiers, id: \.self) { tier in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 8) {
                            Circle()
                                .fill(tier.legendColor)
                                .frame(width: 10, height: 10)
                            Text(tier.tierBadgeText)
                                .font(.headline)
                            Text("- visible in \(tier.environmentValue) builds and above")
                                .foregroundStyle(.secondary)
                        }

                        ForEach(features(for: tier), id: \.name) { feature in
                            Text(feature.name)
                                .font(.body)
                                .foregroundStyle(.primary)
                        }
                    }
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
#endif
