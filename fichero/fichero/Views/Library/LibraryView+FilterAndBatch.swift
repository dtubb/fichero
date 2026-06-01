import OSLog
import SwiftUI

// MARK: - Filter, Selection, and Batch Extension

extension LibraryView {
    private var logger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "LibraryView")
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
                    .help("Clear filter")
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
                // Escape route — clicking a tag in a row could trap the
                // user with a stuck filter and no visible filter bar
                // (Daniel hit this with "Image"). Always offer Clear.
                Button {
                    searchText = ""
                    showFilterBar = false
                } label: {
                    Label("Clear Filter", systemImage: "xmark.circle.fill")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(.top, 4)
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
    /// Also updates selection so the highlighted row matches the activated
    /// doc — without this, double-clicking a doc that wasn't single-clicked
    /// first leaves the previous selection highlighted while the new doc
    /// shows in the preview pane. (#779)
    func handleDoubleClick(_ doc: Document) {
        // Wrap in withAnimation so the layout transition from .none →
        // .standard/.widescreen animates instead of flashing — combined with
        // the .animation(value: layout) on the centerContent Group, this
        // makes the first click smooth.
        withAnimation(.easeInOut(duration: 0.2)) {
            selection = [doc.id]
            selectionAnchor = doc.id
            if canNavigateInto(doc) {
                onNavigateInto(doc)
            } else {
                detailDocument = doc
            }
        }
        // Scroll grid to the activated doc so when the preview opens and
        // the grid shrinks, the user can still see what they just opened
        // in the now-smaller grid pane. Use the *center* target so we force
        // a recenter even when the item was technically visible in the old
        // wide grid — after the layout shrinks, "visible" changes (#769).
        listScrollCenterTarget = doc.id
    }

    func handleTap(_ doc: Document) {
        onRequestFocus()
        let modifiers = NSEvent.modifierFlags
        if modifiers.contains(.shift), let anchor = selectionAnchor {
            handleShiftClick(doc, anchor: anchor, commandKeyDown: modifiers.contains(.command))
        } else if modifiers.contains(.command) {
            handleCommandClick(doc)
        } else {
            handlePlainClick(doc)
        }
    }

    private func handleShiftClick(_ doc: Document, anchor: String, commandKeyDown: Bool) {
        // Shift+click: range select from anchor to clicked item.
        let docs = filteredDocuments
        guard let anchorIndex = docs.firstIndex(where: { $0.id == anchor }),
              let clickIndex = docs.firstIndex(where: { $0.id == doc.id }) else {
            return
        }
        let range = min(anchorIndex, clickIndex)...max(anchorIndex, clickIndex)
        let rangeIds = Set(docs[range].map(\.id))
        if commandKeyDown {
            selection.formUnion(rangeIds)
        } else {
            selection = rangeIds
        }
    }

    private func handleCommandClick(_ doc: Document) {
        // Cmd+click: toggle individual item.
        if selection.contains(doc.id) {
            selection.remove(doc.id)
        } else {
            selection.insert(doc.id)
        }
        selectionAnchor = doc.id
    }

    private func handlePlainClick(_ doc: Document) {
        // Plain click: replace selection.
        selection = [doc.id]
        selectionAnchor = doc.id
        if sidebarHidden, canNavigateInto(doc) {
            onNavigateInto(doc)
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

        // Add-to-Workspace bridge (#1494): alias this document into a
        // workspace folder. Never moves the source (#1487).
        Button {
            workspacePickerDocument = document
        } label: {
            Label("Add to Workspace…", systemImage: "square.grid.2x2")
        }

        // Run Workflow submenu — workflows grouped by `folderPath` so
        // user-organized presets (e.g. /Catalogue, /Transcribe) appear
        // as nested submenus matching the context menu in the sidebar
        // (#722).
        let availableWorkflows = libraryWorkflows
        if !selection.isEmpty && featureManager.isWorkflowRunOnSelectionEnabled
            && !availableWorkflows.isEmpty {
            let docIds = Array(selection)
            Menu {
                workflowSubmenuItems(workflows: availableWorkflows) { workflowId, providerOverride, modelOverride in
                    selectedDocumentIdsForBatch = docIds
                    Task {
                        await runBatchWorkflow(
                            workflowId: workflowId,
                            providerOverride: providerOverride,
                            modelOverride: modelOverride
                        )
                    }
                }
            } label: {
                Label("Run Workflow", systemImage: "flowchart")
            }
            .onAppear {
                Task { @MainActor in
                    let chatService = libraryManager
                        .getLibrary(id: windowState.libraryId)?
                        .chatServiceGenerated
                        ?? libraryManager.globalLibrary?.chatServiceGenerated
                    await workflowRunProviderCache.ensureLoaded(chatService: chatService)
                }
            }
        }
    }

    /// Render a Run-Workflow menu body that groups workflows by their
    /// `folderPath`. Top-level workflows appear directly; folders become
    /// `Menu("<folder>")` submenus. Used by the grid context menu and the
    /// sidebar row context menu (which has its own copy in
    /// SidebarItemRow.swift). Centralizing here would require passing
    /// the action across modules — we accept the duplication for now.
    @ViewBuilder
    private func workflowSubmenuItems(
        workflows: [WorkflowSidebarItem],
        action: @escaping (String, String?, String?) -> Void
    ) -> some View {
        let grouped = Dictionary(grouping: workflows) { workflow in
            workflow.folderPath.isEmpty ? "/" : workflow.folderPath
        }
        let topLevel = (grouped["/"] ?? []).sorted { $0.name < $1.name }
        let folderKeys = grouped.keys.filter { $0 != "/" }.sorted()

        ForEach(topLevel) { workflow in
            runWorkflowMenuEntry(workflow: workflow, action: action)
        }
        ForEach(folderKeys, id: \.self) { folderPath in
            Menu(folderPathLabel(folderPath)) {
                let inFolder = (grouped[folderPath] ?? []).sorted { $0.name < $1.name }
                ForEach(inFolder) { workflow in
                    runWorkflowMenuEntry(workflow: workflow, action: action)
                }
            }
        }
    }

    @ViewBuilder
    private func runWorkflowMenuEntry(
        workflow: WorkflowSidebarItem,
        action: @escaping (String, String?, String?) -> Void
    ) -> some View {
        Menu(workflow.name) {
            Button("Default") { action(workflow.id, nil, nil) }
            ForEach(workflowRunProviderCache.providers.filter { $0.available }) { provider in
                if provider.models.isEmpty {
                    Button(provider.name) {
                        action(workflow.id, provider.id, nil)
                    }
                } else {
                    Menu(provider.name) {
                        ForEach(provider.models, id: \.self) { model in
                            Button(model) {
                                action(workflow.id, provider.id, model)
                            }
                        }
                    }
                }
            }
        }
    }

    private func folderPathLabel(_ path: String) -> String {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmed.isEmpty { return path }
        return String(trimmed.split(separator: "/").last ?? Substring(trimmed))
    }
    // MARK: - Workflow Execution (replaces batch path)
    /// Execute a workflow via SSE, mirroring the toolbar path in ContentView+Actions.
    /// Passes ALL selected document IDs at once so aggregation workflows (Catalogue)
    /// receive the complete set, and SSE events drive UI refresh.
    @MainActor
    func runBatchWorkflow(
        workflowId: String,
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) async {
        guard !selectedDocumentIdsForBatch.isEmpty else { return }

        let docIds = selectedDocumentIdsForBatch
        let library = libraryManager.getLibrary(id: windowState.libraryId)
        let activeWorkflows = library?.workflowStore.workflows
        let workflowName = activeWorkflows?.first(where: { $0.id == workflowId })?.name
            ?? libraryManager.globalLibrary?.workflowStore.workflows.first(where: { $0.id == workflowId })?.name
            ?? workflowId

        logger.info("Starting SSE workflow \(workflowId) on \(docIds.count) documents via context menu")

        var streamCompleted = false
        do {
                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": docIds],
                    providerOverride: providerOverride,
                    modelOverride: modelOverride,
                    onEvent: { [weak documentStore = library?.documentStore] event in
                    if handleBatchWorkflowEvent(
                        event,
                        workflowId: workflowId,
                        documentStore: documentStore
                    ) {
                        streamCompleted = true
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

            let finalStatus = batchWorkflowFinalStatus(for: workflowId)
            executionObserver.endExecution(workflowId: workflowId, status: finalStatus)
            logger.info("Workflow \(workflowId) finished with status: \(String(describing: finalStatus))")

        } catch {
            logger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
            ErrorService.shared.reportError(error)
            executionObserver.endExecution(workflowId: workflowId, status: .failed)
        }
    }

    private func handleBatchWorkflowEvent(
        _ event: WorkflowStreamEvent,
        workflowId: String,
        documentStore: DocumentStore?
    ) -> Bool {
        executionObserver.handleEvent(event, for: workflowId)
        if let store = documentStore {
            switch event {
            case .fileStart(_, _, let filePath, _, _, _):
                store.updateProcessingStatus(forPath: filePath, status: .processing)
            case .fileComplete(_, _, let filePath, _, _, _, _):
                store.recordFanoutComplete(forPath: filePath)
            case .fileError(_, _, let filePath, _, _):
                store.updateProcessingStatus(forPath: filePath, status: .failed)
            default:
                break
            }
        }
        switch event {
        case .complete:
            documentStore?.flushPendingFanoutCompletions(status: .completed)
            return true
        case .error, .systemicError:
            documentStore?.flushPendingFanoutCompletions(status: .failed)
            return true
        default:
            return false
        }
    }

    private func batchWorkflowFinalStatus(for workflowId: String) -> WorkflowStatus {
        guard let exec = executionObserver.activeExecutions[workflowId] else {
            return .completed
        }
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }
}
