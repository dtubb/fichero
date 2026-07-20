import FicheroAPIClient
import SwiftUI

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
            text: document.pageContent?.isEmpty == false ? document.pageContent ?? document.name : document.name
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

        openAndRenameMenuItems(for: document)
        organizeMenuItems(for: document)
        stackMenuItems(for: document)
        excludeFromProcessingMenuItem(excludeTargets: excludeTargets)
        runWorkflowMenuItem()
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
    private func runWorkflowMenuItem() -> some View {
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
                        .chatService
                        ?? libraryManager.globalLibrary?.chatService
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
