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
struct FicheroApp: App {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "FicheroApp")
    // App delegate for lifecycle events
    @NSApplicationDelegateAdaptor(FicheroAppDelegate.self) private var appDelegate

    // Backend service - manages embedded Python backend
    @StateObject private var backendService = EmbeddedBackendService()

    // Backend connection state
    @StateObject private var appState = AppState()
    @StateObject private var viewSettings = ViewSettings()
    @StateObject private var featureManager = FeatureManager.shared
    @StateObject private var claimFocusState = ClaimFocusState.shared
    @State private var kgFocusState = KGFocusState.shared

    // Library manager - singleton managing all open libraries
    @StateObject private var libraryManager = LibraryManager.shared

    init() {
        // Xcode Previews / Playgrounds host the app to render a single view —
        // skip everything that blocks (modal "Move to Applications?" prompt,
        // saved-library restore that opens DuckDB files). The preview canvas
        // doesn't need either; renders are pure SwiftUI tree walks against
        // mock data.
        let env = ProcessInfo.processInfo.environment
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
            logger.info("FicheroApp.init: UI-testing launch — skipping installer + saved-library restore")
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

    @MainActor
    private func showBackendError(_ error: Error) async {
        let alert = NSAlert()
        alert.messageText = "Backend Failed to Start"
        alert.informativeText = error.localizedDescription
        alert.alertStyle = .critical
        alert.addButton(withTitle: "Quit")

        if alert.runModal() == .alertFirstButtonReturn {
            NSApplication.shared.terminate(nil)
        }
    }

    var body: some Scene {
        WindowGroup("Fichero", id: "main") {
            LibraryWindow()
                .environmentObject(backendService)
                .environmentObject(appState)
                .environmentObject(viewSettings)
                .environmentObject(libraryManager)
                .environmentObject(claimFocusState)
                .environment(kgFocusState)
                .environmentObject(appState.mcpService)
                .frame(minWidth: 640, minHeight: 700)
                .onOpenURL { url in
                    handleOpenURL(url)
                }
                .task {
                    appDelegate.backendService = backendService

                    // Start backend on app launch
                    let backendStart = Date()
                    do {
                        try await backendService.start()
                        let backendMs = Date().timeIntervalSince(backendStart) * 1000
                        logger.info("⏱ backendService.start: \(backendMs, format: .fixed(precision: 1))ms")
                        await KnownLibraryRegistryStore.shared.refresh()
                        await libraryManager.backendDidBecomeReady()
                    } catch {
                        logger.error("Failed to start backend: \(error.localizedDescription)")
                        await showBackendError(error)
                    }
                }
        }
        .defaultSize(width: 1400, height: 900)
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: false))
        .commands {
            CommandGroup(after: .appInfo) {
                Button("Check for Updates...") {
                    SparkleUpdater.shared.checkForUpdates()
                }
            }

            // File menu - Database/Library management
            CommandGroup(replacing: .newItem) {
                FileMenuCommands()
                    .environmentObject(libraryManager)
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
                    .keyboardShortcut(.return, modifiers: [])

                FocusedDeleteButton()
                    .keyboardShortcut(.delete, modifiers: [.command])
            }

            // View menu items
            CommandGroup(after: .toolbar) {
                ViewMenuCommands()
                    .environmentObject(viewSettings)
            }

            CommandGroup(replacing: .sidebar) { }

            // Data menu — declared after View, before Format
            CommandMenu("Data") {
                FocusedNewFolderButton()

                FocusedImportFilesButton()

                Divider()

                // Standalone notes browser (#1500)
                Button {
                    appState.showNotesBrowser = true
                } label: {
                    Label("Notes Browser…", systemImage: "note.text")
                }

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

            // Help menu - use default macOS help behavior

            CommandGroup(after: .appSettings) {
                Divider()

                Button {
                    appState.showProvidersSettings = true
                } label: {
                    Label("AI Providers & Models...", systemImage: "cpu")
                }

                if featureManager.isMCPEnabled {
                    Button("MCP Servers...") {
                        appState.showMCPServers = true
                    }
                }

                if featureManager.isIntegrationsEnabled {
                    Divider()

                    // Integrations submenu (Hazel-like folder/app observers)
                    Menu("Integrations") {
                        Button("Folder Watchers...") {
                            appState.showFolderWatchers = true
                        }

                        Button("App Observers...") {
                            appState.showAppObservers = true
                        }

                        Divider()

                        Button("Automation Rules...") {
                            appState.showAutomationRules = true
                        }
                    }
                }
            }
        }

        // Track B (#2003): a detachable artifact-detail scene. Torn off from
        // the inspector's Artifacts tab, it follows the shared FocusedArtifact
        // selection by default (with a pin toggle to park on one artifact).
        // Read-only — it observes FocusedArtifact.shared's resolved snapshot,
        // so it needs no library-service environment plumbing.
        WindowGroup("Artifact", id: "artifact-detail") {
            ArtifactDetailWindow()
        }
        .defaultSize(width: 480, height: 620)

        // Track B (#2004 / #2005): detachable citation + reference detail scenes,
        // each torn off from its inspector tab and following the matching shared
        // focus holder (FocusedCitation / FocusedReference) by default. Read-only,
        // so they need no library-service environment plumbing.
        WindowGroup("Citation", id: "citation-detail") {
            CitationDetailWindow()
        }
        .defaultSize(width: 480, height: 560)

        WindowGroup("Reference", id: "reference-detail") {
            ReferenceDetailWindow()
        }
        .defaultSize(width: 480, height: 560)

        // Track B (#2010 / #2011): detachable annotation + note detail scenes,
        // each torn off from its inspector tab and following the matching shared
        // focus holder by default. Read-only in the detached scene, so they
        // need no library-service environment plumbing.
        WindowGroup("Annotation", id: "annotation-detail") {
            AnnotationDetailWindow()
        }
        .defaultSize(width: 480, height: 620)

        WindowGroup("Note", id: "note-detail") {
            NoteDetailWindow()
        }
        .defaultSize(width: 480, height: 620)

        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}
