import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "DocumentTabView")

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
    @EnvironmentObject var savedSearchService: SavedSearchService
    @EnvironmentObject var searchService: SearchService
    @EnvironmentObject var conversationService: ConversationService
    @EnvironmentObject var chatService: ChatService
    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var importService: ImportService
    @EnvironmentObject var documentService: DocumentService
    @EnvironmentObject var storageService: StorageService
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
        .onChange(of: document.viewMode) { _, newMode in
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
            }
        } else {
            Text("Library not found")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }

    private func loadContext() async {
        // Load appropriate data based on document.viewMode
        switch document.viewMode {
        case .library:
            if let context = document.libraryContext {
                // Load collection if specified
                if context.selectedCollectionId != nil {
                    // documentStore.loadCollection(context.selectedCollectionId!)
                    // TODO: Implement when integrating with DocumentStore
                }
            }

        case .workflow:
            if let context = document.workflowContext {
                // Load workflow if specified
                if context.workflowId != nil {
                    // workflowStore.loadWorkflow(context.workflowId!)
                    // TODO: Implement when integrating with WorkflowStore
                }
            }

        case .chat:
            if let context = document.chatContext {
                // Load conversation if specified
                if context.conversationId != nil {
                    // conversationService.loadConversation(context.conversationId!)
                    // TODO: Implement when integrating with ConversationService
                }
            }

        case .search:
            // Search doesn't need to load anything upfront
            break
        }
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
