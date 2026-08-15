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

            // Show Original in Finder (#4305) — every document row, same
            // shared policy as the grid menu: local engine + the path resolves
            // on this machine; linked originals get the Finder-alias verb.
            if case .document(let revealDoc) = item.itemType {
                RevealOriginalMenuItem(document: revealDoc)
            }

            // Grid-menu parity (#4121): the processing toggle the library
            // grid offers, for the same document, on its sidebar row.
            if case .document(let processDoc) = item.itemType, processDoc.docType != .folder {
                Button(
                    processDoc.excludeFromProcessing
                        ? "Include in Processing" : "Exclude from Processing"
                ) {
                    toggleExcludeFromProcessing(processDoc)
                }
                // Same-parity picker sheets (#4121): saved-pointer bookmark
                // and workspace membership, presented from this row.
                Button {
                    bookmarkPickerDocument = processDoc
                } label: {
                    Label("Bookmark…", systemImage: "bookmark")
                }
                Button {
                    workspacePickerDocument = processDoc
                } label: {
                    Label("Add to Workspace…", systemImage: "square.grid.2x2")
                }
                #if os(macOS)
                // Export a real copy of the source file (#4121) — the same
                // storage-service path the Finder drag-out uses (#4123).
                Button {
                    DocumentExporter.exportViaSavePanel(SidebarDragID(item: item)) { message in
                        sidebarState.dropErrorMessage = message
                    }
                } label: {
                    Label("Export…", systemImage: "square.and.arrow.up")
                }
                #endif
            }

            let resolution = resolvedWorkflowRun
            let availableWorkflows = Self.contextMenuWorkflows(
                own: workflowStore?.workflows ?? [],
                global: libraryManager.globalLibrary?.workflowStore.workflows ?? []
            )
            // #4419: the menu is NOT gated on the target list being non-empty
            // any more. That gate is how "nothing in Marshall can be run" was
            // produced — a cross-library row resolved to nothing and the whole
            // submenu vanished, which reads as an unsupported feature rather
            // than a failure. The resolver now always yields a target, and if
            // it somehow cannot, the disabled row below names the reason.
            if !availableWorkflows.isEmpty {
                Divider()
                Menu("Run Workflow") {
                    if resolution.isEmpty {
                        Button("Nothing to run on") {}
                            .disabled(true)
                    } else {
                        // Silently discarding a selection is the same defect as
                        // silently widening one (#4396) — so say it, in the menu,
                        // before the run rather than after.
                        if resolution.ignoredSelection {
                            Text("Runs on this item only — it is outside your selection")
                            Divider()
                        }
                        // Two named groups (#4450): a global default is part
                        // of the app and must read as one wherever you are.
                        let sections = Self.workflowMenuSections(availableWorkflows)
                        if !sections.defaults.isEmpty {
                            Section("Global Defaults") {
                                workflowSubmenu(sections.defaults, resolution: resolution)
                            }
                        }
                        if !sections.libraryOwn.isEmpty {
                            Section(library?.displayName ?? "This Library") {
                                workflowSubmenu(sections.libraryOwn, resolution: resolution)
                            }
                        }
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

    /// #4275 — the workflow list the Run Workflow submenu offers for this row.
    ///
    /// A row's own library store is authoritative (its list is what the run
    /// executes against, #3820). But a non-global library whose store hasn't
    /// loaded (or failed to load) used to make the submenu silently VANISH on
    /// its folders. Fall back to the global library's list so the menu is
    /// never silently empty; the run still targets this row's documents in
    /// this row's library, and a genuinely unknown workflow id surfaces the
    /// engine's error on the banner rather than nothing at all.
    /// One group of the Run Workflow menu. Both sections run the SAME action
    /// against the SAME targets — the split is presentational.
    @ViewBuilder
    private func workflowSubmenu(
        _ workflows: [WorkflowSidebarItem],
        resolution: WorkflowRunTargetResolver.Resolution
    ) -> some View {
        RunWorkflowSubmenuItems(workflows: workflows) { workflowId, provider, model in
            runWorkflowOnDocuments(
                workflowId: workflowId,
                docIds: resolution.targetIds,
                providerOverride: provider,
                modelOverride: model
            )
        }
    }

    /// #4450 — the fallback is filtered to `isSystem`. A global-library USER
    /// workflow (built while Global was open, or a preset DEMOTED by editing
    /// it, #780) is not a default; `resolve_default_workflow` refuses it from
    /// another library, so offering it is the menu asserting availability it
    /// has not established.
    nonisolated static func contextMenuWorkflows(
        own: [WorkflowSidebarItem],
        global: [WorkflowSidebarItem]
    ) -> [WorkflowSidebarItem] {
        own.isEmpty ? global.filter(\.isSystem) : own
    }

    /// #4450 — the two groups: global defaults, visible and runnable in EVERY
    /// library, and this library's own. Both come from ONE list: a non-global
    /// library's `/api/workflows` already merges the shipped defaults in
    /// server-side (`list_global_default_workflows`), so re-reading the global
    /// store here would list every default twice. The split is `isSystem`, the
    /// flag only the seeder writes.
    nonisolated static func workflowMenuSections(
        _ workflows: [WorkflowSidebarItem]
    ) -> (defaults: [WorkflowSidebarItem], libraryOwn: [WorkflowSidebarItem]) {
        (workflows.filter(\.isSystem), workflows.filter { !$0.isSystem })
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
    /// Same executor as the grid menu (#4121): batchExclude + local refresh.
    private func toggleExcludeFromProcessing(_ doc: Document) {
        guard let library else { return }
        Task { @MainActor in
            do {
                let refreshed = try await library.documentService.batchExclude(
                    documentIds: [doc.id],
                    excluded: !doc.excludeFromProcessing
                )
                for updated in refreshed {
                    library.documentStore.refreshLocalContent(updated)
                }
            } catch {
                sidebarRowLogger.error(
                    "exclude toggle for \(doc.id, privacy: .public) failed: \(error.localizedDescription)"
                )
            }
        }
    }

    private var makeAliasAction: (() -> Void)? {
        guard case .document(let doc) = item.itemType, let library else { return nil }
        // Aliasing an alias targets the ORIGINAL (Finder: no alias chains).
        let targetId = doc.isAlias ? (doc.aliasTargetId ?? doc.id) : doc.id
        return {
            Task { @MainActor in
                let created = await library.bookmarkService.createBookmark(
                    targetId: targetId,
                    // #116: was "\(doc.name) alias" — a storage filename
                    // written INTO the engine, not merely onto the screen.
                    name: AliasName.forAlias(of: doc, targetParentId: doc.parentId),
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
            lookupItem($0.serializedID)
        }
    }

    /// #4419: resolves against the row's own identity first, so a row in a
    /// library whose store this view does not hold still runs. `documents` is
    /// only ever an EXPANSION hint for folders now — never a membership gate —
    /// so an unloaded or cross-library store degrades to "run this row" instead
    /// of to nothing.
    private var resolvedWorkflowRun: WorkflowRunTargetResolver.Resolution {
        guard let clickedTarget = workflowRunTarget(for: item) else {
            return WorkflowRunTargetResolver.Resolution(
                targetIds: [],
                ignoredSelection: false,
                usedRowIdentityFallback: false
            )
        }
        // #4523 LAW: the run's selection is the WINDOW's document selection,
        // not just the sidebar's own. The library-pane selection (live or
        // preserved across the navigation that cleared it, #712 carve-out)
        // is what makes right-clicking the selected file's row run THAT file
        // rather than its peers.
        //
        // #4552: these two are separate DOMAINS and must not be unioned. See
        // `selectionScope` — a union let the clicked row arrive from one
        // domain while the extra targets came from the other, which `resolve`
        // cannot tell apart from a real multi-selection. That ran a workflow
        // on a PDF the user had not touched in an hour.
        let sidebarSelection = Set(selectedDestinations.compactMap(workflowRunTarget(for:)))
        // LIVE pane selection only (2026-08-15): a stale preserved snapshot
        // containing the clicked file once ran a one-file job on 200 siblings.
        let windowSelection = Set(
            windowState.liveDocumentSelection.map { WorkflowRunTarget.file($0) }
        )
        return WorkflowRunTargetResolver.resolve(
            clicked: clickedTarget,
            selection: WorkflowRunTargetResolver.selectionScope(
                clicked: clickedTarget,
                sidebarSelection: sidebarSelection,
                windowSelection: windowSelection
            ),
            documents: documentStore?.sidebarDocuments ?? []
        )
    }

    private func workflowRunTarget(for item: SidebarItem) -> WorkflowRunTarget? {
        guard case .document(let document) = item.itemType else { return nil }
        return document.docType == .folder ? .folder(document.id) : .file(document.id)
    }

    private func workflowRunTarget(for destination: SidebarDestination) -> WorkflowRunTarget? {
        guard case .document = destination,
              let item = lookupItem(destination.serializedID) else {
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
}
