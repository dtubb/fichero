import AppKit
import OSLog
import SwiftUI

// MARK: - LibraryWindow

/// Main window view - simplified to just track one library per window
struct LibraryWindow: View {
    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var viewSettings: ViewSettings

    @StateObject private var windowState: WindowState

    // App-wide workflow execution observer (uses @Observable, not ObservableObject)
    @State private var executionObserver = WorkflowExecutionObserver()

    @State private var hasInitialized = false
    @State private var showingFileImporter = false
    @SceneStorage("libraryWindow.libraryId") private var persistedLibraryId: String?

    @Environment(\.openWindow) private var openWindow

    let libraryWindowLogger = Logger(subsystem: "ca.tubb.Fichero", category: "LibraryWindow")

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
        case .batches: viewModeName = "Batches"
        case .automation: viewModeName = "Automation"
        case .running: viewModeName = "Running"
        case .history: viewModeName = "History"
        case .issues: viewModeName = "Issues"
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
                .environmentObject(library.savedSearchServiceGenerated)
                .environmentObject(library.searchService)
                .environmentObject(library.conversationServiceGenerated)
                .environmentObject(library.chatServiceGenerated)
                .environmentObject(library.workflowStore)
                .environmentObject(library.workflowServiceGenerated)
                .environmentObject(library.workflowStreamService)
                .environmentObject(library.importService)
                .environmentObject(library.documentServiceGenerated)
                .environmentObject(library.storageService)
                .environmentObject(library.providerService)
                .environmentObject(library.modelService)
                .environmentObject(library.artifactService)
                .environment(executionObserver)
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
        // App-level sheets (providers, MCP servers) - must be here to work when no library is open
        .sheet(isPresented: Binding(
            get: { appState.showProvidersSettings },
            set: { appState.showProvidersSettings = $0 }
        )) {
            ProvidersSettingsSheet()
                .environmentObject(appState)
                .environmentObject(appState.providerService)
        }
        .sheet(isPresented: Binding(
            get: { appState.showAddProvider },
            set: { appState.showAddProvider = $0 }
        )) {
            AddProviderSheet(
                onAdd: {
                    await appState.loadProviders()
                    appState.isFirstLaunchProviderSetup = false
                },
                isFirstLaunch: appState.isFirstLaunchProviderSetup
            )
            .environmentObject(appState.providerService)
        }
        .sheet(isPresented: Binding(
            get: { appState.showMCPServers },
            set: { appState.showMCPServers = $0 }
        )) {
            MCPServersSheet()
                .environmentObject(appState)
                .environmentObject(appState.mcpService)
        }
        // Integrations sheets
        .sheet(isPresented: Binding(
            get: { appState.showFolderWatchers },
            set: { appState.showFolderWatchers = $0 }
        )) {
            IntegrationsPlaceholderSheet(
                title: "Folder Watchers",
                description: "Automatically process files when added to watched folders.",
                icon: "folder.badge.gearshape"
            )
        }
        .sheet(isPresented: Binding(
            get: { appState.showAppObservers },
            set: { appState.showAppObservers = $0 }
        )) {
            IntegrationsPlaceholderSheet(
                title: "App Observers",
                description: "Trigger workflows based on app events (e.g., when files are saved in specific apps).",
                icon: "app.badge"
            )
        }
        .sheet(isPresented: Binding(
            get: { appState.showAutomationRules },
            set: { appState.showAutomationRules = $0 }
        )) {
            IntegrationsPlaceholderSheet(
                title: "Automation Rules",
                description: "Create rules to automatically organize and process documents.",
                icon: "gearshape.2"
            )
        }
        // React to currentLibraryId changes (from Finder open, etc.)
        // Safari model: switch current window to the new library
        .onChange(of: libraryManager.currentLibraryId) { _, newId in
            guard let id = newId,
                  libraryManager.getLibrary(id: id) != nil else { return }

            // Switch this window to the new library
            windowState.libraryId = id
            libraryWindowLogger.info("Switched to library: \(id)")
        }
        .onAppear {
            guard !hasInitialized else { return }
            hasInitialized = true
            initializeWindow()
        }
    }

    // MARK: - Initialization

    private func initializeWindow() {
        libraryWindowLogger.info("""
            initializeWindow - openLibraries=\(libraryManager.openLibraries.count), \
            currentLibraryId=\(libraryManager.currentLibraryId?.uuidString ?? "nil")
            """)

        // Priority 0: Restore the library this scene was showing last time.
        if let persistedLibraryId,
           let restoredId = UUID(uuidString: persistedLibraryId),
           libraryManager.getLibrary(id: restoredId) != nil {
            libraryWindowLogger.info("Restoring persisted libraryId: \(restoredId)")
            assignLibrary(id: restoredId)
            return
        }

        // Priority 1: Use currentLibraryId (set by handleOpenURL or restoreSavedLibraries)
        if let currentId = libraryManager.currentLibraryId,
           libraryManager.getLibrary(id: currentId) != nil {
            libraryWindowLogger.info("Using currentLibraryId: \(currentId)")
            assignLibrary(id: currentId)
            return
        }

        // Priority 2: Use first open library if any exist (restored on app launch)
        if let first = libraryManager.openLibraries.first {
            libraryWindowLogger.info("Using first library: \(first.displayName)")
            assignLibrary(id: first.id)
            return
        }

        // Priority 3: No library - show welcome screen
        libraryWindowLogger.info("No library available - showing welcome screen")
    }

    private func assignLibrary(id: UUID) {
        windowState.libraryId = id
        persistedLibraryId = id.uuidString
        libraryWindowLogger.info("Assigned library: \(id)")
    }

    private func createNewLibrary() {
        let library = libraryManager.createNewLibrary()
        assignLibrary(id: library.id)
        libraryWindowLogger.info("Created and assigned new library: \(library.displayName)")
    }

    // MARK: - Actions

    private func handleFileImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            let library = libraryManager.openLibrary(at: url)
            assignLibrary(id: library.id)
            libraryWindowLogger.info("Opened library: \(library.displayName)")
        case .failure(let error):
            libraryWindowLogger.error("Failed to open library: \(error.localizedDescription)")
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
                libraryWindowLogger.info("Saved library to: \(url.path)")
            } catch {
                libraryWindowLogger.error("Failed to save: \(error.localizedDescription)")
            }
        }
    }
}
