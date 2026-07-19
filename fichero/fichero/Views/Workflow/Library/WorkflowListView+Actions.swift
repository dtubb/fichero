import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowLibraryView")

// Data loading, CRUD, selection, and import/export actions for WorkflowListView.
// Split out of WorkflowLibraryView to keep the type body under the SwiftLint
// threshold.
extension WorkflowListView {
    func loadWorkflows() async {
        isLoading = true
        defer { isLoading = false }
        await workflowStore.loadWorkflows()
    }

    func createWorkflow(name: String, description: String) async {
        do {
            let workflowDef = WorkflowDefinition(
                name: name,
                description: description,
                nodes: [],
                edges: []
            )
            let newWorkflow = try await workflowStore.saveWorkflow(workflowDef)
            selectedWorkflowId = newWorkflow.id
            logger.info("Created workflow: \(newWorkflow.name)")
        } catch {
            logger.error("Failed to create workflow: \(String(describing: error))")
        }
    }

    func openWorkflow(_ workflow: WorkflowSidebarItem) {
        // Use callback instead of NotificationCenter (SwiftUI best practice)
        onOpenWorkflow?(workflow)
    }

    func confirmDelete(_ workflow: WorkflowSidebarItem) {
        confirmDelete([workflow])
    }

    func confirmDelete(_ workflows: [WorkflowSidebarItem]) {
        workflowsToDelete = workflows
        showDeleteConfirmation = !workflows.isEmpty
    }

    func deleteSelection(containing workflow: WorkflowSidebarItem? = nil) -> [WorkflowSidebarItem] {
        let selection = currentDeletionSelection
        guard let workflow else { return selection }
        if selection.contains(where: { $0.id == workflow.id }) {
            return selection
        }
        return [workflow]
    }

    var currentDeletionSelection: [WorkflowSidebarItem] {
        var selectedIds = selectedWorkflowIds
        if let selectedWorkflowId {
            selectedIds.insert(selectedWorkflowId)
        }
        guard !selectedIds.isEmpty else { return [] }
        return workflowStore.workflows.filter { workflow in
            selectedIds.contains(workflow.id) && !workflow.isSystem
        }
    }

    func promptDeleteSelected() {
        confirmDelete(currentDeletionSelection)
    }

    func deleteWorkflows(_ workflows: [WorkflowSidebarItem]) async {
        do {
            for workflow in workflows {
                try await workflowStore.deleteWorkflow(workflow.id)
            }
            let deletedIds = Set(workflows.map(\.id))
            selectedWorkflowIds.subtract(deletedIds)
            selectedWorkflowId = selectedWorkflowIds.first
            workflowsToDelete = []
            logger.info("Deleted \(workflows.count, privacy: .public) workflow(s)")
        } catch {
            logger.error("Failed to delete workflows: \(String(describing: error))")
        }
    }

    func duplicateWorkflow(_ workflow: WorkflowSidebarItem) {
        Task {
            do {
                let duplicate = try await workflowStore.duplicateWorkflow(workflow.id)
                selectedWorkflowId = duplicate.id
                logger.info("Duplicated workflow: \(workflow.name)")
            } catch {
                logger.error("Failed to duplicate workflow: \(String(describing: error))")
            }
        }
    }

    func executeWorkflow(_ workflow: WorkflowSidebarItem) {
        // Execution is handled by WorkflowDetailView which has direct access to workflowStore
        logger.info("Execute requested for workflow: \(workflow.name)")
    }

    func importWorkflow() {
        isImporting = true
        Task {
            do {
                if let importedId = try await WorkflowExporter.importFromFile(using: workflowService) {
                    await loadWorkflows()
                    selectedWorkflowId = importedId
                }
            } catch {
                logger.error("Failed to import workflow: \(error.localizedDescription)")
            }
            isImporting = false
        }
    }

    func exportWorkflow(_ workflow: WorkflowSidebarItem) {
        Task {
            await WorkflowExporter.exportToFile(
                workflow.id,
                name: workflow.name,
                using: workflowService
            )
        }
    }

    // installDefaultWorkflows() removed at #930 fix — Reset is a
    // superset (adds missing AND replaces user-edited) so the
    // separate Install action was redundant + confusing.

    func resetDefaultWorkflows() async {
        guard !isManagingDefaults else { return }
        isManagingDefaults = true
        defer { isManagingDefaults = false }

        do {
            let created = try await workflowStore.resetDefaultWorkflowTemplates()
            templateOperationMessage = created.isEmpty
                ? "Default workflows are already up to date."
                : "Reinstalled \(created.count) default workflow\(created.count == 1 ? "" : "s")."
        } catch {
            templateOperationMessage = "Failed to reset defaults: \(error.localizedDescription)"
        }
    }
}
