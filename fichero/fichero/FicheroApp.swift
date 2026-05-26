import AppKit
import OSLog
import SwiftUI

// MARK: - App Delegate

/// Custom AppDelegate to handle app lifecycle events (especially termination)
final class FicheroAppDelegate: NSObject, NSApplicationDelegate, ObservableObject {
    private let logger = Logger(subsystem: "com.fichero.fichero", category: "FicheroAppDelegate")
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
    private let logger = Logger(subsystem: "com.fichero.fichero", category: "FicheroApp")
    // App delegate for lifecycle events
    @NSApplicationDelegateAdaptor(FicheroAppDelegate.self) private var appDelegate

    // Backend service - manages embedded Python backend
    @StateObject private var backendService = EmbeddedBackendService()

    // Backend connection state
    @StateObject private var appState = AppState()
    @StateObject private var viewSettings = ViewSettings()
    @StateObject private var featureManager = FeatureManager.shared
    @StateObject private var claimFocusState = ClaimFocusState.shared

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
                .environmentObject(appState.mcpService)
                .frame(minWidth: 1100, minHeight: 700)
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
                FocusedNewDatabaseButton()

                FocusedOpenDatabaseButton()

                Divider()

                FocusedNewWindowButton()

                Divider()

                FocusedSaveDatabaseButton()
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

        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}
