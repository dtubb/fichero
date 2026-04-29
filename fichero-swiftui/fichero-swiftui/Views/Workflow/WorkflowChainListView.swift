import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.fichero.fichero", category: "WorkflowChainListView")

/// View for browsing and managing workflow chains
struct WorkflowChainListView: View {
    @StateObject private var chainService: ChainService
    @EnvironmentObject var workflowStore: WorkflowStore
    @State private var searchText = ""
    @State private var selectedChainId: String?
    @State private var showNewChainSheet = false
    @State private var showDeleteConfirmation = false
    @State private var chainToDelete: WorkflowChain?
    @State private var executingChainId: String?

    init(apiClient: APIClient) {
        _chainService = StateObject(wrappedValue: ChainService(apiClient: apiClient))
    }

    var body: some View {
        ChainListContent(
            filteredChains: filteredChains,
            isLoading: chainService.isLoading,
            chainsEmpty: chainService.chains.isEmpty,
            searchText: searchText,
            executingChainId: executingChainId,
            onNewChain: { showNewChainSheet = true },
            onSelectChain: { selectedChainId = $0 },
            onExecuteChain: { executeChain($0) },
            onConfirmDelete: { confirmDelete($0) },
            onRefresh: {
                Task {
                    guard FeatureManager.shared.isWorkflowChainsEnabled else {
                        chainService.chains = []
                        return
                    }
                    await chainService.loadChains()
                }
            }
        )
        .searchable(text: $searchText, prompt: "Search chains...")
        .task {
            guard !Task.isCancelled else { return }
            guard FeatureManager.shared.isWorkflowChainsEnabled else {
                chainService.chains = []
                return
            }
            await chainService.loadChains()
        }
        .sheet(isPresented: $showNewChainSheet) {
            NewChainSheet(
                workflows: workflowStore.workflows,
                onCreate: { name, description, steps in
                    await createChain(name: name, description: description, steps: steps)
                }
            )
        }
        .sheet(item: selectedChain) { chain in
            ChainDetailSheet(
                chain: chain,
                workflows: workflowStore.workflows,
                onExecute: { executeChain(chain) },
                onDelete: { confirmDelete(chain) }
            )
        }
        .alert("Delete Chain?", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) {
                chainToDelete = nil
            }
            Button("Delete", role: .destructive) {
                if let chain = chainToDelete {
                    Task { await deleteChain(chain) }
                }
            }
        } message: {
            if let chain = chainToDelete {
                Text("Are you sure you want to delete \"\(chain.name)\"? This action cannot be undone.")
            }
        }
    }

    private var selectedChain: Binding<WorkflowChain?> {
        Binding(
            get: {
                guard let id = selectedChainId else { return nil }
                return chainService.chains.first { $0.id == id }
            },
            set: { newChain in
                selectedChainId = newChain?.id
            }
        )
    }

    private var filteredChains: [WorkflowChain] {
        if searchText.isEmpty {
            return chainService.chains
        }
        return chainService.chains.filter { chain in
            chain.name.localizedCaseInsensitiveContains(searchText) ||
                chain.description.localizedCaseInsensitiveContains(searchText)
        }
    }

    // MARK: - Actions

    private func createChain(name: String, description: String, steps: [ChainStep]) async {
        do {
            _ = try await chainService.createChain(
                name: name,
                description: description,
                steps: steps
            )
            logger.info("Created chain: \(name)")
        } catch {
            logger.error("Failed to create chain: \(error.localizedDescription)")
        }
    }

    private func deleteChain(_ chain: WorkflowChain) async {
        do {
            try await chainService.deleteChain(chain.id)
            if selectedChainId == chain.id {
                selectedChainId = nil
            }
            logger.info("Deleted chain: \(chain.name)")
        } catch {
            logger.error("Failed to delete chain: \(error.localizedDescription)")
        }
    }

    private func confirmDelete(_ chain: WorkflowChain) {
        chainToDelete = chain
        showDeleteConfirmation = true
    }

    private func executeChain(_ chain: WorkflowChain) {
        executingChainId = chain.id
        Task {
            do {
                let response = try await chainService.executeChain(chainId: chain.id)
                logger.info("Started chain execution: \(response.executionId)")

                let result = try await chainService.waitForExecution(response.executionId) { status in
                    logger.debug("Chain progress: \(status.status)")
                }

                logger.info("Chain completed with status: \(result.status)")
            } catch {
                logger.error("Chain execution failed: \(error.localizedDescription)")
            }
            executingChainId = nil
        }
    }
}

#Preview {
    WorkflowChainListView(apiClient: APIClient())
}
