import OSLog
import SwiftUI

// MARK: - Filter, Selection, and Batch Extension

extension LibraryView {
    private var logger: Logger {
        Logger(subsystem: "com.tubb.Fichero", category: "LibraryView")
    }

    var libraryWorkflows: [WorkflowSidebarItem] {
        let lib = libraryManager.getLibrary(id: windowState.libraryId) ?? libraryManager.globalLibrary
        return lib?.workflowStore.workflows ?? []
    }

    // MARK: - Filtered Documents

    var filteredDocuments: [Document] {
        var docs = documents
        if !searchText.isEmpty {
            docs = docs.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) ||
                    ($0.pageContent?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                    $0.status.rawValue.localizedCaseInsensitiveContains(searchText)
            }
        }
        return docs.sorted(using: sortOrder)
    }

    // MARK: - Filter Bar

    var filterBarView: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                    .font(.system(size: 12))

                TextField("Filter", text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .focused($filterFieldFocused)

                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }

                Button("Done") {
                    searchText = ""
                    showFilterBar = false
                }
                .buttonStyle(.borderless)
                .font(.system(size: 12))
                .keyboardShortcut(.escape, modifiers: [])
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.bar)

            Divider()
        }
    }

    // MARK: - Empty State

    var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
                .controlSize(.large)

            Text("Loading Documents...")
                .font(.headline)

            Text("Connecting to library data")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    func errorState(message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 40))
                .foregroundColor(.orange)

            Text("Couldn’t Load Documents")
                .font(.headline)

            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)

            Button("Retry") {
                onRetry()
            }
            .keyboardShortcut("r", modifiers: .command)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("No Documents")
                .font(.headline)

            if !searchText.isEmpty {
                Text("No results for \"\(searchText)\"")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            } else {
                Text("Select a collection to view documents")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Tap Handling

    func canNavigateInto(_ doc: Document) -> Bool {
        doc.isNavigableContainer
    }

    /// Handle double-click: navigate into folders/PDFs, preview everything else.
    func handleDoubleClick(_ doc: Document) {
        if canNavigateInto(doc) {
            onNavigateInto(doc)
        } else {
            detailDocument = doc
        }
    }

    func handleTap(_ doc: Document) {
        onRequestFocus()
        let modifiers = NSEvent.modifierFlags
        if modifiers.contains(.shift), let anchor = selectionAnchor {
            // Shift+click: range select from anchor to clicked item
            let docs = filteredDocuments
            if let anchorIndex = docs.firstIndex(where: { $0.id == anchor }),
               let clickIndex = docs.firstIndex(where: { $0.id == doc.id }) {
                let range = min(anchorIndex, clickIndex)...max(anchorIndex, clickIndex)
                let rangeIds = Set(docs[range].map(\.id))
                if modifiers.contains(.command) {
                    // Shift+Cmd+click: add range to existing selection
                    selection.formUnion(rangeIds)
                } else {
                    // Shift+click: replace selection with range
                    selection = rangeIds
                }
            }
            // Don't update anchor on Shift+click
        } else if modifiers.contains(.command) {
            // Cmd+click: toggle individual item
            if selection.contains(doc.id) {
                selection.remove(doc.id)
            } else {
                selection.insert(doc.id)
            }
            selectionAnchor = doc.id
        } else {
            // Plain click: replace selection
            selection = [doc.id]
            selectionAnchor = doc.id
        }
    }

    // MARK: - Context Menu

    @ViewBuilder
    func documentContextMenu(for document: Document) -> some View {
        Button {
            startRename(for: document)
        } label: {
            Label("Rename", systemImage: "pencil")
        }

        if let path = document.path, !path.isEmpty {
            Button {
                let url = URL(fileURLWithPath: path)
                NSWorkspace.shared.activateFileViewerSelecting([url])
            } label: {
                Label("Reveal in Finder", systemImage: "folder")
            }
        }

        // Run Workflow submenu — lists all workflows inline, no picker dialog.
        let availableWorkflows = libraryWorkflows
        if !selection.isEmpty && featureManager.isWorkflowRunOnSelectionEnabled
            && !availableWorkflows.isEmpty {
            let docIds = Array(selection)
            Menu {
                ForEach(availableWorkflows.sorted { $0.name < $1.name }) { workflow in
                    Button(workflow.name) {
                        selectedDocumentIdsForBatch = docIds
                        Task { await runBatchWorkflow(workflowId: workflow.id) }
                    }
                }
            } label: {
                Label("Run Workflow", systemImage: "flowchart")
            }
        }
    }

    // MARK: - Workflow Execution (replaces batch path)

    /// Execute a workflow via SSE, mirroring the toolbar path in ContentView+Actions.
    /// Passes ALL selected document IDs at once so aggregation workflows (Catalogue)
    /// receive the complete set, and SSE events drive UI refresh.
    @MainActor
    // swiftlint:disable:next function_body_length
    func runBatchWorkflow(workflowId: String) async {
        guard !selectedDocumentIdsForBatch.isEmpty else { return }

        let docIds = selectedDocumentIdsForBatch
        let activeWorkflows = libraryManager.getLibrary(id: windowState.libraryId)?.workflowStore.workflows
        let globalWorkflows = libraryManager.globalLibrary?.workflowStore.workflows
        let workflowName = activeWorkflows?.first(where: { $0.id == workflowId })?.name
            ?? globalWorkflows?.first(where: { $0.id == workflowId })?.name
            ?? workflowId

        logger.info("Starting SSE workflow \(workflowId) on \(docIds.count) documents via context menu")

        var streamCompleted = false
        do {
            let response = try await workflowStreamService.execute(
                workflowId: workflowId,
                inputs: ["selected_doc_ids": docIds],
                onEvent: { event in
                    executionObserver.handleEvent(event, for: workflowId)
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
            logger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
            ErrorService.shared.reportError(error)
            executionObserver.endExecution(workflowId: workflowId, status: .failed)
        }
    }
}
