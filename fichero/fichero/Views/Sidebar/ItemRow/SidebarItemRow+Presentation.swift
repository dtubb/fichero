import SwiftUI

extension SidebarItemRow {
    var rowContextMenu: some View {
        Group {
            chatWithScopeAction
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

            // Creation INTO the right-clicked folder (#4121): Finder
            // semantics — the new folder nests under this row. Reuses the
            // shared New Folder dialog; `newFolderParentId` targets it.
            // (Binding named folderDoc: WorkflowContextMenuTargetsTests guards
            // against the old single-doc workflow-target pattern by string.)
            if case .document(let folderDoc) = item.itemType, folderDoc.docType == .folder {
                Button("New Folder") {
                    // Select the clicked row first so the create targets its
                    // library (createFolder resolves via selectedItemLibrary).
                    selectedItemId = "doc:\(folderDoc.id)"
                    sidebarState.newFolderParentId = folderDoc.id
                    sidebarState.newFolderCategory = .folder
                    sidebarState.showingNewFolderDialog = true
                }
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
                onDuplicate: workflowDuplicateAction,
                onMakeAlias: makeAliasAction
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

    /// Duplicate action for the kinds with a backend duplicate endpoint —
    /// workflows, saved searches, conversations (nil hides the menu item).
    /// Backend owns id/naming; the store/service reload republishes the
    /// sidebar. Failures surface via the shared drop-error banner rather
    /// than vanishing into the log (prefer-raise-over-silent-fallback).
    private var workflowDuplicateAction: (() -> Void)? {
        switch item.itemType {
        case .document(let doc):
            // Audited document.duplicate (deep copy beside the original) via
            // the same invokeAction path document.delete uses. Locked mirror
            // rows get the engine's 403 on the banner.
            guard let library else { return nil }
            return duplicateTask {
                _ = try await library.actionsService.invokeAction(
                    name: "document.duplicate",
                    params: DocumentDuplicateActionParams(docId: doc.id, parentId: nil)
                )
                await library.documentStore.refresh()
            }
        case .workflow(let workflow):
            guard let store = workflowStore else { return nil }
            return duplicateTask { _ = try await store.duplicateWorkflow(workflow.id) }
        case .savedSearch(let search):
            guard let service = savedSearchService else { return nil }
            return duplicateTask {
                _ = try await service.duplicateSavedSearch(search.id)
                try await service.loadSavedSearches()
            }
        case .conversation(let conversation):
            guard let service = conversationService else { return nil }
            return duplicateTask {
                _ = try await service.duplicateConversation(conversation.id)
                try await service.loadConversations()
            }
        default:
            return nil
        }
    }

    /// Finder-style Make Alias for document rows (#2591): a real engine alias
    /// node (via the bookmarks surface) beside the original — never a
    /// sidebar-only copy. The tree republishes on the store refresh.
    private var makeAliasAction: (() -> Void)? {
        guard case .document(let doc) = item.itemType, let library else { return nil }
        // Aliasing an alias targets the ORIGINAL (Finder: no alias chains).
        let targetId = doc.isAlias ? (doc.aliasTargetId ?? doc.id) : doc.id
        return {
            Task { @MainActor in
                let created = await library.bookmarkService.createBookmark(
                    targetId: targetId,
                    name: "\(doc.name) alias",
                    parentId: doc.parentId
                )
                if created {
                    await library.documentStore.refresh()
                } else {
                    sidebarState.dropErrorMessage = "Couldn’t create the alias."
                }
            }
        }
    }

    private func duplicateTask(_ body: @escaping () async throws -> Void) -> () -> Void {
        {
            Task { @MainActor in
                do {
                    try await body()
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

    /// Scoped chat, as a command on the node itself.
    ///
    /// Deliberately NOT size-class gated (#4102): this used to be compact-only
    /// because Mac reached document-scoped chat through the pinned "Chat with
    /// Docs" row at the sidebar's bottom. Retiring those rows left the
    /// capability wired (`onOpenChatWithCurrentScope` still threads all the way
    /// down) but unreachable on Mac — Data ▸ New Chat opens an UNSCOPED chat.
    /// A context-menu command on the document is the node-shaped home for it.
    @ViewBuilder
    private var chatWithScopeAction: some View {
        if case .document = item.itemType, let onOpenChatWithCurrentScope {
            Button {
                selectedItemId = item.id
                Task { @MainActor in
                    onOpenChatWithCurrentScope()
                }
            } label: {
                Label("Add to Chat", systemImage: "plus.circle")
            }
            Divider()
        }
    }

    /// Touch-only affordances. Move-to-Folder stays gated because Mac already
    /// has it through drag-and-drop; touch has no equivalent.
    @ViewBuilder
    private var compactTouchActions: some View {
        if horizontalSizeClass == .compact,
           case .document(let document) = item.itemType {
            let folders = moveDestinationFolders(for: document) ?? []

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

            if !folders.isEmpty {
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
        let grouped = Dictionary(grouping: workflows.filter(\.canRunDirectly)) { workflow in
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
