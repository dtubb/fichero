import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentTabView")

/// Main view for a document tab/window
/// Switches between different view modes based on document state
struct DocumentTabView: View {
    let libraryId: UUID  // ID of the library this view is displaying
    @Binding var document: FicheroDocument
    let documentURL: URL?  // URL of the .fichero package file
    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager
    @Environment(ViewSettings.self) var viewSettings

    // All services come from the environment (shared per-library, not per-tab)
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(SavedSearchServiceGenerated.self) var savedSearchService
    @Environment(SearchServiceGenerated.self) var searchService
    @Environment(ConversationServiceGenerated.self) var conversationService
    @Environment(ChatServiceGenerated.self) var chatService
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(ImportServiceGenerated.self) var importService
    @Environment(DocumentServiceGenerated.self) var documentService
    @Environment(StorageServiceGenerated.self) var storageService
    @Environment(WorkflowStreamService.self) var workflowStreamService
    @Environment(ResearchService.self) var researchService
    @Environment(WindowState.self) var windowState

    // @Observable objects injected by LibraryWindow — must be forwarded explicitly
    // when ContentView() is constructed below (SwiftUI does not re-propagate
    // @Environment(T.self) values across an explicit .environment() chain).
    @Environment(ArtifactServiceGenerated.self) var artifactService
    @Environment(EntityServiceGenerated.self) var entityService
    @Environment(KGCurationServiceGenerated.self) var kgCurationService
    @Environment(ArtifactStore.self) var artifactStore
    @Environment(EntityStore.self) var entityStore
    @Environment(ClaimStore.self) var claimStore
    @Environment(ClaimFocusState.self) var claimFocusState
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(WorkflowExecutionObserver.self) var executionObserver

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
        // Render-only connection view (#3108): the Retry button re-probes health
        // and, on success, runs the post-ready wiring. The window's root gate is
        // the primary surface for a dead engine; this in-tab fallback is rare.
        BackendConnectionView(appState: appState, onRetry: retryBackendConnection)
    }

    @MainActor
    private func retryBackendConnection() async {
        appState.engine.markStarting()
        await appState.checkBackendHealth()
        guard appState.isBackendRunning else { return }
        await completeBackendRetryReadiness()
    }

    @ViewBuilder
    private var contentView: some View {
        if let apiClient = apiClient {
            switch document.viewMode {
            case .library:
                // Use existing ContentView for now (will extract LibraryTabView later)
                ContentView()
                    .environment(appState)
                    .environment(viewSettings)
                    .environment(apiClient)
                    .environment(documentStore)
                    .environment(savedSearchService)
                    .environment(searchService)
                    .environment(conversationService)
                    .environment(chatService)
                    .environment(workflowStore)
                    .environment(importService)
                    .environment(documentService)
                    .environment(storageService)
                    .environment(workflowStreamService)
                    .environment(researchService)
                    .environment(windowState)
                    // App-wide singletons injected at the ContentView host so
                    // ContentView reads them via environment injection rather
                    // than grabbing `.shared` — the DI seam for #3033. Shared
                    // instances, no new objects created here.
                    .environment(ErrorService.shared)
                    .environmentObject(FeatureManager.shared)
                    // Forward the @Observable artifact service so the library
                    // subtree built after `selectCollection` (LibraryView →
                    // inspector / artifact cells) can read it via
                    // @Environment(ArtifactServiceGenerated.self). Without this,
                    // opening a library or selecting a collection traps with
                    // "No Observable object of type ArtifactServiceGenerated
                    // found." (#3350)
                    .environment(artifactService)
                    // The inspector reads the entity / KG services + stores
                    // from ContentView, not directly from DocumentTabView's
                    // parent environment. Forward them here too so the
                    // inspector still resolves its dependencies during the
                    // first render before windowState.library is available.
                    .environment(entityService)
                    .environment(kgCurationService)
                    .environment(artifactStore)
                    .environment(entityStore)
                    .environment(claimStore)
                    // These app-/library-scoped @Observable focus + substrate
                    // services are also read directly by ContentView. Forward
                    // them here so switching into Research / KG / claim-focused
                    // surfaces never depends on accidental inheritance past the
                    // explicit ContentView() host.
                    .environment(claimFocusState)
                    .environment(kgFocusState)
                    // Forward the @Observable observer so ContentView and its subtree
                    // (DocumentInspector → ArtifactEntityViews) can read it via
                    // @Environment(WorkflowExecutionObserver.self). Without this the
                    // environment chain breaks at the ContentView() host and crashes
                    // with "No Observable object of type WorkflowExecutionObserver found."
                    // (#1561). Single shared instance — no new object created here.
                    .environment(executionObserver)

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

    @MainActor
    private func completeBackendRetryReadiness() async {
        appState.startBackendHeartbeat()
        await KnownLibraryRegistryStore.shared.refresh()
        await libraryManager.backendDidBecomeReady()
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
        .background(Color(platformColor: .windowBackgroundColor))
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
        .background(Color(platformColor: .windowBackgroundColor))
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
        .background(Color(platformColor: .windowBackgroundColor))
    }
}
