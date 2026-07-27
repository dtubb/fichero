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
                let response = try await globalLibrary.chatService.chat(
                    message: "Hello",
                    conversationId: nil,
                    documentIds: nil
                )

                // Create conversation directly from response (don't rely on lookup which may have timing issues)
                let newConv = Conversation(
                    id: response.conversationId,
                    title: "New Chat",
                    messages: [
                        ChatMessage(role: .user, content: "Hello"),
                        ChatMessage(role: .assistant, content: response.message)
                    ],
                    documentScope: [],
                    folderPath: "/",
                    sortOrder: 0
                )

                // Add to service's conversations array
                globalLibrary.conversationService.conversations.append(newConv)

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
        logger.info("Creating folder '\(name)' in library: \(library.displayName)")
        do {
            let newFolder = try await library.documentStore.createCollection(name: name)
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
