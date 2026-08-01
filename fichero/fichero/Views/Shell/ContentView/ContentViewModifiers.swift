import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentViewModifiers")

// MARK: - View Modifiers

/// Data loading modifiers (initial task + cache rebuilding)
struct DataLoadingModifiers: ViewModifier {
    @Environment(FeatureManager.self) private var featureManager
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
                    if featureManager.isVisible(.workflows) {
                        group.addTask {
                            guard !Task.isCancelled else { return }
                            await workflowStore.loadWorkflows()
                        }
                    }
                    if featureManager.isVisible(.chat) {
                        group.addTask {
                            guard !Task.isCancelled else { return }
                            try? await conversationService.loadConversations()
                        }
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
                .environment(appState.providerService)
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
            // NSItemProvider-based (#4184), not the Transferable
            // `.dropDestination(for: URL.self)` this used to be: Transferable
            // decodes URL via the SAME file-url promise `loadObject(URL.self)`
            // uses, which Finder drags supply but Mail attachment / Safari
            // image-or-PDF / in-progress Downloads drags often don't — those
            // advertise a content UTI only, and only
            // `loadFileRepresentation(forTypeIdentifier:)` reads them. The
            // sidebar row drop target solved this for #587; content-pane drops
            // quietly never had the fix. `ExternalFileDropLoader` is the ONE
            // shared implementation now — a fix to one drag source lands on
            // every drop surface, not just the one that happened to hit it.
            // Root-level drops are classified in handleFileDrop: `.fichero`
            // packages open/focus a window, everything else still imports to
            // Inbox. The 400 error is readable via LocalizedError so the real
            // backend message surfaces (#598).
            .onDrop(of: [.item], isTargeted: $isDropTargeted) { providers in
                guard !providers.isEmpty else { return false }
                Task {
                    var urls: [URL] = []
                    for provider in providers {
                        if let url = try? await ExternalFileDropLoader.loadAnyFileURL(from: provider) {
                            urls.append(url)
                        }
                    }
                    guard !urls.isEmpty else { return }
                    // ponytail: the stable fichero-drop-<uuid> temp copies
                    // `loadFileRepresentation` produces for non-file-url
                    // providers aren't swept here — `handleFileDrop`'s import
                    // Task has no completion signal this closure can await,
                    // and deleting on a fixed timer risks racing a slow copy.
                    // The OS temp directory is purged periodically; add real
                    // cleanup if that turns out not to be good enough.
                    handleFileDrop(urls)
                }
                return true
            }
            // No full-window import overlay — a folder-of-folders import runs
            // long and the dimmed spinner covered the sidebar so nothing
            // appeared until the WHOLE ingest finished (#4065). Progress now
            // streams per-file through the DocumentStore change stream (items
            // populate incrementally) and the trailing status lives in the
            // toolbar's ActivityStatusToolbarItem (#4036), keeping the
            // sidebar visible the whole time. The drop-target highlight stays
            // on the per-row sidebar state.
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

    @Binding var sidebarMode: SidebarMode
    @Binding var viewMode: AppViewMode
    @Binding var browserSelection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var columnVisibility: NavigationSplitViewVisibility
    @Binding var editingWorkflow: Workflow
    @Binding var currentLayoutMode: LayoutMode
    @Binding var isDropTargeted: Bool
    @Binding var isImporting: Bool
    @Binding var importProgress: String?
    @Binding var importError: String?

    /// Last workflow definition this window loaded or the server confirmed — the
    /// baseline that lets cross-window re-sync tell "no unsaved edits" (safe to
    /// overwrite) from "local edits pending" (must not clobber). See #2278 /
    /// `WorkflowSync`.
    @State private var lastSyncedWorkflow: Workflow?
    /// Coalesces the active workflow's graph re-fetch on change-stream bursts
    /// (#2278), independent of the sidebar-list reload task in ContentView.
    @State private var workflowGraphResyncTask: Task<Void, Never>?

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
            // Cross-window / cross-device node-config sync (#2278). A `workflow.*`
            // change bumps the store's `changeToken`; re-fetch the active
            // workflow's full graph through the store (single accessor) and adopt
            // it — guarded so unsaved local edits are never clobbered.
            .onChange(of: workflowStore.changeToken) { _, _ in
                resyncActiveWorkflowGraph()
            }
    }

    /// Re-fetch the currently-edited workflow after a change-stream event and
    /// reconcile it with any local edits (#2278). Coalesced via
    /// `workflowGraphResyncTask` so a burst of `workflow.*` events triggers one
    /// fetch.
    private func resyncActiveWorkflowGraph() {
        guard case .workflow(let item) = viewMode, let item,
              editingWorkflow.id == item.id else { return }
        workflowGraphResyncTask?.cancel()
        workflowGraphResyncTask = Task { @MainActor in
            // Short debounce coalesces an event storm into a single re-fetch.
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            guard let remote = try? await workflowStore.getWorkflow(item.id) else { return }
            guard !Task.isCancelled else { return }
            let remoteWorkflow = Workflow(from: remote)
            switch WorkflowSync.decide(
                remote: remoteWorkflow,
                local: editingWorkflow,
                baseline: lastSyncedWorkflow
            ) {
            case .apply(let workflow):
                editingWorkflow = workflow
                lastSyncedWorkflow = workflow
            case .advanceBaseline(let workflow):
                lastSyncedWorkflow = workflow
            case .skip:
                break
            }
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
                    // Freshly loaded from the server → this IS the baseline for
                    // cross-window re-sync (#2278): no local edits yet.
                    lastSyncedWorkflow = editingWorkflow
                } catch {
                    logger.error("Failed to load workflow: \(error.localizedDescription)")
                    editingWorkflow = Workflow(id: item.id, name: item.name, description: item.description ?? "")
                    lastSyncedWorkflow = nil
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
                // Apply status overrides so failed/processing state survives
                // navigation to single-file gallery — direct assignment was
                // bypassing the override layer that other load paths use,
                // making the red-X workflow-error icon vanish on click-away
                // even though success checkmarks persisted (#791).
                documentStore.currentDocuments =
                    documentStore.applyStatusOverrides([document])
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
        case .chat:
            // Model Comparison lives under the chat sidebar mode. "New
            // Comparison" sets sidebarMode = .chat AND viewMode = .comparison(nil);
            // without this guard the mode-change handler immediately overwrote
            // viewMode back to .chat(nil), so the comparison UI was never
            // reachable (#1475). Preserve an explicitly-set comparison view.
            if case .comparison = viewMode { return }
            viewMode = .chat(nil)
        case .workflows:
            viewMode = .workflow(nil)
        case .automation:
            viewMode = .automation
        case .activity:
            viewMode = .activity(nil)
        case .research, .knowledgeGraph:
            // Research and Knowledge Graph have no ViewMode case; contentView
            // intercepts on sidebarMode == .research / .knowledgeGraph, so leave
            // viewMode untouched.
            break
        }
    }

    private func handleBrowserSelectionChange(_ newSelection: Set<String>) {
        if newSelection.isEmpty {
            detailDocument = nil
            return
        }
        if let firstId = newSelection.first,
           let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }),
           BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
            layoutMode: currentLayoutMode,
            selectedDocumentId: firstId,
            currentDetailDocumentId: detailDocument?.id
           ) {
            detailDocument = doc
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
