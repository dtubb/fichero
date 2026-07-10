// swiftlint:disable file_length
import FicheroAPIClient
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

    // ponytail: recompute inputs — documents, entities, searchText, sortOrder, sortFieldRaw, sortAscending, folderId
    // filteredDocuments and filteredEntities are @State vars on LibraryView; recomputeFiltered()
    // is called from .onAppear and .onChange of every input so filter/sort never runs in body.
    func recomputeFiltered() {
        // Documents
        var docs = documents
        if !searchText.isEmpty {
            docs = docs.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) ||
                    ($0.pageContent?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                    $0.status.rawValue.localizedCaseInsensitiveContains(searchText)
            }
        }
        filteredDocuments = docs.sorted(using: sortOrder)
        thumbnailPrefetchKey = filteredDocuments.map(\.id).joined()

        // Entities — always strip OCR/extraction garbage names (no-letter fragments
        // like "12:10" that the entity extractor occasionally produces).
        var items = entities.filter { !OntologyBrowser.isOcrGarbage($0.canonicalName) }
        if !searchText.isEmpty {
            let query = searchText.localizedLowercase
            items = items.filter { entity in
                entity.canonicalName.localizedLowercase.contains(query)
                    || entity.entityType?.rawValue.localizedLowercase.contains(query) == true
                    || (entity.aliases ?? []).contains { $0.localizedLowercase.contains(query) }
            }
        }
        filteredEntities = items.sorted { lhs, rhs in
            let lhsName = lhs.canonicalName.localizedLowercase
            let rhsName = rhs.canonicalName.localizedLowercase
            if lhsName != rhsName {
                return lhsName < rhsName
            }
            let lhsCorroboration = lhs.corroborationCount ?? 0
            let rhsCorroboration = rhs.corroborationCount ?? 0
            if lhsCorroboration != rhsCorroboration {
                return lhsCorroboration > rhsCorroboration
            }
            return entitySelectionId(for: lhs) < entitySelectionId(for: rhs)
        }
    }

    var isShowingEntitiesCollection: Bool {
        contentCollection == .entities
    }

    var entityCollectionTaskKey: String {
        guard isShowingEntitiesCollection else { return "documents" }
        return "entities:\(windowState.libraryId.uuidString)"
    }

    var isCollectionLoading: Bool {
        isShowingEntitiesCollection ? isLoadingEntities : isLoading
    }

    var activeErrorMessage: String? {
        isShowingEntitiesCollection ? entityLoadErrorMessage : errorMessage
    }

    var isCollectionEmpty: Bool {
        isShowingEntitiesCollection ? filteredEntities.isEmpty : filteredDocuments.isEmpty
    }

    // MARK: - Filter Bar

    /// Xcode-navigator-style filter bar pinned to the BOTTOM of the library
    /// list pane (mounted via `.safeAreaInset(edge: .bottom)` in `LibraryView`).
    /// Thin, subtle `.bar` material with a top divider; binds `searchText`,
    /// which drives `filteredDocuments`, so it quick-narrows the visible rows
    /// client-side. The toolbar filter toggle / ⌘F controls visibility;
    /// Escape hides the bar (and clears the filter so no rows stay hidden).
    var filterBarView: some View {
        VStack(spacing: 0) {
            Divider()

            // Translucent Liquid Glass background, matching the sidebar mini-toolbars
            // and the library action bar for a consistent glass look (#2550).
            GlassEffectContainer {
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                        .foregroundStyle(.secondary)
                        .font(.body)
                        .imageScale(.small)

                    TextField("Filter", text: $searchText)
                        .textFieldStyle(.plain)
                        .font(.callout)
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
                }
                .padding(.horizontal, 10)
                .frame(height: 30)
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
            }
        }
        // Escape hides the bottom filter bar and clears the filter so no rows
        // are left silently hidden once the bar disappears.
        .background(
            Button("") {
                searchText = ""
                showFilterBar = false
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.escape, modifiers: [])
            .hidden()
        )
    }

    // MARK: - Empty State

    var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
                .controlSize(.large)

            Text(isShowingEntitiesCollection ? "Loading Entities..." : "Loading Documents...")
                .font(.headline)

            Text(isShowingEntitiesCollection ? "Reading knowledge graph entities" : "Connecting to library data")
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

            Text(isShowingEntitiesCollection ? "Couldn’t Load Entities" : "Couldn’t Load Documents")
                .font(.headline)

            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)

            Button("Retry") {
                if isShowingEntitiesCollection {
                    Task {
                        await loadEntitiesIfNeeded()
                    }
                } else {
                    onRetry()
                }
            }
            .keyboardShortcut("r", modifiers: .command)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: isShowingEntitiesCollection ? "person.3.sequence" : "doc.text.magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text(isShowingEntitiesCollection ? "No Entities" : "No Documents")
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
            } else if isShowingEntitiesCollection {
                Text("Select an entity to inspect it.")
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

    func loadEntitiesIfNeeded() async {
        guard isShowingEntitiesCollection else { return }
        isLoadingEntities = true
        entityLoadErrorMessage = nil
        defer { isLoadingEntities = false }
        do {
            let fetched = try await entityService.listEntities(limit: 1000)
            guard !Task.isCancelled else { return }
            entities = fetched
            // Eagerly recompute so syncSelectionToLoadedEntities reads the fresh filteredEntities.
            recomputeFiltered()
            syncSelectionToLoadedEntities()
        } catch {
            guard !Task.isCancelled else { return }
            entities = []
            entityLoadErrorMessage = error.localizedDescription
        }
    }

    func entitySelectionId(for entity: Components.Schemas.KnowledgeEntity) -> String {
        entity.id ?? entity.stableInspectorId
    }

    func focusEntityIfPossible(_ entity: Components.Schemas.KnowledgeEntity) {
        guard let entityId = entity.id, !entityId.isEmpty else { return }
        kgFocusState.focusEntity(entityId: entityId)
    }

    func syncSelectionToLoadedEntities() {
        let validIds = Set(filteredEntities.map { entitySelectionId(for: $0) })
        selection = selection.intersection(validIds)
        if let selectionAnchor, !validIds.contains(selectionAnchor) {
            self.selectionAnchor = nil
        }
    }

    // MARK: - Tap Handling

    func canNavigateInto(_ doc: Document) -> Bool {
        doc.isNavigableContainer
    }

    /// Finder-style double-click: keep the source row selected in THIS window,
    /// then open it in place — navigate into containers, otherwise preview the
    /// document. Explicit New Tab / New Window affordances stay in the context
    /// menu. (#3364)
    func handleDoubleClick(_ doc: Document) {
        listScrollCenterTarget = doc.id
        openDocument(doc)
    }

    func handleTap(_ doc: Document) {
        onRequestFocus()
        #if os(macOS)
        let modifiers = NSEvent.modifierFlags
        if modifiers.contains(.shift), let anchor = selectionAnchor {
            handleShiftClick(doc, anchor: anchor, commandKeyDown: modifiers.contains(.command))
        } else if modifiers.contains(.command) {
            handleCommandClick(doc)
        } else {
            handlePlainClick(doc)
        }
        #else
        handlePlainClick(doc)
        #endif
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
        detailDocument = doc
        if sidebarHidden, canNavigateInto(doc) {
            onNavigateInto(doc)
        }
    }

    func handleEntityTap(_ entity: Components.Schemas.KnowledgeEntity) {
        onRequestFocus()
        #if os(macOS)
        let modifiers = NSEvent.modifierFlags
        if modifiers.contains(.shift), let anchor = selectionAnchor {
            handleEntityShiftClick(entity, anchor: anchor, commandKeyDown: modifiers.contains(.command))
        } else if modifiers.contains(.command) {
            handleEntityCommandClick(entity)
        } else {
            handleEntityPlainClick(entity)
        }
        #else
        handleEntityPlainClick(entity)
        #endif
        focusEntityIfPossible(entity)
    }

    func handleEntityDoubleClick(_ entity: Components.Schemas.KnowledgeEntity) {
        let entityId = entitySelectionId(for: entity)
        withAnimation(.easeInOut(duration: 0.2)) {
            selection = [entityId]
            selectionAnchor = entityId
        }
        listScrollCenterTarget = entityId
        focusEntityIfPossible(entity)
    }

    private func handleEntityShiftClick(
        _ entity: Components.Schemas.KnowledgeEntity,
        anchor: String,
        commandKeyDown: Bool
    ) {
        let items = filteredEntities
        guard let anchorIndex = items.firstIndex(where: { entitySelectionId(for: $0) == anchor }),
              let clickIndex = items.firstIndex(where: { entitySelectionId(for: $0) == entitySelectionId(for: entity) }) else {
            return
        }
        let range = min(anchorIndex, clickIndex)...max(anchorIndex, clickIndex)
        let rangeIds = Set(range.map { entitySelectionId(for: items[$0]) })
        if commandKeyDown {
            selection.formUnion(rangeIds)
        } else {
            selection = rangeIds
        }
    }

    private func handleEntityCommandClick(_ entity: Components.Schemas.KnowledgeEntity) {
        let entityId = entitySelectionId(for: entity)
        if selection.contains(entityId) {
            selection.remove(entityId)
        } else {
            selection.insert(entityId)
        }
        selectionAnchor = entityId
    }

    private func handleEntityPlainClick(_ entity: Components.Schemas.KnowledgeEntity) {
        let entityId = entitySelectionId(for: entity)
        selection = [entityId]
        selectionAnchor = entityId
    }

    // MARK: - Open Affordances (#1685)

    /// In-window "Open": navigate into containers, otherwise show the doc in
    /// the detail/preview pane. Mirrors the existing double-click open path.
    func openDocument(_ doc: Document) {
        selection = [doc.id]
        selectionAnchor = doc.id
        if canNavigateInto(doc) {
            onNavigateInto(doc)
        } else {
            detailDocument = doc
        }
    }

    /// "Open in New Tab / New Window": open a fresh window on this library via
    /// the shared Safari new-window path, asking it to focus this document
    /// once its rows load.
    func openDocumentInNewWindow(_ doc: Document, asTab: Bool) {
        WindowOpener.open(
            libraryId: windowState.libraryId,
            documentId: doc.id,
            asTab: asTab,
            using: openWindow
        )
    }

    /// Hand-off consumer for a cross-window open intent. When a window is
    /// opened via "Open in New Tab/Window" with a pending document id, select
    /// and preview that document here, then clear the intent so sibling
    /// windows don't also consume it.
    func consumePendingOpen() {
        guard let pendingId = libraryManager.pendingOpenDocumentId,
              let doc = documents.first(where: { $0.id == pendingId }) else { return }
        libraryManager.pendingOpenDocumentId = nil
        openDocument(doc)
    }

    // MARK: - Context Menu

    @ViewBuilder
    // swiftlint:disable:next function_body_length
    func documentContextMenu(for document: Document) -> some View {
        let excludeTargets = excludeToggleTargets(for: document)
        let shouldIncludeInProcessing = excludeTargets.allSatisfy(\.excludeFromProcessing)

        // Finder-style open affordances (#1685). "Open" reuses the existing
        // in-window open path; New Tab / New Window reuse the Safari
        // new-window path and focus this document once the window loads.
        OpenInMenuItems(
            open: { openDocument(document) },
            openInNewTab: { openDocumentInNewWindow(document, asTab: true) },
            openInNewWindow: { openDocumentInNewWindow(document, asTab: false) }
        )

        Divider()

        Button {
            startRename(for: document)
        } label: {
            Label("Rename", systemImage: "pencil")
        }

        // Only available when the engine is local — a remote engine means
        // document.path is a server-side path, not a path on this Mac (#1861).
        #if os(macOS)
        if EngineConfig.engineIsLocal, let path = document.path, !path.isEmpty {
            Button {
                let url = URL(fileURLWithPath: path)
                NSWorkspace.shared.activateFileViewerSelecting([url])
            } label: {
                Label("Reveal in Finder", systemImage: "folder")
            }
        }
        #endif

        // Add-to-Workspace bridge (#1494): alias this document into a
        // workspace folder. Never moves the source (#1487).
        Button {
            workspacePickerDocument = document
        } label: {
            Label("Add to Workspace…", systemImage: "square.grid.2x2")
        }

        // Bookmark this document — a saved pointer node (#2755).
        Button {
            bookmarkPickerDocument = document
        } label: {
            Label("Bookmark…", systemImage: "bookmark")
        }

        Button {
            Task {
                await toggleExcludeFromProcessing(
                    documentIds: excludeTargets.map(\.id),
                    excluded: !shouldIncludeInProcessing
                )
            }
        } label: {
            Label(
                shouldIncludeInProcessing ? "Include in Processing" : "Exclude from Processing",
                systemImage: shouldIncludeInProcessing ? "eye" : "eye.slash"
            )
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

    private func excludeToggleTargets(for document: Document) -> [Document] {
        let targetIds = selection.isEmpty ? [document.id] : Array(selection)
        let selectedDocuments = documents.filter { targetIds.contains($0.id) }
        return selectedDocuments.isEmpty ? [document] : selectedDocuments
    }

    @MainActor
    private func toggleExcludeFromProcessing(
        documentIds: [String],
        excluded: Bool
    ) async {
        guard let library = activeLibraryReference else { return }

        do {
            let refreshed = try await library.documentServiceGenerated.batchExclude(
                documentIds: documentIds,
                excluded: excluded
            )
            for updated in refreshed {
                documentStore.refreshLocalContent(updated)
                if detailDocument?.id == updated.id {
                    detailDocument = updated
                }
            }
        } catch {
            documentStore.error = error
        }
    }

    private var activeLibraryReference: LibraryManager.LibraryReference? {
        if let library = libraryManager.getLibrary(id: windowState.libraryId) {
            return library
        }
        return libraryManager.globalLibrary
    }

    // MARK: - Workflow Execution (replaces batch path)
    /// Execute a workflow via SSE, mirroring the toolbar path in ContentView+Actions.
    /// Passes ALL selected document IDs at once so aggregation workflows (Catalogue)
    /// receive the complete set, and SSE events drive UI refresh.
    @MainActor
    // swiftlint:disable:next function_body_length
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

        var executionThreadId = "pending:\(UUID().uuidString)"
        executionObserver.startExecution(
            workflowId: workflowId,
            name: workflowName,
            threadId: executionThreadId
        )
        var streamCompleted = false
        do {
                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": docIds],
                    providerOverride: providerOverride,
                    modelOverride: modelOverride,
                    onAccepted: { acceptedResponse in
                        let threadId = acceptedResponse.threadId
                        executionObserver.promoteExecution(
                            from: executionThreadId,
                            to: threadId,
                            onCancel: { [weak workflowStreamService] in
                                Task { @MainActor in
                                    try? await workflowStreamService?.stopWorkflow(threadId: threadId)
                                }
                            }
                        )
                        executionThreadId = threadId
                    },
                    onEvent: { [weak documentStore = library?.documentStore] event in
                    if handleBatchWorkflowEvent(
                        event,
                        threadId: executionThreadId,
                        documentStore: documentStore
                    ) {
                        streamCompleted = true
                    }
                }
            )

            let threadId = response.threadId
            logger.info("Started SSE workflow \(workflowId) thread \(threadId) for \(docIds.count) docs")

            while !streamCompleted {
                try await Task.sleep(for: .milliseconds(200))
                if Task.isCancelled { break }
                if let exec = executionObserver.activeExecutions[executionThreadId], !exec.isRunning {
                    streamCompleted = true
                }
            }

            let finalStatus = batchWorkflowFinalStatus(forThreadId: executionThreadId)
            executionObserver.endExecution(threadId: executionThreadId, status: finalStatus)
            logger.info("Workflow \(workflowId) finished with status: \(String(describing: finalStatus))")

        } catch {
            logger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
            ErrorService.shared.reportError(error)
            executionObserver.endExecution(threadId: executionThreadId, status: .failed)
        }
    }

    // swiftlint:disable:next cyclomatic_complexity
    private func handleBatchWorkflowEvent(
        _ event: WorkflowStreamEvent,
        threadId: String,
        documentStore: DocumentStore?
    ) -> Bool {
        executionObserver.handleEvent(event, forThreadId: threadId)
        if let store = documentStore {
            switch event {
            case .fileStart:
                if let identity = event.fileProgressIdentity {
                    store.updateProcessingStatus(for: identity, status: .processing)
                }
            case .fileComplete:
                if let identity = event.fileProgressIdentity {
                    store.recordFanoutComplete(for: identity)
                    if let documentId = identity.leafDocumentId {
                        Task { @MainActor in
                            await store.refreshDocumentsByIds([documentId])
                        }
                    }
                }
            case .fileError:
                if let identity = event.fileProgressIdentity {
                    store.updateProcessingStatus(for: identity, status: .failed)
                }
            default:
                break
            }
        }
        switch event {
        case .complete:
            documentStore?.flushPendingFanoutCompletions(status: .completed)
            if let documentStore {
                Task { @MainActor in
                    await documentStore.refreshDocumentsByIds(selectedDocumentIdsForBatch)
                }
            }
            return true
        case .error, .systemicError:
            documentStore?.flushPendingFanoutCompletions(status: .failed)
            return true
        default:
            return false
        }
    }

    private func batchWorkflowFinalStatus(forThreadId threadId: String) -> WorkflowStatus {
        guard let exec = executionObserver.activeExecutions[threadId] else {
            return .completed
        }
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }
}
