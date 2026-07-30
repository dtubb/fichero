import OSLog
import SwiftUI

/// Structured logger for sidebar creation operations
private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarCreation")

// MARK: - Creation Methods Extension

extension SidebarView {
    /// Create a new chat - defaults to Global library
    func createNewChat() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                // #4308: create through the audited `conversation.create`
                // endpoint — instant and provider-independent. The old path
                // POSTed a real LLM turn ("Hello"); with no provider/API key
                // configured it failed silently and the sidebar showed nothing.
                // createConversation appends to the service's conversations
                // array itself (one item, in place).
                let newConv = try await globalLibrary.conversationService
                    .createConversation()

                // Rebuild caches so sidebar shows the new chat
                rebuildCaches()

                // Select the new chat
                selectedItemId = "chat:\(newConv.id)"
                sidebarMode = .chat  // Switch to chat sidebar
                viewMode = .chat(newConv)
                logger.info("Created new chat: \(newConv.id)")

            } catch {
                logger.error("Failed to create chat: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new saved workspace (#4308/#4335): a workspace node (folder +
    /// `is_workspace`) in the CURRENT window's library, selected in the
    /// sidebar, opening the Research surface. `createWorkspace` reloads the
    /// document collections, so the node appears in this window's tree
    /// immediately; other windows follow through the document change stream.
    func createNewWorkspace() {
        guard let library = libraryManager.getLibrary(id: windowState.libraryId)
            ?? libraryManager.globalLibrary else {
            logger.error("No library available for workspace creation")
            return
        }

        Task {
            do {
                let workspace = try await library.documentStore.createWorkspace(name: "New Workspace")
                rebuildCaches()
                selectedItemId = "doc:\(workspace.id)"
                sidebarMode = .research
                logger.info("Created new workspace: \(workspace.id)")
            } catch {
                logger.error("Failed to create workspace: \(error.localizedDescription)")
                library.documentStore.error = error
            }
        }
    }

    /// Create a new workflow - defaults to Global library
    func createNewWorkflow() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                let newWorkflowDef = WorkflowDefinition(
                    id: UUID().uuidString,
                    name: "New Workflow",
                    description: "",
                    provider: "",
                    model: "",
                    nodes: [],
                    edges: [],
                    folderPath: "/",
                    sortOrder: 0
                )
                let response = try await globalLibrary.workflowService.createWorkflow(newWorkflowDef)
                await globalLibrary.workflowStore.loadWorkflows()
                rebuildCaches()
                let workflowItem = WorkflowSidebarItem(
                    id: response.id,
                    name: response.name,
                    description: response.description,
                    nodeCount: response.nodes.count,
                    isEnabled: true,
                    folderPath: response.folderPath,
                    sortOrder: response.sortOrder,
                    createdAt: Date(),
                    updatedAt: Date()
                )
                selectedItemId = "workflow:\(workflowItem.id)"
                sidebarMode = .workflows  // Switch to workflows sidebar
                viewMode = .workflow(workflowItem)
                logger.info("Created new workflow: \(workflowItem.id)")
            } catch {
                logger.error("Failed to create workflow: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new folder - defaults to Global library
    func handleCreateNewFolder() {
        guard libraryManager.globalLibrary != nil else {
            logger.error("Global library not available")
            return
        }
        // Finder semantics (#4121): New Folder nests into the SELECTED
        // folder; with no folder selected it lands at the library root.
        if let selectedId = selectedItemId,
           let selected = cachedItem(id: selectedId),
           case .document(let doc) = selected.itemType, doc.docType == .folder {
            sidebarState.newFolderParentId = doc.id
        } else {
            sidebarState.newFolderParentId = nil
        }
        sidebarState.showingNewFolderDialog = true
        sidebarState.newFolderCategory = .folder
    }

    /// Create a new chain via ChainService
    func createNewChain() {
        logger.info("Creating new chain")
        Task {
            do {
                let chainService = ChainService(apiClient: apiClient)
                let newChain = try await chainService.createChain(
                    name: "New Chain",
                    description: "",
                    steps: []
                )

                // Switch to workflows mode and select the new chain.
                // ID must be `chain:<id>` (colon separator) to match
                // SidebarItem.fromChain's prefix convention. The previous
                // `chain-<id>` (dash) form broke extractActualId's
                // colon-split and caused SidebarItemKind to misclassify
                // new chains as .document, silently misrouting every
                // drag/rename/lookup on them. Sidebar review 2026-04-17.
                sidebarMode = .workflows
                selectedItemId = "chain:\(newChain.id)"
                viewMode = .chain(newChain)
                logger.info("Created new chain: \(newChain.id)")
            } catch {
                logger.error("Failed to create chain: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new comparison - opens the comparison view
    func createNewComparison() {
        logger.info("Creating new comparison")
        sidebarMode = .chat
        viewMode = .comparison(nil)
    }

    /// Create a new schedule - shows the schedule creation sheet
    func createNewSchedule() {
        logger.info("Creating new schedule")
        sidebarMode = .automation
        sidebarState.showingScheduleCreation = true
    }

    /// Create a new trigger - shows the trigger creation sheet
    func createNewTrigger() {
        logger.info("Creating new trigger")
        sidebarMode = .automation
        sidebarState.showingTriggerCreation = true
    }

    /// Actually create the folder after user enters name
    func createFolder(_ name: String) async {
        let targetLibrary = selectedItemLibrary ?? libraryManager.globalLibrary
        guard let library = targetLibrary else {
            sidebarState.newFolderErrorMessage = "No library available"
            return
        }
        let parentId = sidebarState.newFolderParentId
        logger.info("Creating folder '\(name)' in library: \(library.displayName) parent: \(parentId ?? "root")")
        do {
            // Honor the dialog's parent target (#4121) — previously
            // newFolderParentId existed but was never read, so every new
            // folder landed at the library root.
            let newFolder = try await library.documentStore.createFolder(
                name: name, parentId: parentId
            )
            logger.info("Created folder: \(name)")
            rebuildCaches()
            // Select the just-created folder so the user can immediately see its
            // contents (empty) in the grid — matches the behavior for newly
            // created searches/chats/workflows (#573).
            selectedItemId = "doc:\(newFolder.id)"
        } catch {
            logger.error("Failed to create folder: \(error)")
            sidebarState.newFolderErrorMessage = error.localizedDescription
        }
    }
}
