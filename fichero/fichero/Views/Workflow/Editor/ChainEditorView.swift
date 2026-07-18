import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ChainEditorView")

/// Editor view for a workflow chain
/// Uses the ChainDetailContent as the main content
struct ChainEditorView: View {
    let chain: WorkflowChain
    @Environment(ChainStore.self) var chainStore
    @Environment(WorkflowStore.self) var workflowStore
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
                let response = try await chainStore.executeChain(chainId: chain.id)
                logger.info("Started chain execution: \(response.executionId)")
            } catch {
                logger.error("Chain execution failed: \(error.localizedDescription)")
            }
            isExecuting = false
        }
    }

    private func deleteChain() async {
        do {
            try await chainStore.deleteChain(chain.id)
            logger.info("Deleted chain: \(chain.name)")
        } catch {
            logger.error("Failed to delete chain: \(error.localizedDescription)")
        }
    }
}
