import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ContentViewModifiers")

// MARK: - View Modifiers

/// Data loading modifiers (initial task + cache rebuilding)
struct DataLoadingModifiers: ViewModifier {
    let documentStore: DocumentStore
    let workflowStore: WorkflowStore
    let conversationService: ConversationService
    let savedSearchService: SavedSearchService

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
    let viewSettings: ViewSettings
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
            .onChange(of: viewSettings.sidebarMode) { _, newMode in
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
            }
            .sheet(isPresented: Binding(
                get: { appState.showProvidersSettings },
                set: { appState.showProvidersSettings = $0 }
            )) {
                ProvidersSettingsSheet()
                    .environmentObject(appState)
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
            .dropDestination(for: URL.self) { urls, _ in
                handleFileDrop(urls)
                return true
            } isTargeted: { isTargeted in
                self.isDropTargeted = isTargeted
            }
            .overlay {
                if isDropTargeted {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.accentColor, lineWidth: 2)
                        .padding(4)
                        .allowsHitTesting(false)
                }
            }
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
    let conversationService: ConversationService
    let savedSearchService: SavedSearchService
    let appState: AppState
    let viewSettings: ViewSettings

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
                viewSettings: viewSettings,
                browserSelection: $browserSelection,
                detailDocument: $detailDocument,
                handleViewModeChange: handleViewModeChange,
                handleSidebarModeChange: handleSidebarModeChange,
                handleBrowserSelectionChange: handleBrowserSelectionChange,
                handleDocumentChange: handleDocumentChange
            ))
            .modifier(SheetModifiers(appState: appState))
            .modifier(DropTargetModifiers(
                isDropTargeted: $isDropTargeted,
                isImporting: $isImporting,
                importProgress: $importProgress,
                importError: $importError,
                handleFileDrop: handleFileDrop
            ))
    }

    private func handleViewModeChange(_ newMode: AppViewMode) {
        logger.info("handleViewModeChange called with mode: \(String(describing: newMode))")

        // Load workflow from API when workflow mode changes
        if case .workflow(let workflowItem) = newMode, let item = workflowItem {
            Task {
                do {
                    let fullWorkflow = try await workflowStore.getWorkflow(item.id)
                    editingWorkflow = Workflow(
                        id: fullWorkflow.id,
                        name: fullWorkflow.name,
                        description: fullWorkflow.description
                    )
                } catch {
                    logger.error("Failed to load workflow: \(error.localizedDescription)")
                    editingWorkflow = Workflow(id: item.id, name: item.name, description: item.description ?? "")
                }
            }
        }

        // Load children from backend when library folder selected
        if case .library(let doc) = newMode, let document = doc {
            // Only load children for folders, not files
            if document.docType == .folder {
                logger.info("Loading children for folder: \(document.name) (id: \(document.id))")
                Task {
                    await documentStore.selectCollection(document)
                    logger.info("selectCollection completed. currentDocuments count: \(documentStore.currentDocuments.count)")
                }
            } else {
                logger.info("Showing single file in gallery: \(document.name)")
                // Show the selected file as a single item in the gallery
                documentStore.currentDocuments = [document]
            }
        } else if case .library(nil) = newMode {
            logger.info("Library mode with no document selected - showing all documents")
        }

        // Always show all 3 columns
        columnVisibility = .all
    }

    private func handleSidebarModeChange(_ newMode: SidebarMode) {
        switch newMode {
        case .navigate:
            if case .library = viewMode { return }
            viewMode = .library(nil)
        case .search:
            viewMode = .search(nil)
        case .chat:
            viewMode = .chat(nil)
        case .workflows:
            viewMode = .workflow(nil)
        case .activity:
            break
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
}
