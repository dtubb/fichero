import SwiftUI
import OSLog
import AppKit

@main
struct FicheroApp: App {
    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "FicheroApp")

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

    var body: some Scene {
        WindowGroup("Fichero", id: "main") {
            LibraryWindow()
                .environmentObject(appState)
                .environmentObject(viewSettings)
                .environmentObject(libraryManager)
                .frame(minWidth: 1000, minHeight: 600)
                .onOpenURL { url in
                    handleOpenURL(url)
                }
        }
        .defaultSize(width: 1200, height: 800)
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

                FocusedNewWorkflowButton()
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

            CommandGroup(replacing: .help) {
                Button("Fichero Help") {
                    // TODO: Implement help documentation
                }

                Divider()

                Button("Check for Updates...") {
                    // TODO: Implement update checking
                }
            }

            CommandGroup(after: .appSettings) {
                Divider()

                Button("Providers...") {
                    appState.showProvidersSettings = true
                }

                Button("Add Provider...") {
                    appState.showAddProviderFromMenu()
                }
            }
        }

        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}

// MARK: - LibraryWindow

/// Main window view - simplified to just track one library per window
struct LibraryWindow: View {
    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var viewSettings: ViewSettings

    @StateObject private var windowState: WindowState

    @State private var hasInitialized = false
    @State private var showingFileImporter = false

    @Environment(\.openWindow) private var openWindow

    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "LibraryWindow")

    init() {
        _windowState = StateObject(wrappedValue: WindowState(libraryId: UUID()))
    }

    private var windowTitle: String {
        guard let library = windowState.library else {
            return "Fichero"
        }

        let viewModeName: String
        switch library.document.viewMode {
        case .library: viewModeName = "Library"
        case .workflow: viewModeName = "Workflow"
        case .chat: viewModeName = "Chat"
        case .search: viewModeName = "Search"
        }

        return "\(library.displayName) > \(viewModeName)"
    }

    private var windowSubtitle: String {
        // Subtitle suppressed - toolbar already shows library name and view mode
        return ""
    }

    var body: some View {
        Group {
            if let library = windowState.library {
                DocumentTabView(
                    libraryId: library.id,
                    document: Binding(
                        get: { library.document },
                        set: { library.document = $0 }
                    ),
                    documentURL: libraryManager.isTemporaryLibrary(library.url) ? nil : library.url
                )
                // Note: Removed .id(library.id) to prevent sidebar flash when switching libraries
                // Environment objects update automatically when windowState.libraryId changes
                .environmentObject(windowState)
                // Inject all library services (one instance per library, shared across tabs)
                .environmentObject(library.documentStore)
                .environmentObject(library.savedSearchService)
                .environmentObject(library.searchService)
                .environmentObject(library.conversationService)
                .environmentObject(library.chatService)
                .environmentObject(library.workflowStore)
                .environmentObject(library.workflowService)
                .environmentObject(library.importService)
                .environmentObject(library.documentService)
                .environmentObject(library.storageService)
                .environmentObject(library.providerService)
                .environmentObject(library.modelService)
            } else {
                // Welcome screen - no library open yet
                WelcomeView(onCreateLibrary: createNewLibrary, onOpenLibrary: { showingFileImporter = true })
            }
        }
        .fileImporter(
            isPresented: $showingFileImporter,
            allowedContentTypes: [.package],
            allowsMultipleSelection: false
        ) { result in
            handleFileImport(result)
        }
        .focusedValue(\.openLibraryAction) { showingFileImporter = true }
        .focusedValue(\.newWindowAction) { handleNewWindow() }
        .focusedValue(\.newLibraryAction) { handleNewLibrary() }
        .focusedValue(\.saveLibraryAction) { handleSaveLibrary() }
        .navigationTitle(windowTitle)
        .navigationSubtitle(windowSubtitle)
        // React to currentLibraryId changes (from Finder open, etc.)
        // Safari model: switch current window to the new library
        .onChange(of: libraryManager.currentLibraryId) { _, newId in
            guard let id = newId,
                  libraryManager.getLibrary(id: id) != nil else { return }

            // Switch this window to the new library
            windowState.libraryId = id
            logger.info("Switched to library: \(id)")
        }
        .onAppear {
            guard !hasInitialized else { return }
            hasInitialized = true
            initializeWindow()
        }
    }

    // MARK: - Initialization

    private func initializeWindow() {
        logger.info("""
            initializeWindow - openLibraries=\(libraryManager.openLibraries.count), \
            currentLibraryId=\(libraryManager.currentLibraryId?.uuidString ?? "nil")
            """)

        // Priority 1: Use currentLibraryId (set by handleOpenURL or restoreSavedLibraries)
        if let currentId = libraryManager.currentLibraryId,
           libraryManager.getLibrary(id: currentId) != nil {
            logger.info("Using currentLibraryId: \(currentId)")
            assignLibrary(id: currentId)
            return
        }

        // Priority 2: Use first open library if any exist (restored on app launch)
        if let first = libraryManager.openLibraries.first {
            logger.info("Using first library: \(first.displayName)")
            assignLibrary(id: first.id)
            return
        }

        // Priority 3: No library - show welcome screen
        logger.info("No library available - showing welcome screen")
    }

    private func assignLibrary(id: UUID) {
        windowState.libraryId = id
        logger.info("Assigned library: \(id)")
    }

    private func createNewLibrary() {
        let library = libraryManager.createNewLibrary()
        assignLibrary(id: library.id)
        logger.info("Created and assigned new library: \(library.displayName)")
    }

    // MARK: - Actions

    private func handleFileImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            let library = libraryManager.openLibrary(at: url)
            assignLibrary(id: library.id)
            logger.info("Opened library: \(library.displayName)")
        case .failure(let error):
            logger.error("Failed to open library: \(error.localizedDescription)")
        }
    }

    private func handleNewWindow() {
        libraryManager.currentLibraryId = windowState.libraryId
        openWindow(id: "main")
    }

    private func handleNewLibrary() {
        let newLibrary = libraryManager.createNewLibrary()
        libraryManager.currentLibraryId = newLibrary.id
        openWindow(id: "main")
    }

    private func handleSaveLibrary() {
        guard let library = windowState.library else { return }

        let savePanel = NSSavePanel()
        savePanel.allowedContentTypes = [.package]
        savePanel.canCreateDirectories = true
        savePanel.nameFieldStringValue = library.displayName + ".fichero"
        savePanel.message = "Choose a location to save your library"

        savePanel.begin { response in
            guard response == .OK, let url = savePanel.url else { return }

            do {
                try libraryManager.saveLibrary(windowState.libraryId, to: url)
                logger.info("Saved library to: \(url.path)")
            } catch {
                logger.error("Failed to save: \(error.localizedDescription)")
            }
        }
    }
}

// MARK: - WelcomeView

struct WelcomeView: View {
    let onCreateLibrary: () -> Void
    let onOpenLibrary: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "doc.richtext")
                .font(.system(size: 64))
                .foregroundColor(.accentColor)

            Text("Welcome to Fichero")
                .font(.largeTitle)
                .fontWeight(.semibold)

            Text("Create a new library or open an existing one to get started.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                Button(action: onCreateLibrary) {
                    Label("New Library", systemImage: "plus")
                }
                .buttonStyle(.borderedProminent)

                Button(action: onOpenLibrary) {
                    Label("Open Library", systemImage: "folder")
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
    }
}
