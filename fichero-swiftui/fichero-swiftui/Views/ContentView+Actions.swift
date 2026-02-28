import SwiftUI
import OSLog

// MARK: - ContentView Actions Extension
// Agent: ActionsAgent
// Responsibility: All action handlers, event handlers, and business logic methods

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ContentView")

extension ContentView {

    // MARK: - Pane Focus Cycling

    /// Cycle keyboard focus between sidebar, content, and inspector panes
    func cyclePaneFocus(reverse: Bool) {
        var panes: [PaneFocus] = [.sidebar, .content]
        if showInspectorSidebar {
            panes.append(.inspector)
        }

        guard let current = focusedPane, let idx = panes.firstIndex(of: current) else {
            // No pane focused — default to content
            focusedPane = .content
            return
        }

        if reverse {
            focusedPane = panes[(idx - 1 + panes.count) % panes.count]
        } else {
            focusedPane = panes[(idx + 1) % panes.count]
        }
    }

    // MARK: - Document Change Handler

    @MainActor
    func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated:
            break

        case .collectionSelected(let collection):
            selectedSidebarItemId = collection.id

        case .documentsUpdated:
            break

        case .documentDeleted(let document):
            browserSelection.remove(document.id)
            if detailDocument?.id == document.id {
                detailDocument = nil
            }

        case .documentCreated:
            break
        }
    }

    // MARK: - UI Actions

    func toggleSidebar() {
        withAnimation {
            if columnVisibility == .all {
                columnVisibility = .doubleColumn
            } else {
                columnVisibility = .all
            }
        }
    }

    func updateColumnVisibility() {
        withAnimation {
            if showInspectorSidebar {
                columnVisibility = .all
            } else {
                columnVisibility = .doubleColumn
            }
        }
    }

    // MARK: - Workflow Actions

    func addNodeFromTool(_ tool: ToolInfo, at position: CGPoint) {
        let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
        editingWorkflow.nodes.append(newNode)
        logger.info("Added node '\(tool.displayName)' at (\(position.x), \(position.y))")
    }

    @MainActor
    func autoSaveWorkflow(workflowId: String, workflow: Workflow) async {
        guard !workflow.nodes.isEmpty || !workflow.name.isEmpty else {
            logger.info("Auto-save skipped: empty workflow")
            return
        }

        logger.info("Auto-saving workflow: \(workflow.name) (id: \(workflowId))")
        for node in workflow.nodes {
            let provider = node.providerName ?? "nil"
            let model = node.modelName ?? "nil"
            print(
                "[DEBUG SAVE] Node \(node.id): providerName=\(provider), modelName=\(model)"
            )
        }
        do {
            let definition = workflow.toAPIFormat()
            _ = try await workflowStore.updateWorkflow(definition)
            logger.info("Auto-save completed for workflow: \(workflowId)")
        } catch {
            logger.error("Auto-save failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Navigation

    func navigateToDocument(_ doc: Document) {
        viewMode = .library(doc)
        selectedSidebarItemId = doc.id
    }

    // MARK: - Conversations

    func refreshConversations() {
        Task { @MainActor in
            do {
                try await conversationService.loadConversations()
            } catch {
                logger.error("Failed to refresh conversations: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Saved Searches

    func refreshSavedSearches() {
        Task { @MainActor in
            do {
                try await savedSearchService.loadSavedSearches()
            } catch {
                logger.error("Failed to refresh saved searches: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - File Import

    func handleFileDrop(urls: [URL]) {
        logger.info("Files dropped: \(urls.map { $0.lastPathComponent })")

        var targetParentId: String?
        if case .library(let doc) = viewMode {
            targetParentId = doc?.id
        }

        Task { @MainActor in
            isImporting = true
            importError = nil

            var successCount = 0
            var failedFiles: [String] = []

            for url in urls {
                do {
                    guard url.isFileURL else {
                        logger.warning("Skipping non-file URL: \(url)")
                        continue
                    }

                    await MainActor.run {
                        importProgress = "Importing \(url.lastPathComponent)..."
                    }

                    logger.info("Importing file: \(url.path)")
                    _ = try await documentStore.importFile(at: url, parentId: targetParentId)
                    successCount += 1

                } catch {
                    logger.error("Failed to import \(url.lastPathComponent): \(String(describing: error))")
                    failedFiles.append(url.lastPathComponent)
                }
            }

            await MainActor.run {
                isImporting = false
                importProgress = nil

                if !failedFiles.isEmpty {
                    let fileList = failedFiles.joined(separator: ", ")
                    importError = "Failed to import \(failedFiles.count) file(s): \(fileList)"
                }

                if successCount > 0 {
                    Task { @MainActor in
                        await documentStore.loadCollections()
                        logger.info("Successfully imported \(successCount) file(s)")
                    }
                }
            }
        }
    }
}
