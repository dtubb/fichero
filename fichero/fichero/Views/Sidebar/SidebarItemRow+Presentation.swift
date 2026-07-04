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
                renameState: renameState,
                deleteState: deleteState,
                onPause: onAutomationPause,
                onResume: onAutomationResume,
                onTrigger: onAutomationTrigger,
                onCancel: onAutomationCancel
            )

            if case .document(let doc) = item.itemType,
               let workflows = workflowStore?.workflows, !workflows.isEmpty {
                Divider()
                Menu("Run Workflow") {
                    workflowMenuItems(workflows: workflows) { workflowId, providerOverride, modelOverride in
                        runWorkflowOnDocument(
                            workflowId: workflowId,
                            docId: doc.id,
                            providerOverride: providerOverride,
                            modelOverride: modelOverride
                        )
                    }
                }
                .onAppear {
                    Task { @MainActor in
                        await workflowRunProviderCache.ensureLoaded(chatService: library?.chatServiceGenerated)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var compactTouchActions: some View {
        if horizontalSizeClass == .compact,
           case .document(let doc) = item.itemType {
            let folders = moveDestinationFolders(for: doc) ?? []

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
                            Task { await moveDocumentToFolder(documentId: doc.id, folderId: folder.id) }
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
