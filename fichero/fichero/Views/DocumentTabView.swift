import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentTabView")

/// Main view for a document tab/window
/// Switches between different view modes based on document state
struct DocumentTabView: View {
    let libraryId: UUID  // ID of the library this view is displaying
    @Binding var document: FicheroDocument
    let documentURL: URL?  // URL of the .fichero package file
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var viewSettings: ViewSettings

    // All services come from the environment (shared per-library, not per-tab)
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var savedSearchService: SavedSearchServiceGenerated
    @EnvironmentObject var searchService: SearchServiceGenerated
    @EnvironmentObject var conversationService: ConversationServiceGenerated
    @EnvironmentObject var chatService: ChatServiceGenerated
    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var importService: ImportServiceGenerated
    @EnvironmentObject var documentService: DocumentServiceGenerated
    @EnvironmentObject var storageService: StorageServiceGenerated
    @EnvironmentObject var windowState: WindowState

    // Get the library reference
    private var library: LibraryManager.LibraryReference? {
        LibraryManager.shared.getLibrary(id: libraryId)
    }

    private var apiClient: APIClient? {
        library?.apiClient
    }

    init(libraryId: UUID, document: Binding<FicheroDocument>, documentURL: URL?) {
        self.libraryId = libraryId
        self._document = document
        self.documentURL = documentURL
    }

    var body: some View {
        ZStack {
            if appState.isBackendRunning {
                contentView
            } else {
                backendConnectionView
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            // Library path is already set in LibraryManager when library was opened
            if let apiClient = apiClient {
                let clientIdString = String(describing: ObjectIdentifier(apiClient))
                let pathString = apiClient.currentLibraryPath ?? "none"
                let libraryIdString = String(describing: libraryId)
                logger.info("Using library \(libraryIdString) with APIClient-\(clientIdString), path: \(pathString)")
            }

            // Load data for this tab's context
            await loadContext()
        }
        .onChange(of: document.viewMode) { _, _ in
            // Update last modified when view mode changes
            document.lastModified = Date()
        }
    }

    @ViewBuilder
    private var backendConnectionView: some View {
        BackendConnectionView(appState: appState)
    }

    @ViewBuilder
    private var contentView: some View {
        if let apiClient = apiClient {
            switch document.viewMode {
            case .library:
                // Use existing ContentView for now (will extract LibraryTabView later)
                ContentView()
                    .environmentObject(appState)
                    .environmentObject(viewSettings)
                    .environmentObject(apiClient)
                    .environmentObject(documentStore)
                    .environmentObject(savedSearchService)
                    .environmentObject(searchService)
                    .environmentObject(conversationService)
                    .environmentObject(chatService)
                    .environmentObject(workflowStore)
                    .environmentObject(importService)
                    .environmentObject(documentService)
                    .environmentObject(storageService)
                    .environmentObject(windowState)

            case .workflow:
                // Workflow tab view (will create later)
                WorkflowPlaceholderView()

            case .chat:
                // Chat tab view (will create later)
                ChatPlaceholderView()

            case .search:
                // Search tab view (will create later)
                SearchPlaceholderView()

            case .batches:
                // Unified monitoring view
                ContentUnavailableView(
                    "Activity",
                    systemImage: "clock",
                    description: Text("Batch monitoring is unified under Activity")
                )

            case .automation:
                // Automation view for schedules and triggers
                ContentUnavailableView(
                    "Automation",
                    systemImage: "timer",
                    description: Text("Select a schedule or trigger in the sidebar")
                )

            case .running:
                // Running workflows view
                ContentUnavailableView(
                    "Running Workflows",
                    systemImage: "play.circle",
                    description: Text("Select a running workflow in the sidebar to view progress")
                )

            case .history:
                // Activity history view
                ContentUnavailableView(
                    "Activity History",
                    systemImage: "clock",
                    description: Text("Select a history item in the sidebar to view details")
                )

            case .issues:
                // Issues view
                ContentUnavailableView(
                    "Issues",
                    systemImage: "exclamationmark.triangle",
                    description: Text("Select an issue in the sidebar to view details")
                )
            }
        } else {
            Text("Library not found")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }

    private func loadContext() async {
        // Context loading is handled by individual views via their own .task modifiers
        // This method exists for future cross-view state restoration if needed
    }
}

// MARK: - Placeholder Views

/// Placeholder for Workflow tab (to be implemented)
struct WorkflowPlaceholderView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "arrow.triangle.branch")
                .font(.system(size: 64))
                .foregroundColor(.secondary)

            Text("Workflow Editor")
                .font(.title)

            Text("Coming soon: Workflow tab view")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

/// Placeholder for Chat tab (to be implemented)
struct ChatPlaceholderView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 64))
                .foregroundColor(.secondary)

            Text("Chat")
                .font(.title)

            Text("Coming soon: Chat tab view")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

/// Placeholder for Search tab (to be implemented)
struct SearchPlaceholderView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 64))
                .foregroundColor(.secondary)

            Text("Search")
                .font(.title)

            Text("Coming soon: Search tab view")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}
