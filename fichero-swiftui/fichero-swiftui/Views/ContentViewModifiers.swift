import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ContentViewModifiers")

// MARK: - View Modifiers

/// Data loading modifiers (initial task + cache rebuilding)
struct DataLoadingModifiers: ViewModifier {
    let documentStore: DocumentStore
    let workflowStore: WorkflowStore
    let conversationService: ConversationServiceGenerated
    let savedSearchService: SavedSearchServiceGenerated

    func body(content: Content) -> some View {
        content
            .task {
                await withTaskGroup(of: Void.self) { group in
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        await documentStore.loadCollections()
                    }
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        await workflowStore.loadWorkflows()
                    }
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        try? await conversationService.loadConversations()
                    }
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        try? await savedSearchService.loadSavedSearches()
                    }
                }
            }
    }
}

/// Change handler modifiers (view mode, sidebar mode, browser selection)
struct ChangeHandlerModifiers: ViewModifier {
    let documentStore: DocumentStore
    @Binding var viewMode: AppViewMode
    @Binding var sidebarMode: SidebarMode
    @Binding var browserSelection: Set<String>
    @Binding var detailDocument: Document?

    let handleViewModeChange: (AppViewMode) -> Void
    let handleSidebarModeChange: (SidebarMode) -> Void
    let handleBrowserSelectionChange: (Set<String>) -> Void
    let handleDocumentChange: (DocumentChange) -> Void

    func body(content: Content) -> some View {
        content
            .onChange(of: viewMode) { _, newMode in
                handleViewModeChange(newMode)
            }
            .onChange(of: sidebarMode) { _, newMode in
                handleSidebarModeChange(newMode)
            }
            .onChange(of: browserSelection) { _, newSelection in
                handleBrowserSelectionChange(newSelection)
            }
            .onReceive(
                documentStore.documentChangePublisher
                    .replaceError(with: DocumentChange.collectionsUpdated([]))
            ) { change in
                handleDocumentChange(change)
            }
    }
}

/// Sheet modifiers (provider sheets)
struct SheetModifiers: ViewModifier {
    let appState: AppState

    func body(content: Content) -> some View {
        content
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
                get: { appState.showProvidersSettings },
                set: { appState.showProvidersSettings = $0 }
            )) {
                ProvidersSettingsSheet()
                    .environmentObject(appState)
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
    }
}

/// Drop target and import overlays
struct DropTargetModifiers: ViewModifier {
    @Binding var isDropTargeted: Bool
    @Binding var isImporting: Bool
    @Binding var importProgress: String?
    @Binding var importError: String?
    let handleFileDrop: ([URL]) -> Void

    func body(content: Content) -> some View {
        content
            // Transferable API — does not interfere with hit testing on sidebar
            // icon/text rows the way .onDrop(of:) does. Root-level drops are
            // routed to Inbox in handleFileDrop; the 400 error is now readable
            // via LocalizedError so the real backend message surfaces (#598).
            .dropDestination(for: URL.self) { urls, _ in
                handleFileDrop(urls)
                return true
            } isTargeted: { isTargeted in
                self.isDropTargeted = isTargeted
            }
            // No full-window highlight overlay — sidebar folder rows show their own
            // per-folder drop targeting via SidebarItemRow's isDropTargeted state.
            .overlay {
                if isImporting {
                    ZStack {
                        Color.black.opacity(0.3)
                        VStack(spacing: 12) {
                            ProgressView()
                                .scaleEffect(1.2)
                            if let progress = importProgress {
                                Text(progress)
                                    .foregroundColor(.white)
                            }
                        }
                        .padding(20)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(8)
                    }
                    .allowsHitTesting(false)
                }
            }
            .alert("Import Error", isPresented: .constant(importError != nil)) {
                Button("OK") {
                    importError = nil
                }
            } message: {
                if let error = importError {
                    Text(error)
                }
            }
    }

}

/// Splits mainContentView modifiers into a separate struct to avoid compiler timeout
struct MainContentModifiers: ViewModifier {
    let documentStore: DocumentStore
    let workflowStore: WorkflowStore
    let conversationService: ConversationServiceGenerated
    let savedSearchService: SavedSearchServiceGenerated
    let appState: AppState

    @Binding var sidebarMode: SidebarMode
    @Binding var viewMode: AppViewMode
    @Binding var selectedSidebarItemId: String?
    @Binding var browserSelection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var columnVisibility: NavigationSplitViewVisibility
    @Binding var editingWorkflow: Workflow
    @Binding var isDropTargeted: Bool
    @Binding var isImporting: Bool
    @Binding var importProgress: String?
    @Binding var importError: String?

    let handleDocumentChange: (DocumentChange) -> Void
    let handleFileDrop: ([URL]) -> Void

    func body(content: Content) -> some View {
        content
            .modifier(DataLoadingModifiers(
                documentStore: documentStore,
                workflowStore: workflowStore,
                conversationService: conversationService,
                savedSearchService: savedSearchService
            ))
            .modifier(ChangeHandlerModifiers(
                documentStore: documentStore,
                viewMode: $viewMode,
                sidebarMode: $sidebarMode,
                browserSelection: $browserSelection,
                detailDocument: $detailDocument,
                handleViewModeChange: handleViewModeChange,
                handleSidebarModeChange: handleSidebarModeChange,
                handleBrowserSelectionChange: handleBrowserSelectionChange,
                handleDocumentChange: handleDocumentChange
            ))
            // Note: SheetModifiers removed - app-level sheets now handled in LibraryWindow
            .modifier(DropTargetModifiers(
                isDropTargeted: $isDropTargeted,
                isImporting: $isImporting,
                importProgress: $importProgress,
                importError: $importError,
                handleFileDrop: handleFileDrop
            ))
            .onChange(of: workflowStore.workflows) { _, updatedWorkflows in
                syncActiveWorkflowMetadata(with: updatedWorkflows)
            }
    }

    private func handleViewModeChange(_ newMode: AppViewMode) {
        logger.info("handleViewModeChange called with mode: \(String(describing: newMode))")

        // Load workflow from API when workflow mode changes
        if case .workflow(let workflowItem) = newMode, let item = workflowItem {
            // Keep editable metadata aligned immediately to avoid rename races while
            // the full workflow payload is loading asynchronously.
            if editingWorkflow.id == item.id {
                editingWorkflow.name = item.name
                editingWorkflow.description = item.description ?? ""
            }

            Task {
                do {
                    let fullWorkflow = try await workflowStore.getWorkflow(item.id)
                    // Use the initializer that copies ALL fields (nodes, edges, provider, model, etc.)
                    editingWorkflow = Workflow(from: fullWorkflow)
                } catch {
                    logger.error("Failed to load workflow: \(error.localizedDescription)")
                    editingWorkflow = Workflow(id: item.id, name: item.name, description: item.description ?? "")
                }
            }
        }

        // Load children from backend when a library container is selected.
        // Containers = folders (contents) + PDFs (pages, per #568/#570). Using
        // Document.isNavigableContainer keeps this check in sync with
        // double-click routing and sidebar-filter semantics — one property,
        // one definition of "container." Everything else (plain files) shows
        // as a single item in the gallery.
        if case .library(let doc) = newMode, let document = doc {
            if document.isNavigableContainer {
                logger.info("Loading children for container: \(document.name) (id: \(document.id))")
                Task {
                    await documentStore.selectCollection(document)
                    detailDocument = document
                    let docCount = documentStore.currentDocuments.count
                    logger.info("selectCollection completed. currentDocuments count: \(docCount)")
                }
            } else {
                logger.info("Showing single file in gallery: \(document.name)")
                documentStore.currentDocuments = [document]
            }
        } else if case .library(nil) = newMode {
            logger.info("Library mode with no document selected - showing all documents")
        }

    }

    private func handleSidebarModeChange(_ newMode: SidebarMode) {
        switch newMode {
        case .library:
            if case .library = viewMode { return }
            viewMode = .library(nil)
        case .search:
            viewMode = .search(nil)
        case .chat:
            viewMode = .chat(nil)
        case .workflows:
            viewMode = .workflow(nil)
        case .automation:
            viewMode = .automation
        case .activity:
            viewMode = .activity(nil)
        }
    }

    private func handleBrowserSelectionChange(_ newSelection: Set<String>) {
        if let firstId = newSelection.first,
           let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }) {
            detailDocument = doc
        } else if newSelection.isEmpty {
            detailDocument = nil
        }
    }

    private func syncActiveWorkflowMetadata(with updatedWorkflows: [WorkflowSidebarItem]) {
        guard case .workflow(let selectedWorkflow) = viewMode,
              let selectedWorkflow,
              let canonical = updatedWorkflows.first(where: { $0.id == selectedWorkflow.id }) else {
            return
        }

        if selectedWorkflow != canonical {
            viewMode = .workflow(canonical)
        }

        if editingWorkflow.id == canonical.id {
            editingWorkflow.name = canonical.name
            editingWorkflow.description = canonical.description ?? ""
        }
    }
}
