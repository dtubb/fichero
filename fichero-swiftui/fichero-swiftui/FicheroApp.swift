import SwiftUI
import OSLog
import AppKit

// MARK: - App Delegate

/// Custom AppDelegate to handle app lifecycle events (especially termination)
final class FicheroAppDelegate: NSObject, NSApplicationDelegate, ObservableObject {
    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "FicheroAppDelegate")
    weak var backendService: EmbeddedBackendService?

    func applicationWillTerminate(_ notification: Notification) {
        logger.info("App will terminate - stopping backend...")
        backendService?.stop()
    }
}

@main
struct FicheroApp: App {
    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "FicheroApp")

    // App delegate for lifecycle events
    @NSApplicationDelegateAdaptor(FicheroAppDelegate.self) private var appDelegate

    // Backend service - manages embedded Python backend
    @StateObject private var backendService = EmbeddedBackendService()

    // Backend connection state
    @StateObject private var appState = AppState()
    @StateObject private var viewSettings = ViewSettings()

    // Library manager - singleton managing all open libraries
    @StateObject private var libraryManager = LibraryManager.shared

    // Environment to open windows
    @Environment(\.openWindow) private var openWindow

    init() {
        // Restore libraries synchronously before any windows appear
        LibraryManager.shared.restoreSavedLibraries()
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

    private func handleNewLibrary() {
        let newLibrary = libraryManager.createNewLibrary()
        libraryManager.currentLibraryId = newLibrary.id
        openWindow(id: "main")
        logger.info("Created new library: \(newLibrary.displayName)")
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
                .environmentObject(appState.mcpService)
                .frame(minWidth: 1100, minHeight: 700)
                .onOpenURL { url in
                    handleOpenURL(url)
                }
                .task {
                    // Connect backend service to app delegate for termination handling
                    appDelegate.backendService = backendService

                    // Start backend on app launch
                    do {
                        try await backendService.start()
                        logger.info("Backend started successfully")
                    } catch {
                        logger.error("Failed to start backend: \(error.localizedDescription)")
                        // Show error alert to user
                        await showBackendError(error)
                    }
                }
        }
        .defaultSize(width: 1400, height: 900)
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: true))
        .commands {
            // File menu - Database/Library management
            CommandGroup(replacing: .newItem) {
                Button("New Database") {
                    handleNewLibrary()
                }
                .keyboardShortcut("n", modifiers: [.command])

                FocusedOpenDatabaseButton()

                Divider()

                FocusedNewWindowButton()

                Divider()

                FocusedSaveDatabaseButton()
            }

            // Data menu - Item creation commands
            CommandMenu("Data") {
                FocusedNewFolderButton()

                FocusedImportFilesButton()

                Divider()

                FocusedNewSearchButton()

                FocusedNewChatButton()

                FocusedNewComparisonButton()

                Divider()

                FocusedNewWorkflowButton()

                FocusedNewChainButton()

                Divider()

                FocusedNewScheduleButton()

                FocusedNewTriggerButton()

                Divider()

                FocusedRunWorkflowOnSelectionButton()
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

            // Help menu - use default macOS help behavior
            // Update checking will be added via Sparkle framework when ready for distribution

            CommandGroup(after: .appSettings) {
                Divider()

                Button("AI Providers & Models...") {
                    appState.showProvidersSettings = true
                }

                Button("MCP Servers...") {
                    appState.showMCPServers = true
                }

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

        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}

