import OSLog
import SwiftUI

// MARK: - ContentView Actions Extension
// Agent: ActionsAgent
// Responsibility: All action handlers, event handlers, and business logic methods

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ContentView")

extension ContentView {

    // MARK: - Pane Focus Cycling

    /// Cycle keyboard focus between sidebar, content, and inspector panes
    func cyclePaneFocus(reverse: Bool) {
        var panes: [PaneFocus] = [.sidebar, .content]
        if showsPreviewPane {
            panes.append(.preview)
        }
        if showInspectorSidebar {
            panes.append(.inspector)
        }

        guard let current = focusedPane, let idx = panes.firstIndex(of: current) else {
            // No pane focused — default to content
            focusedPane = .content
            return
        }

        if reverse {
            focusedPane = panes[(idx - 1 + panes.count) % panes.count]
        } else {
            focusedPane = panes[(idx + 1) % panes.count]
        }
    }

    var showsPreviewPane: Bool {
        guard currentLayoutMode != .none else { return false }
        switch viewMode {
        case .library, .search:
            return true
        default:
            return false
        }
    }

    // MARK: - Document Change Handler

    @MainActor
    func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated:
            break

        case .collectionSelected(let collection):
            selectedSidebarItemId = "doc:\(collection.id)"

        case .documentsUpdated:
            break

        case .documentDeleted(let document):
            browserSelection.remove(document.id)
            if detailDocument?.id == document.id {
                detailDocument = nil
            }

        case .documentCreated:
            break
        }
    }

    // MARK: - UI Actions

    func toggleSidebar() {
        withAnimation {
            showSidebar.toggle()
            updateColumnVisibility()
        }
    }

    func updateColumnVisibility() {
        withAnimation {
            // 2-column layout: sidebar + detail (inspector is a panel inside detail).
            columnVisibility = showSidebar ? .all : .detailOnly
        }
    }

    // MARK: - Workflow Actions

    func addNodeFromTool(_ tool: ToolInfo, at position: CGPoint) {
        let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
        editingWorkflow.nodes.append(newNode)
        logger.info("Added node '\(tool.displayName)' at (\(position.x), \(position.y))")
    }

    @MainActor
    func autoSaveWorkflow(workflowId: String, workflow: Workflow) async {
        guard !workflow.nodes.isEmpty || !workflow.name.isEmpty else {
            logger.info("Auto-save skipped: empty workflow")
            return
        }

        logger.info("Auto-saving workflow: \(workflow.name) (id: \(workflowId))")
        for node in workflow.nodes {
            let provider = node.providerName ?? "nil"
            let model = node.modelName ?? "nil"
            print(
                "[DEBUG SAVE] Node \(node.id): providerName=\(provider), modelName=\(model)"
            )
        }
        do {
            var workflowForSave = workflow

            // If sidebar/workflow-store metadata has a newer name, prefer it to prevent
            // stale editor state from clobbering a just-renamed workflow.
            if let canonical = workflowStore.workflows.first(where: { $0.id == workflowId }),
               workflowForSave.name != canonical.name {
                logger.info(
                    "Auto-save name reconciliation: '\(workflowForSave.name)' -> '\(canonical.name)' for \(workflowId)"
                )
                workflowForSave.name = canonical.name
            }

            let definition = workflowForSave.toAPIFormat()
            _ = try await workflowStore.updateWorkflow(definition)
            logger.info("Auto-save completed for workflow: \(workflowId)")
        } catch {
            logger.error("Auto-save failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Navigation

    func navigateToDocument(_ doc: Document) {
        viewMode = .library(doc)
        selectedSidebarItemId = "doc:\(doc.id)"
    }

    @MainActor
    func runWorkflowOnSelection(workflowId: String) {
        let selectedIds = !browserSelection.isEmpty
            ? Array(browserSelection)
            : (detailDocument.map { [$0.id] } ?? [])
        guard !selectedIds.isEmpty else { return }

        let workflowName = workflowStore.workflows.first(where: { $0.id == workflowId })?.name ?? workflowId
        let noun = selectedIds.count == 1 ? "document" : "documents"
        importProgress = "Starting workflow on \(selectedIds.count) \(noun)…"

        executeWorkflowViaSSE(
            workflowId: workflowId,
            workflowName: workflowName,
            docIds: selectedIds
        )
    }

    @MainActor
    func runWorkflowOnCollection(workflowId: String) {
        let collectionIds = documentStore.currentDocuments
            .filter { $0.docType == .file }
            .map { $0.id }
        guard !collectionIds.isEmpty else { return }

        let workflowName = workflowStore.workflows.first(where: { $0.id == workflowId })?.name ?? workflowId
        importProgress = "Starting workflow on \(collectionIds.count) documents in collection…"

        executeWorkflowViaSSE(
            workflowId: workflowId,
            workflowName: workflowName,
            docIds: collectionIds
        )
    }

    /// Shared SSE execution path used by both selection and collection runs.
    /// Registers with executionObserver so Activity view shows live progress.
    @MainActor
    private func executeWorkflowViaSSE(
        workflowId: String,
        workflowName: String,
        docIds: [String]
    ) {
        Task { @MainActor in
            var streamCompleted = false
            do {
                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": docIds],
                    onEvent: { [weak documentStore] event in
                        executionObserver.handleEvent(event, for: workflowId)
                        updateDocumentStatusFromEvent(event, documentStore: documentStore)
                        switch event {
                        case .complete, .error, .systemicError:
                            streamCompleted = true
                        default:
                            break
                        }
                    }
                )

                let threadId = response.threadId
                executionObserver.startExecution(
                    workflowId: workflowId,
                    name: workflowName,
                    threadId: threadId,
                    onCancel: { [weak workflowStreamService] in
                        Task { @MainActor in
                            try? await workflowStreamService?.stopWorkflow(threadId: threadId)
                        }
                    }
                )
                importProgress = nil
                logger.info("Started SSE workflow \(workflowId) thread \(threadId) for \(docIds.count) docs")

                while !streamCompleted {
                    try await Task.sleep(for: .milliseconds(200))
                    if Task.isCancelled { break }
                    if let exec = executionObserver.activeExecutions[workflowId], !exec.isRunning {
                        streamCompleted = true
                    }
                }

                let finalStatus: WorkflowStatus = {
                    guard let exec = executionObserver.activeExecutions[workflowId] else { return .completed }
                    return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
                }()
                executionObserver.endExecution(workflowId: workflowId, status: finalStatus)
                logger.info("Workflow \(workflowId) finished with status: \(String(describing: finalStatus))")

            } catch {
                importProgress = nil
                logger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
                ErrorService.shared.reportError(error)
                executionObserver.endExecution(workflowId: workflowId, status: .failed)
            }
        }
    }

    private func updateDocumentStatusFromEvent(
        _ event: WorkflowStreamEvent,
        documentStore: DocumentStore?
    ) {
        guard let documentStore else { return }
        switch event {
        case .fileStart(_, _, let filePath, _, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .processing)
        case .fileComplete(_, _, let filePath, _, _, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .completed)
        case .fileError(_, _, let filePath, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .failed)
        default:
            break
        }
    }

    // MARK: - Conversations

    func refreshConversations() {
        Task { @MainActor in
            do {
                try await conversationService.loadConversations()
            } catch {
                logger.error("Failed to refresh conversations: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Saved Searches

    func refreshSavedSearches() {
        Task { @MainActor in
            do {
                try await savedSearchService.loadSavedSearches()
            } catch {
                logger.error("Failed to refresh saved searches: \(error.localizedDescription)")
            }
        }
    }

    func runToolbarSearch(_ rawQuery: String) {
        guard featureManager.isSearchEnabled else { return }
        let query = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }

        Task { @MainActor in
            do {
                let saved = try await savedSearchService.saveSearch(
                    query: query,
                    isSmartSearch: true,
                    searchType: "hybrid",
                    sortBy: "relevance",
                    sortDirection: "desc"
                )
                try await savedSearchService.loadSavedSearches()

                let search = SavedSearch(
                    id: saved.id,
                    name: saved.query,
                    query: saved.query,
                    isSmartSearch: saved.isSmartSearch,
                    folderPath: saved.folderPath,
                    sortOrder: saved.sortOrder
                )

                selectedSidebarItemId = "search:\(saved.id)"
                sidebarMode = .search
                viewMode = .search(search)
            } catch {
                logger.error("Toolbar search failed: \(error.localizedDescription)")
            }
        }
    }

    func updateViewDisplayMode(_ requestedMode: ViewDisplayMode) {
        let effectiveMode = normalizedViewDisplayMode(requestedMode)
        if effectiveMode != viewDisplayMode {
            viewDisplayMode = effectiveMode
        }

        viewSettings.libraryLayout = switch effectiveMode {
        case .icon: .icons
        case .list: .list
        case .table: .table
        case .map: .map
        }
        saveDisplayMode(effectiveMode, for: selectedSidebarItemId)
    }

    // MARK: - File Import

    func handleFileDrop(urls: [URL]) {
        logger.info("Files dropped: \(urls.map { $0.lastPathComponent })")

        var targetParentId: String?
        if case .library(let doc) = viewMode {
            targetParentId = doc?.id
        }

        let targetLibrary = LibraryManager.shared.getLibrary(id: windowState.libraryId)
            ?? LibraryManager.shared.globalLibrary

        Task { @MainActor in
            isImporting = true
            importError = nil

            guard let library = targetLibrary else {
                isImporting = false
                importProgress = nil
                importError = "No library available for import."
                logger.error("Run file drop import failed: no target library")
                return
            }

            do {
                _ = try await library.importService.importFiles(
                    urls,
                    mode: .link,
                    parentId: targetParentId
                ) { current, total in
                    importProgress = "Importing \(current) of \(total)..."
                }
                await library.documentStore.refresh()
                logger.info("Successfully imported \(urls.count) dropped item(s)")
            } catch {
                logger.error("Failed dropped import: \(String(describing: error))")
                importError = "Import failed: \(error.localizedDescription)"
            }

            if let importError {
                logger.error("Dropped import ended with error: \(importError)")
            }

            await MainActor.run {
                isImporting = false
                importProgress = nil
            }
        }
    }
}
