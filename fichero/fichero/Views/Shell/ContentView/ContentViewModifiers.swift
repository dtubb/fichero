import OSLog
import SwiftUI

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
    let handleDocumentChange: (DocumentChange) -> Void

    func body(content: Content) -> some View {
        content
            .onChange(of: viewMode) { _, newMode in
                handleViewModeChange(newMode)
            }
            .onChange(of: sidebarMode) { _, newMode in
                handleSidebarModeChange(newMode)
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

/// Import reporting for the window. Deliberately carries NO drop target.
///
/// This modifier attaches where `decoratedNavigationSplitColumn` mounts it
/// (`ContentView+RootLayout.swift`), which wraps the WHOLE
/// `NavigationSplitView` — sidebar column AND detail column both, not the
/// content pane alone. Every drop target ever mounted here has been a defect:
///
///   * `.dropDestination(for: URL.self)` (the original) sat above the sidebar
///     rows and, since #4123 taught a document row to export a real file,
///     resolved an internal drag to that export and re-imported it — a second,
///     hollow copy (#4401).
///   * `6a11a9fc2` replaced it with `.onDrop(of: [.item], isTargeted:)`, which
///     is the exact configuration the comment it replaced said had been TRIED
///     and REVERTED during #4184 for stealing hit-testing from nested rows.
///     `.item` is UTType's root, so it accepted every drag anywhere in the
///     window — including over sidebar rows that have their own handler, and
///     `.onDrop`'s proposal is always COPY, which is where the `+` badge on an
///     intra-library move came from (#4401 reopened, #4520).
///
/// The content-pane drop now lives at `detailColumn` scope ONLY — #4458's ask,
/// and the placement the reverted comment named as the safe one, because the
/// sidebar is not inside the modified view at all. Do not re-add a drop target
/// here: a window-wide acceptor shadows every scoped one beneath it, and which
/// of two overlapping destinations wins is not answerable from source.
struct DropTargetModifiers: ViewModifier {
    @Binding var isImporting: Bool
    @Binding var importProgress: String?
    @Binding var importError: String?

    func body(content: Content) -> some View {
        content
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
    /// The reader's page-focus cursor (#1463): moving it changes which page
    /// the PDF canvas shows WITHOUT re-rooting `detailDocument`. The sidebar
    /// page-click fix (2026-08-08) writes it — see `handleViewModeChange`.
    @Binding var pageFocusDocument: Document?
    @Binding var columnVisibility: NavigationSplitViewVisibility
    @Binding var editingWorkflow: Workflow
    @Binding var currentLayoutMode: LayoutMode
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
    /// The in-flight selection→content load (#4574). Cancelled and replaced
    /// on every selection change: without this, each click spawned an
    /// untracked Task and rapid page-clicks STACKED full loads — the
    /// signposts measured a superseded load still costing 620.8ms on the
    /// main thread. `loadChildren` treats cancellation as a non-failure, so
    /// cancelling the loser is free.
    @State private var selectionLoadTask: Task<Void, Never>?

    let handleDocumentChange: (DocumentChange) -> Void

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
                handleDocumentChange: handleDocumentChange
            ))
            // Note: SheetModifiers removed - app-level sheets now handled in LibraryWindow
            .modifier(DropTargetModifiers(
                isImporting: $isImporting,
                importProgress: $importProgress,
                importError: $importError
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
                selectionLoadTask?.cancel()
                selectionLoadTask = Task {
                    await documentStore.selectCollection(document)
                    guard !Task.isCancelled else { return }
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
                // A sidebar PAGE click must drive the PDF canvas to THAT page
                // (Daniel, 2026-08-08: "the preview for it shows the first
                // page"). This branch never touched the reader state, so the
                // canvas kept the old detailDocument and pdfPageIndex(for:)
                // returned 0 for it. Same seam as reader scroll/click
                // (#1463): move the page-focus cursor; re-root
                // detailDocument only when the page belongs to a DIFFERENT
                // document than the one on canvas.
                if document.docType == .page {
                    pageFocusDocument = document
                    if sidebarPageParentPDFId(for: document) != sidebarDetailPDFId(for: detailDocument) {
                        detailDocument = document
                    }
                }
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

    // handleBrowserSelectionChange DELETED (2026-08-08 night review, finding A):
    // it was a STRIPPED COPY of ContentView.handleBrowserSelectionChange
    // (StateEvents) registered as a SECOND onChange(of: browserSelection) on
    // the same window — every selection click ran both bodies in undefined
    // order and wrote detailDocument twice ("the preview redraws twice on
    // each row"). The full handler in ContentView+RootLayout is the ONE
    // registration; this struct no longer observes browserSelection at all.

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
