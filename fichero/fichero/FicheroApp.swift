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

/// Custom AppDelegate — the APP-scoped owner of the engine lifecycle (#3945).
/// The engine is started here in `applicationDidFinishLaunching` and stopped in
/// `applicationWillTerminate`, NOT from a window's `.task`. Opening or closing a
/// window is not an engine event; windows read the controller off the delegate
/// and observe its `EngineSession` phase, they never trigger it.
@MainActor
final class FicheroAppDelegate: NSObject, NSApplicationDelegate, ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroAppDelegate")

    /// The single app-scoped engine lifecycle controller (#3945). Owns the
    /// spawn/watch/stop (`EmbeddedBackendService`) and the connect/probe/heartbeat
    /// (`AppState`) halves; `EngineSession` inside it is the sole phase writer.
    let controller = EngineLifecycleController()

    func applicationDidFinishLaunching(_ notification: Notification) {
        // The unit-test host must never start a real engine (#3902).
        guard !isRunningXCTests() else { return }
        logger.info("App did finish launching — starting engine app-scoped (#3945)")
        LaunchProfile.milestone("applicationDidFinishLaunching")
        // The engine's async startup lives here, not in a scene `.task`: `@main
        // App.init` is synchronous and `.task` is per-scene, so the delegate is the
        // one app-level hook that fires exactly once, independent of any window.
        Task { await controller.start() }
    }

    /// True once a quit has been accepted, so a second ⌘Q (or a Dock quit while
    /// the teardown is in flight) doesn't start a second teardown or double
    /// `reply(toApplicationShouldTerminate:)`.
    private var isTerminatingWithDeferredTeardown = false

    /// #4291: quit must be instant from the user's side. The old path did the
    /// whole teardown inside `applicationWillTerminate` — which included
    /// SIGTERM-then-`Thread.sleep`-poll for up to 5s on the MAIN thread — so ⌘Q
    /// beachballed for as long as the engine took to exit.
    ///
    /// The Mac-correct shape: accept the quit with `.terminateLater`, run the
    /// teardown off-main under a hard deadline (`TerminationDeadlinePolicy`),
    /// escalate SIGTERM → SIGKILL past it, and reply either way. Nothing is lost
    /// by not waiting longer: the engine's own `FICHERO_PARENT_PID` watchdog
    /// self-terminates any child that outlives us.
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        // The unit-test host never spawned an engine (see
        // `applicationDidFinishLaunching`), so there is nothing to tear down and
        // an unanswered `.terminateLater` would hang the harness.
        guard !isRunningXCTests() else { return .terminateNow }
        guard !isTerminatingWithDeferredTeardown else { return .terminateLater }
        isTerminatingWithDeferredTeardown = true

        logger.info("Quit requested — deferring termination for bounded engine teardown (#4291)")
        Task {
            // `stopAndAwaitExit` signals on the main actor and then polls off it
            // with `Task.sleep`, so the run loop keeps drawing/servicing events
            // while the child exits.
            await controller.stopAndAwaitExit()
            logger.info("Engine teardown finished (or deadline spent) — replying terminate (#4291)")
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    func applicationWillTerminate(_ notification: Notification) {
        logger.info("App will terminate - stopping backend...")
        // Backstop only: `applicationShouldTerminate` has normally already reaped
        // the child, which clears the tracked pid and makes this a no-op. It still
        // matters for termination paths that skip `shouldTerminate` (e.g. a
        // programmatic `NSApp.terminate` short-circuit or the test host).
        controller.stop()
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        true
    }
}

@main
struct FicheroApp: App {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroApp")
    @Environment(\.openWindow) private var openWindow
    // App delegate for lifecycle events
    @NSApplicationDelegateAdaptor(FicheroAppDelegate.self) private var appDelegate

    // The engine lifecycle is app-owned (#3945): the AppDelegate holds the single
    // EngineLifecycleController. These read its instances so the whole App body —
    // every appState/backendService reference and the .environment injections —
    // stays unchanged, while ownership + startup move to the delegate. @Observable
    // objects are tracked wherever their properties are read in body; @State is
    // only about ownership/lifetime, which now belongs to the controller.
    private var backendService: EmbeddedBackendService { appDelegate.controller.backendService }
    private var appState: AppState { appDelegate.controller.appState }
    @State private var viewSettings = ViewSettings()
    private let featureManager = FeatureManager.shared
    @State private var claimFocusState = ClaimFocusState.shared
    @State private var kgFocusState = KGFocusState.shared

    // Library manager - the app-owned controller holds the shared singleton (#3945).
    private var libraryManager: LibraryManager { appDelegate.controller.libraryManager }

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
        // #4227: engine -> server rename; copy the saved host forward before
        // any store reads the canonical key.
        EngineConfig.migrateLegacyHostKeyIfNeeded()
        // #2381: decide the launch connection mode BEFORE any early return so
        // this @State is initialized on every path. A normal launch uses the
        // embedded local engine; holding Option surfaces the remote-host chooser.
        let env = ProcessInfo.processInfo.environment
        // #3968: `isUITesting()` is also true in embedded-engine UI-test mode
        // (which is *defined* as `isUITesting() && hasFlag`), but that mode is
        // supposed to launch the real engine interactively. The carve-out lives
        // in ONE predicate now — `suppressesBootSideEffectsForUITesting()` —
        // rather than being spelled out both here and in
        // `currentEngineProvisioningInputs`, with nothing forcing the two to agree.
        let interactiveLaunch = !(env["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
            || env["XCODE_RUNNING_FOR_PLAYGROUNDS"] == "1"
            || isRunningXCTests()
            || suppressesBootSideEffectsForUITesting())
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

        // XCUITest run (#1230): open an explicit fixture in either mode. The
        // non-embedded path then skips installer and saved-library side effects;
        // embedded tests continue so they can launch the bundled engine.
        if isUITesting() {
            openUITestLibraryOverrideIfNeeded()
            if !isEmbeddedEngineUITesting() { return }
        }

        // Materialize saved libraries BEFORE the scene graph builds (launch
        // speed, #4036): the first window frame then mounts the real library
        // shell instead of `noLibraryView`. This no longer races the engine
        // bind — restore is local-only now; data loads and registry writes
        // defer/fail-soft until the authenticated probe flips ready (see
        // `restoreSavedLibraries`'s doc comment).
        //
        // NOT in embedded-engine UI-test mode: that path reaches here (its
        // early-return above is carved out on purpose), but restoring would
        // open the DEVELOPER'S real saved libraries into the test app — the
        // harness seeds its own library through the engine registry instead.
        if !isUITesting() {
            LibraryManager.shared.restoreSavedLibraries()
            LaunchProfile.milestone("saved libraries materialized (pre-ready)")
        }
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

        // Pairing link (#3788). The app MINTS fichero:// links, offers Copy and
        // Share buttons for them, and iOS has a full receive path — but macOS fell
        // through to `openLibrary(at:)` and tried to open "fichero://pair?…" as a
        // LIBRARY FOLDER. So a tapped link did nothing (and the scheme was not even
        // registered — see Info.plist CFBundleURLTypes, added in the same commit).
        //
        // It does NOT pair silently: pairing repoints this Mac at a remote host, so
        // the link prefills the existing pairing field and the user presses Connect.
        // Accepts both fichero://pair and the https://fichero.app/pair universal
        // link (#3791) so a tapped invite works even where the scheme isn't
        // registered.
        if RemoteClientPairing.isPairingInviteLink(url) {
            logger.info("handleOpenURL: pairing link received")  // never log the payload
            appState.pendingPairingInvite = url.absoluteString
            appState.openSettings(tab: .backend)
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

    /// The shared library-window root + its environment. Used by BOTH the
    /// primary `id: "main"` window and the value-seeded Duplicate Window group
    /// (#2262), so there is exactly one LibraryWindow scene definition — the
    /// duplicate path reuses it rather than introducing a parallel one.
    @ViewBuilder
    private func libraryWindowRoot(seed: WindowSeed?) -> some View {
        // #2864/#3107: the root switches on the single `engine.phase` sum
        // type — one authoritative "is the backend usable" decision, not
        // ANDed booleans. `.setupNeeded` (iOS first-run pairing; never on
        // macOS, where the engine is embedded) renders BackendConnectionView.
        // Every other phase — `.starting`, `.ready`, and all failure phases
        // (`.portConflict` / `.authRejected` / `.unreachable` / `.failed`) —
        // renders LibraryWindow content immediately; per #4036 those
        // failures surface as toolbar chrome (`EngineStatusToolbarItem`),
        // not a full-window takeover, and a mid-session drop that exhausts
        // restarts raises the `appState.showBackendDropModal` alert (#4064).
        // The full-window BackendConnectionView is no longer the failure
        // surface, so the real UI is never hidden behind a connect splash.
        BackendRootGate(
            appState: appState,
            // The connection view's Retry runs the SAME connect sequence as
            // launch, respawning a wedged embedded engine (#3108) — the button
            // no longer re-implements start().
            onRetry: { await appDelegate.controller.retry() },
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
        .environment(featureManager)
        .environment(claimFocusState)
        .environment(kgFocusState)
        .environment(appState.mcpService)
        // Same retry closure as `onRetry` above, threaded via the environment
        // so `EngineStatusToolbarItem` (inside `content()`, which now renders
        // during `.starting` / failures too — #startup-transport-ux S1) can
        // offer Retry without re-implementing `start()` (#3108).
        .environment(\.engineRetry, { await appDelegate.controller.retry() })
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
            // The engine is started by FicheroAppDelegate.applicationDidFinishLaunching,
            // NOT here (#3945). A window no longer triggers connect/auth — it only
            // observes EngineSession — so opening a second window/tab can't re-run
            // the sequence, which is what shouldReuseExistingConnection existed to
            // suppress (#3394/#3407). That guard is now unreachable from the app.
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
                // Sparkle auto-update is the DMG/Developer-ID channel only. The
                // Mac App Store forbids Sparkle's helpers and does its own
                // updates, so the MAS build (which defines APP_STORE and doesn't
                // link Sparkle) hides this item (#3340). No-op on Dev/Release,
                // which never define APP_STORE — those keep the update item.
                #if os(macOS) && !APP_STORE
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
                // ⌘A, routed by focus (#4376). Declared AFTER the system
                // pasteboard group on purpose: menu key equivalents match in
                // menu order, and this item disables itself whenever the app
                // has no business claiming ⌘A — so the reader's WebKit surface
                // still gets its own select-all through the responder chain.
                SelectAllButton()

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

            // Go menu (#4121, Finder's Go/View split): Back/Forward/Go Up
            // leave the View menu. ONE CommandsBuilder element (arity is at
            // the 10-entry cap, #3347) composing the menu + the .sidebar
            // replacement that keeps the system sidebar items suppressed.
            GoMenuCommands()

            // Data menu — declared after View, before Format
            CommandMenu("Data") {
                FocusedNewFolderButton()

                FocusedImportFilesButton()

                if featureManager.isChatEnabled
                    || featureManager.isWorkflowsEnabled {
                    Divider()
                }

                if featureManager.isChatEnabled {
                    FocusedNewChatButton()
                }

                if featureManager.isWorkflowsEnabled {
                    FocusedNewWorkflowButton()
                }

                if featureManager.allFeaturesEffectivelyEnabled {
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

            // One CommandsBuilder element (arity limit): Format's system
            // commands + Show Ruler, which lives in Format not View (#4121
            // View-menu diet — TextEdit/Pages precedent).
            FormatMenuCommands()

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
                .environment(appState)
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
                // The Settings scene is separate — inject the SAME app-wide
                // ViewSettings the main window uses so the per-view panes (#3680)
                // edit the live view config, not a detached copy.
                .environment(viewSettings)
                // Same reasoning for the feature flags (#3033/#3034): the panes now
                // read @Environment(FeatureManager.self) var featureManager instead of
                // grabbing FeatureManager.shared themselves, so the scene must inject it.
                // A singleton is legitimate at the composition root — not in a pane.
                .environment(FeatureManager.shared)
        }
    }
}

private struct FeatureTierLegendWindow: View {
    private let featureManager = FeatureManager.shared

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
                            // Legend teaches the glyph (#4122): "β BETA".
                            Text(
                                tier.tierBadgeGlyph.isEmpty
                                    ? tier.tierBadgeText
                                    : "\(tier.tierBadgeGlyph) \(tier.tierBadgeText)"
                            )
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
