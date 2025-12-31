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

    // DocumentStore is shared across all windows/tabs viewing the same library
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var windowState: WindowState

    // Other services are per-tab
    @StateObject private var workflowStore: WorkflowStore
    @StateObject private var conversationService: ConversationService
    @StateObject private var documentService: DocumentService
    @StateObject private var storageService: StorageService
    @StateObject private var importService: ImportService

    // Get the library reference and its APIClient
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

        // Get library's APIClient for per-tab services
        // DocumentStore is injected via environmentObject
        guard let library = LibraryManager.shared.getLibrary(id: libraryId) else {
            // Fallback: create temporary services (should not happen in practice)
            let tempClient = APIClient()
            _workflowStore = StateObject(wrappedValue: WorkflowStore(apiClient: tempClient))
            _conversationService = StateObject(wrappedValue: ConversationService(apiClient: tempClient))
            _documentService = StateObject(wrappedValue: DocumentService(apiClient: tempClient))
            _storageService = StateObject(wrappedValue: StorageService(apiClient: tempClient))
            _importService = StateObject(wrappedValue: ImportService(apiClient: tempClient))
            return
        }

        let client = library.apiClient
        // Create per-tab services
        _workflowStore = StateObject(wrappedValue: WorkflowStore(apiClient: client))
        _conversationService = StateObject(wrappedValue: ConversationService(apiClient: client))
        _documentService = StateObject(wrappedValue: DocumentService(apiClient: client))
        _storageService = StateObject(wrappedValue: StorageService(apiClient: client))
        _importService = StateObject(wrappedValue: ImportService(apiClient: client))
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
                    .environmentObject(conversationService)
                    .environmentObject(importService)
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
                if let collectionId = context.selectedCollectionId {
                    // documentStore.loadCollection(collectionId)
                    // TODO: Implement when integrating with DocumentStore
                }
            }

        case .workflow:
            if let context = document.workflowContext {
                // Load workflow if specified
                if let workflowId = context.workflowId {
                    // workflowStore.loadWorkflow(workflowId)
                    // TODO: Implement when integrating with WorkflowStore
                }
            }

        case .chat:
            if let context = document.chatContext {
                // Load conversation if specified
                if let conversationId = context.conversationId {
                    // conversationService.loadConversation(conversationId)
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
