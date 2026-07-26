import SwiftUI

extension SidebarItemRow {
    var rowContextMenu: some View {
        Group {
            compactTouchActions

            // Finder-style open affordances (#1685). "Open" selects the row in
            // this window; New Tab / New Window open a fresh window on the
            // item's library, focusing the document when the row is a doc.
            if item.libraryId != nil {
                OpenInMenuItems(
                    open: { openInWindow() },
                    openInNewTab: { openInNewWindow(asTab: true) },
                    openInNewWindow: { openInNewWindow(asTab: false) }
                )
                Divider()
            }

            SidebarItemContextMenu(
                item: item,
                deleteTargets: sidebarContextDeleteTargets(
                    clicked: item,
                    selection: resolvedSelectionItems
                ),
                renameState: renameState,
                deleteState: deleteState,
                onPause: onAutomationPause,
                onResume: onAutomationResume,
                onTrigger: onAutomationTrigger,
                onCancel: onAutomationCancel,
                onDuplicate: workflowDuplicateAction
            )

            let workflowTargetIDs = resolvedWorkflowTargetIDs
            if let workflows = workflowStore?.workflows,
               !workflows.isEmpty,
               !workflowTargetIDs.isEmpty {
                Divider()
                Menu("Run Workflow") {
                    workflowMenuItems(workflows: workflows) { workflowId, providerOverride, modelOverride in
                        runWorkflowOnDocuments(
                            workflowId: workflowId,
                            docIds: workflowTargetIDs,
                            providerOverride: providerOverride,
                            modelOverride: modelOverride
                        )
                    }
                }
                .onAppear {
                    Task { @MainActor in
                        await workflowRunProviderCache.ensureLoaded(chatService: library?.chatService)
                    }
                }
            }
        }
    }

    /// Duplicate action for workflow rows (nil for every other kind, which
    /// hides the menu item). Mirrors WorkflowListView's duplicate flow —
    /// backend owns id/naming; the store reload republishes the sidebar.
    /// Failures surface via the shared drop-error banner rather than
    /// vanishing into the log (prefer-raise-over-silent-fallback).
    private var workflowDuplicateAction: (() -> Void)? {
        guard case .workflow(let workflow) = item.itemType,
              let store = workflowStore else { return nil }
        return {
            Task { @MainActor in
                do {
                    _ = try await store.duplicateWorkflow(workflow.id)
                } catch {
                    sidebarState.dropErrorMessage = error.localizedDescription
                }
            }
        }
    }

    /// Every highlighted row resolved to its SidebarItem — mirrors
    /// `SidebarView.selectedItems` for row-level batch actions.
    private var resolvedSelectionItems: [SidebarItem] {
        selectedDestinations.compactMap {
            findItemById($0.serializedID, in: allCachedItems)
        }
    }

    private var resolvedWorkflowTargetIDs: [String] {
        guard let clickedTarget = workflowRunTarget(for: item),
              let documents = documentStore?.sidebarDocuments else {
            return []
        }
        return WorkflowRunTargetResolver.resolve(
            clicked: clickedTarget,
            selection: Set(selectedDestinations.compactMap(workflowRunTarget(for:))),
            documents: documents
        )
    }

    private func workflowRunTarget(for item: SidebarItem) -> WorkflowRunTarget? {
        guard case .document(let document) = item.itemType else { return nil }
        return document.docType == .folder ? .folder(document.id) : .file(document.id)
    }

    private func workflowRunTarget(for destination: SidebarDestination) -> WorkflowRunTarget? {
        guard case .document = destination,
              let item = findItemById(destination.serializedID, in: allCachedItems) else {
            return nil
        }
        return workflowRunTarget(for: item)
    }

    @ViewBuilder
    private var compactTouchActions: some View {
        if horizontalSizeClass == .compact,
           case .document(let document) = item.itemType {
            let folders = moveDestinationFolders(for: document) ?? []

            if let onOpenChatWithCurrentScope {
                Button {
                    selectedItemId = item.id
                    Task { @MainActor in
                        onOpenChatWithCurrentScope()
                    }
                } label: {
                    Label("Add to Chat", systemImage: "plus.circle")
                }
            }

            if !folders.isEmpty {
                Menu("Move to Folder") {
                    ForEach(folders, id: \.id) { folder in
                        Button(folder.name) {
                            // Same executor as drag-drop (#3014) — store call +
                            // error surfacing shared via moveDocumentToFolder.
                            Task { await moveDocumentToFolder(documentId: document.id, folderId: folder.id) }
                        }
                    }
                }
            }

            if onOpenChatWithCurrentScope != nil || !folders.isEmpty {
                Divider()
            }
        }
    }

    private func moveDestinationFolders(for document: Document) -> [Document]? {
        guard let all = documentStore?.collections else { return nil }
        // Same eligibility as the drop handler: a folder target that is neither
        // the document itself nor one of its descendants (no circular move). The
        // old `$0.id != document.id` filter caught self but NOT descendants, so
        // the menu could move a folder into its own child — the drop path already
        // rejected that. Share one decision (#3014).
        return all
            .filter {
                $0.docType == .folder
                    && SidebarMovePolicy.isValidTarget(sourceId: document.id, targetId: $0.id, documents: all)
            }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    /// Builds a `Run Workflow` submenu where workflows whose `folderPath`
    /// is "/" appear at the top level and workflows under any other folder
    /// path are grouped into a `Menu("<folder>")` submenu (#722). Folder
    /// paths like `/Transcribe` and `/Catalogue` give us nested
    /// submenus matching the user's mental model. Workflows are sorted
    /// alphabetically within each group; folder names are sorted
    /// alphabetically too.
    @ViewBuilder
    func workflowMenuItems(
        workflows: [WorkflowSidebarItem],
        action: @escaping (String, String?, String?) -> Void
    ) -> some View {
        let grouped = Dictionary(grouping: workflows) { workflow in
            workflow.folderPath.isEmpty ? "/" : workflow.folderPath
        }
        let topLevel = (grouped["/"] ?? []).sorted { $0.name < $1.name }
        let folderKeys = grouped.keys
            .filter { $0 != "/" }
            .sorted()

        ForEach(topLevel) { workflow in
            Menu(workflow.name) {
                Button("Default") { action(workflow.id, nil, nil) }
                ForEach(workflowRunProviderCache.providers.filter { $0.available }) { provider in
                    if provider.models.isEmpty {
                        Button(provider.name) { action(workflow.id, provider.id, nil) }
                    } else {
                        Menu(provider.name) {
                            ForEach(provider.models, id: \.self) { model in
                                Button(model) { action(workflow.id, provider.id, model) }
                            }
                        }
                    }
                }
            }
        }

        ForEach(folderKeys, id: \.self) { folderPath in
            Menu(folderLabel(for: folderPath)) {
                let inFolder = (grouped[folderPath] ?? []).sorted { $0.name < $1.name }
                ForEach(inFolder) { workflow in
                    Menu(workflow.name) {
                        Button("Default") { action(workflow.id, nil, nil) }
                        ForEach(workflowRunProviderCache.providers.filter { $0.available }) { provider in
                            if provider.models.isEmpty {
                                Button(provider.name) { action(workflow.id, provider.id, nil) }
                            } else {
                                Menu(provider.name) {
                                    ForEach(provider.models, id: \.self) { model in
                                        Button(model) { action(workflow.id, provider.id, model) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    /// "/Transcribe" → "Transcribe"; "/Catalogue/Sub" → "Sub" (last
    /// component, mirroring how Finder shows nested folders in menus).
    func folderLabel(for path: String) -> String {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmed.isEmpty { return path }
        return String(trimmed.split(separator: "/").last ?? Substring(trimmed))
    }
}
