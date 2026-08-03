import FicheroAPIClient
import OSLog
import SwiftUI

private let contextMenuLogger = Logger(
    subsystem: "app.fichero.fichero", category: "LibraryContextMenu"
)

// MARK: - Context Menu, Drag, and Workflow Menu

extension LibraryView {

    func libraryItemDrag(for document: Document) -> LibraryItemDrag {
        let kind: LibraryItemDrag.Kind = switch document.docType {
        case .page: .page
        case .group: .group
        default: .document
        }
        return LibraryItemDrag(
            kind: kind,
            id: document.id,
            documentId: document.id,
            text: document.pageContent?.isEmpty == false ? document.pageContent ?? document.name : document.name,
            // File-export context (#4123): the drag can promise a real copy
            // of the source file, named for Finder. Page rows export just
            // their page (`sequence` is 1-based).
            libraryId: windowState.libraryId,
            name: document.name,
            pageIndex: kind == .page ? max(0, (document.sequence ?? 1) - 1) : nil
        )
    }

    var libraryWorkflows: [WorkflowSidebarItem] {
        // #3820 — source from the SAME reference the execution uses
        // (`activeLibraryReference`), so the menu can never list a workflow the
        // run would execute against a different library and 400 on.
        activeLibraryReference?.workflowStore.workflows ?? []
    }

    var activeLibraryReference: LibraryManager.LibraryReference? {
        if let library = libraryManager.getLibrary(id: windowState.libraryId) {
            return library
        }
        return libraryManager.globalLibrary
    }

    // MARK: - Context Menu

    @ViewBuilder
    func documentContextMenu(for document: Document) -> some View {
        let excludeTargets = excludeToggleTargets(for: document)

        // Parity with the sidebar row menu (#4121): the same document gets
        // the same actions in every surface.
        addToChatMenuItem(for: document)
        importIntoFolderMenuItem(for: document)
        openAndRenameMenuItems(for: document)
        duplicateAndAliasMenuItems(for: document)
        organizeMenuItems(for: document)
        stackMenuItems(for: document)
        excludeFromProcessingMenuItem(excludeTargets: excludeTargets)
        deleteMenuItem(for: document)
        runWorkflowMenuItem(for: document)
    }

    /// Contextual-menu import (#4449) — one of the three affordances the
    /// issue requires, alongside the Data-menu item and the bottom-bar
    /// button. Only on a folder; a plain document has nothing to import
    /// INTO. Shares `showingFileImporter`/`handleFileImport` with the
    /// bottom bar (`LibraryView+BottomActionBar.swift`) — one picker, one
    /// handler, every surface states its own target folder first.
    @ViewBuilder
    private func importIntoFolderMenuItem(for document: Document) -> some View {
        if document.docType == .folder {
            Button {
                fileImportMode = .link
                fileImportTargetFolderId = document.id
                showingFileImporter = true
            } label: {
                Label("Import Files Here…", systemImage: "square.and.arrow.down")
            }
            Divider()
        }
    }

    /// The ONE empty-area import menu (#4449), for every surface that can be
    /// right-clicked while showing no row: the icon grid's scroll gutter
    /// (`LibraryView+IconMode.swift`) and — the case the first fix missed —
    /// the `emptyState` body itself (`LibraryView+FilterAndBatch.swift`).
    ///
    /// Those are two different views, and an empty library shows the SECOND
    /// one: `libraryRowsOrEmptyState` branches to `emptyState` before the
    /// `displayMode` switch ever reaches `iconsView`. So the gutter menu was
    /// only ever reachable in a library that already had documents, and a
    /// new user right-clicking their empty library got nothing — the exact
    /// "app cannot take my files" conclusion this issue is about.
    ///
    /// Extracted rather than copied a third time: two inline duplicates is
    /// how the bottom bar and `AddItemMenu` diverged in the first place.
    /// Targets `folderId` — this pane's own container, never a bare root.
    @ViewBuilder
    var libraryEmptyAreaImportMenu: some View {
        Button {
            fileImportMode = .link
            fileImportTargetFolderId = folderId
            showingFileImporter = true
        } label: {
            Label("Import Files…", systemImage: "square.and.arrow.down")
        }
    }

    // MARK: - Sidebar-parity items (#4121)

    @ViewBuilder
    private func addToChatMenuItem(for document: Document) -> some View {
        if let onAddToChat, document.docType != .folder {
            Button {
                // Right-click acts on the clicked item unless it's part of
                // the current selection (Finder semantics).
                if !selection.contains(document.id) {
                    selection = [document.id]
                }
                onAddToChat()
            } label: {
                Label("Add to Chat", systemImage: "bubble.left.and.text.bubble.right")
            }
            Divider()
        }
    }

    @ViewBuilder
    private func duplicateAndAliasMenuItems(for document: Document) -> some View {
        Button {
            duplicateDocument(document)
        } label: {
            Label("Duplicate", systemImage: "plus.square.on.square")
        }
        Button {
            makeAlias(for: document)
        } label: {
            Label("Make Alias", systemImage: "arrowshape.turn.up.right")
        }
        #if os(macOS)
        // Export a real copy of the source file (#4121) — the same
        // storage-service path the Finder drag-out uses (#4123).
        if document.docType != .folder {
            Button {
                DocumentExporter.exportViaSavePanel(
                    SidebarDragID(document: document, libraryId: windowState.libraryId)
                ) { message in
                    contextMenuLogger.error("\(message, privacy: .public)")
                }
            } label: {
                Label("Export…", systemImage: "square.and.arrow.up")
            }
        }
        #endif
    }

    @ViewBuilder
    private func deleteMenuItem(for document: Document) -> some View {
        Divider()
        Button(role: .destructive) {
            promptDelete(for: document)
        } label: {
            Label("Delete", systemImage: "trash")
        }
    }

    /// Audited document.duplicate — the SAME action path the sidebar row uses.
    func duplicateDocument(_ document: Document) {
        guard let library = activeLibraryReference else { return }
        Task { @MainActor in
            do {
                _ = try await library.actionsService.invokeAction(
                    name: "document.duplicate",
                    params: DocumentDuplicateActionParams(docId: document.id, parentId: nil)
                )
                await library.documentStore.refresh()
            } catch {
                contextMenuLogger.error(
                    "duplicate \(document.id, privacy: .public) failed: \(error.localizedDescription)"
                )
            }
        }
    }

    /// Finder-style alias beside the original — aliasing an alias targets the
    /// ORIGINAL (no alias chains), mirroring the sidebar's makeAliasAction.
    func makeAlias(for document: Document) {
        guard let library = activeLibraryReference else { return }
        let targetId = document.isAlias ? (document.aliasTargetId ?? document.id) : document.id
        Task { @MainActor in
            let created = await library.bookmarkService.createBookmark(
                targetId: targetId,
                // #116: the fourth raw-name write, and the one OUTSIDE the
                // sidebar — a sidebar-scoped audit could not have found it.
                name: AliasName.forAlias(of: document, targetParentId: document.parentId),
                parentId: document.parentId
            )
            if created {
                await library.documentStore.refresh()
            } else {
                contextMenuLogger.error(
                    "make alias for \(document.id, privacy: .public) failed"
                )
            }
        }
    }

    /// The ONE row-level delete entry point (Finder semantics via
    /// `deleteTargets`): context menu AND iOS swipe (#2501) land here, then
    /// the shared confirm dialog runs the audited `document.delete` action.
    func promptDelete(for document: Document) {
        let targets = Self.deleteTargets(
            for: document,
            selection: selection,
            visibleDocuments: filteredDocuments
        )
        guard !targets.isEmpty else { return }
        documentsToDelete = targets
        showDeleteConfirmation = true
    }

    // Finder-style open affordances (#1685). "Open" reuses the existing
    // in-window open path; New Tab / New Window reuse the Safari
    // new-window path and focus this document once the window loads.
    @ViewBuilder
    private func openAndRenameMenuItems(for document: Document) -> some View {
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

        // Discoverable Quick Look (#4160) — same fetch Space uses; folders
        // have no source file to preview.
        if document.docType != .folder {
            Button {
                quickLook(document)
            } label: {
                Label("Quick Look", systemImage: "eye")
            }
        }

        // Shared reveal policy (#4305): local engine + path resolves on this
        // machine; linked originals get the Finder-alias verb.
        RevealOriginalMenuItem(document: document)
    }

    @ViewBuilder
    private func organizeMenuItems(for document: Document) -> some View {
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
    }

    // Image stack/group (#3535): combine 2+ selected images into ONE
    // reversible group node (e.g. two pages of one letter); ungroup fully
    // restores them. The inverse of the reversible split (#1595).
    @ViewBuilder
    private func stackMenuItems(for document: Document) -> some View {
        let stackTargets = imageStackTargets(for: document)
        if stackTargets.count >= 2 {
            Divider()
            Button {
                groupAsStack(stackTargets)
            } label: {
                Label("Group as Stack", systemImage: "square.stack")
            }
        }
        if document.docType == .group {
            Divider()
            Button {
                ungroupStack(document)
            } label: {
                Label("Ungroup", systemImage: "square.stack.3d.up.slash")
            }
        }
    }

    @ViewBuilder
    private func excludeFromProcessingMenuItem(excludeTargets: [Document]) -> some View {
        let shouldIncludeInProcessing = excludeTargets.allSatisfy(\.excludeFromProcessing)
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
    }

    // Run Workflow submenu — workflows grouped by `folderPath` so
    // user-organized presets (e.g. /Catalogue, /Transcribe) appear
    // as nested submenus matching the context menu in the sidebar
    // (#722).
    @ViewBuilder
    private func runWorkflowMenuItem(for clickedDocument: Document) -> some View {
        let availableWorkflows = libraryWorkflows
        let resolution = resolvedWorkflowRun(for: clickedDocument)
        // #4419: not gated on the target list being non-empty — that gate is
        // how the affordance silently vanished for a whole subtree.
        if featureManager.isWorkflowRunOnSelectionEnabled,
           !availableWorkflows.isEmpty {
            Menu {
                if resolution.isEmpty {
                    Button("Nothing to run on") {}
                        .disabled(true)
                } else {
                    if resolution.ignoredSelection {
                        Text("Runs on this item only — it is outside your selection")
                        Divider()
                    }
                    RunWorkflowSubmenuItems(workflows: availableWorkflows) { workflowId, providerOverride, modelOverride in
                        Task { @MainActor in
                            selectedDocumentIdsForBatch = resolution.targetIds
                            await runBatchWorkflow(
                                workflowId: workflowId,
                                providerOverride: providerOverride,
                                modelOverride: modelOverride
                            )
                        }
                    }
                }
            } label: {
                Label("Run Workflow", systemImage: "flowchart")
            }
            .onAppear {
                Task { @MainActor in
                    let chatService = libraryManager
                        .getLibrary(id: windowState.libraryId)?
                        .chatService
                        ?? libraryManager.globalLibrary?.chatService
                    await workflowRunProviderCache.ensureLoaded(chatService: chatService)
                }
            }
        }
    }

    /// #4419: the clicked row's identity is the anchor; `documents` only helps
    /// EXPAND a folder. A selection is read from the grid's own `selection`
    /// set, which is what the user can see is selected.
    private func resolvedWorkflowRun(
        for clickedDocument: Document
    ) -> WorkflowRunTargetResolver.Resolution {
        let currentLibraryDocuments = documentStore.sidebarDocuments
        let selectedTargets = Set(
            currentLibraryDocuments
                .filter { selection.contains($0.id) }
                .map(workflowRunTarget(for:))
        )
        return WorkflowRunTargetResolver.resolve(
            clicked: workflowRunTarget(for: clickedDocument),
            selection: selectedTargets,
            documents: currentLibraryDocuments
        )
    }

    private func workflowRunTarget(for document: Document) -> WorkflowRunTarget {
        document.docType == .folder ? .folder(document.id) : .file(document.id)
    }

    // Run Workflow submenu body lives in the shared `RunWorkflowSubmenuItems`
    // (#722, deduped #4121) — one grouping/override implementation for the
    // sidebar row and the library grid context menus.

    private func excludeToggleTargets(for document: Document) -> [Document] {
        let targetIds = selection.isEmpty ? [document.id] : Array(selection)
        let selectedDocuments = documents.filter { targetIds.contains($0.id) }
        return selectedDocuments.isEmpty ? [document] : selectedDocuments
    }

    /// The image documents this right-click would stack (#3535): the current
    /// multi-selection when it includes this row, else just this document —
    /// filtered to images (only images stack).
    private func imageStackTargets(for document: Document) -> [Document] {
        let targetIds = (selection.contains(document.id) && selection.count > 1)
            ? Array(selection)
            : [document.id]
        return documents.filter { targetIds.contains($0.id) && $0.fileType == .image }
    }

    /// Group the selected images into one reversible stack node, then refresh so
    /// the stack appears as a single expandable node (#3535).
    private func groupAsStack(_ targets: [Document]) {
        guard targets.count >= 2, let library = activeLibraryReference else { return }
        let childIds = targets.map(\.id)
        Task {
            do {
                _ = try await library.documentService.createGroup(
                    name: "Stack of \(childIds.count)",
                    childIds: childIds
                )
                selection.removeAll()
                await documentStore.refresh()
            } catch {
                documentStore.error = error
            }
        }
    }

    /// Ungroup a stack — the engine restores each child to its original parent
    /// and order (#3535). Refresh to reflect the reversal.
    private func ungroupStack(_ group: Document) {
        guard let library = activeLibraryReference else { return }
        Task {
            do {
                try await library.documentService.ungroupDocument(groupId: group.id)
                await documentStore.refresh()
            } catch {
                documentStore.error = error
            }
        }
    }

    @MainActor
    private func toggleExcludeFromProcessing(
        documentIds: [String],
        excluded: Bool
    ) async {
        guard let library = activeLibraryReference else { return }

        do {
            let refreshed = try await library.documentService.batchExclude(
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
}
