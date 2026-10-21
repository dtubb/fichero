import FicheroAPIClient
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
                // File › New Folder's own item (#5652), into this folder.
                NewFolderMenuItem(create: {
                    // Select the clicked row first so the create targets its
                    // library (createFolder resolves via selectedItemLibrary).
                    selectedItemId = "doc:\(folderDoc.id)"
                    sidebarState.newFolderParentId = folderDoc.id
                    sidebarState.newFolderCategory = .folder
                    sidebarState.showingNewFolderDialog = true
                })
                // Share… this folder alone (#5967): offered where a project's Share… is, with Multi-user on.
                if EngineConfig.multiuserEnabled, let libraryId = item.libraryId {
                    Button("Share…") {
                        sidebarState.folderToShare = FolderShareTarget(
                            libraryId: libraryId, folderId: folderDoc.id, name: folderDoc.name)
                    }
                    .accessibilityIdentifier("sidebar.folder.share")
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
                automation: automationTarget,
                onDuplicate: workflowDuplicateAction,
                onMakeAlias: makeAliasAction
            )

            // Show Original in Finder (#4305) — every document row, same
            // shared policy as the grid menu: local engine + the path resolves
            // on this machine; linked originals get the Finder-alias verb.
            if case .document(let revealDoc) = item.itemType {
                RevealOriginalMenuItem(document: revealDoc)
            }

            // Grid-menu parity (#4121, extended 2026-08-20): the curation
            // and organization items the library grid offers, on EVERY
            // document row — folders included (the user: "sidebar and
            // library contextual menus ought to be same"; the library menu
            // excludes folders fine, and folder exclusion is the common
            // curation move for front/back matter). Export stays file-only —
            // a folder has no single source file to copy out.
            if case .document(let processDoc) = item.itemType {
                // The item verbs, as Edit renders them and the Items list's menu does (#5652): one item each.
                let verbs = rowItemVerbs(processDoc)
                ExcludeItemsMenuItem(target: verbs, exclusion: .processing)
                ExcludeItemsMenuItem(target: verbs, exclusion: .search)
                ExcludeItemsMenuItem(target: verbs, exclusion: .everywhere)
                // Same-parity picker sheets (#4121): saved-pointer bookmark
                // and workspace membership, presented from this row.
                BookmarkItemMenuItem(target: verbs)
                AddToWorkspaceMenuItem(target: verbs)
                if processDoc.docType == .folder {
                    // Find the Documents (#5550): the Project menu's own item, as the library grid offers it.
                    FindDocumentsMenuItem(scopeIds: [processDoc.id], library: library)
                    // Run the Recipe on This Folder… (#5540): the Project menu's own item.
                    RunRecipeOnFolderMenuItem(folderId: processDoc.id, library: library)
                }
                #if os(macOS)
                if processDoc.docType != .folder {
                    // Export a Copy… of the source file (#4121), the shared item (#5652).
                    ExportCopyMenuItem(target: verbs)
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
                // Run Workflow ▸'s one shell (#5652): it says what the run reaches before the click — never
                // silently discarding a selection (#4396), never silently widening one (2026-08-15).
                RunWorkflowMenuItem(
                    targetCount: resolution.isEmpty ? 0 : resolution.targetIds.count,
                    ignoredSelection: resolution.ignoredSelection
                ) {
                        // Two named groups (#4450): a global default is part
                        // of the app and must read as one wherever you are.
                        let sections = Self.workflowMenuSections(availableWorkflows)
                        if !sections.defaults.isEmpty {
                            Section("Global Defaults") {
                                workflowSubmenu(sections.defaults, resolution: resolution)
                            }
                        }
                        if !sections.libraryOwn.isEmpty {
                            if let heading = Self.ownWorkflowsHeading(projectName: library?.displayName) {
                                Section(heading) {
                                    workflowSubmenu(sections.libraryOwn, resolution: resolution)
                                }
                            } else {
                                // The always-there project has no name: its workflows sit under no heading.
                                Section {
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
                try await UndoableChange.invoke(
                    "document.duplicate", params: DocumentDuplicateActionParams(docId: doc.id, parentId: nil),
                    named: "Duplicate", service: library.actionsService, steps: windowState.steps
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
    /// The item verbs on this row's document (#5652): the same shared items Edit and the Items list render.
    /// Exclusion is the one shared operation (`ItemVerbs.setExcluded`); the pickers are this row's own sheets,
    /// as sidebar rows span projects.
    private func rowItemVerbs(_ doc: Document) -> ItemVerbsTarget {
        var target = ItemVerbsTarget(ids: [doc.id], documents: [doc])
        if let library {
            target.setExcluded = { exclusion, excluded in
                Task { @MainActor in
                    do {
                        try await ItemVerbs.setExcluded(
                            [doc.id], excluded: excluded, exclusion, using: library.documentService, refreshing: library.documentStore
                        )
                    } catch {
                        sidebarRowLogger.error(
                            "exclude toggle for \(doc.id, privacy: .public) failed: \(error.localizedDescription)"
                        )
                    }
                }
            }
        }
        target.bookmark = { bookmarkPickerDocument = doc }
        target.addToWorkspace = { workspacePickerDocument = doc }
        #if os(macOS)
        if doc.docType != .folder {
            let dragID = SidebarDragID(item: item)
            target.export = {
                DocumentExporter.exportViaSavePanel(dragID) { message in
                    sidebarState.dropErrorMessage = message
                }
            }
        }
        #endif
        return target
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
            // Project › Chat ▸ Add to Chat's own item (#5652).
            AddToChatMenuItem(add: {
                selectedItemId = item.id
                Task { @MainActor in
                    onOpenChatWithCurrentScope()
                }
            })
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
