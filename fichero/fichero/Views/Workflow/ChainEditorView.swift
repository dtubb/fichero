import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ChainEditorView")

/// Editor view for a workflow chain
/// Uses the ChainDetailContent as the main content
struct ChainEditorView: View {
    let chain: WorkflowChain
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(APIClient.self) var apiClient
    @State private var isExecuting = false
    @State private var showDeleteConfirmation = false

    var body: some View {
        ChainDetailContent(
            chain: chain,
            workflows: workflowStore.workflows,
            onExecute: executeChain,
            onDelete: { showDeleteConfirmation = true }
        )
        .alert("Delete Chain?", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                Task { await deleteChain() }
            }
        } message: {
            Text("Are you sure you want to delete \"\(chain.name)\"? This action cannot be undone.")
        }
    }

    private func executeChain() {
        guard !isExecuting else { return }
        isExecuting = true
        Task {
            do {
                let chainService = ChainService(apiClient: apiClient)
                let response = try await chainService.executeChain(chainId: chain.id)
                logger.info("Started chain execution: \(response.executionId)")
            } catch {
                logger.error("Chain execution failed: \(error.localizedDescription)")
            }
            isExecuting = false
        }
    }

    private func deleteChain() async {
        do {
            let chainService = ChainService(apiClient: apiClient)
            try await chainService.deleteChain(chain.id)
            logger.info("Deleted chain: \(chain.name)")
        } catch {
            logger.error("Failed to delete chain: \(error.localizedDescription)")
        }
    }
}
