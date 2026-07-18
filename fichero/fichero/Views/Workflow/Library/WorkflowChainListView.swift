import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowChainListView")

/// View for browsing and managing workflow chains
struct WorkflowChainListView: View {
    @Environment(ChainStore.self) var chainStore
    @Environment(WorkflowStore.self) var workflowStore
    @State private var searchText = ""
    @State private var selectedChainId: String?
    @State private var selectedChainIds: Set<String> = []
    @State private var showNewChainSheet = false
    @State private var showDeleteConfirmation = false
    @State private var chainsToDelete: [WorkflowChain] = []
    @State private var executingChainId: String?

    var body: some View {
        ChainListContent(
            filteredChains: filteredChains,
            isLoading: chainStore.isLoading,
            chainsEmpty: chainStore.chains.isEmpty,
            searchText: searchText,
            executingChainId: executingChainId,
            onNewChain: { showNewChainSheet = true },
            selectedChainIds: $selectedChainIds,
            onSelectChain: { selectedChainId = $0 },
            onExecuteChain: { executeChain($0) },
            onConfirmDelete: { confirmDelete($0) },
            onConfirmDeleteSelection: { confirmDeleteSelection() },
            onRefresh: {
                Task {
                    guard FeatureManager.shared.isWorkflowChainsEnabled else {
                        return
                    }
                    await chainStore.loadChains()
                }
            }
        )
        .onChange(of: selectedChainIds) { _, newValue in
            selectedChainId = newValue.first
        }
        // No per-view toolbar search: the toolbar search is global and always
        // searches files/documents (ContentView owns the single .searchable).
        // A second .searchable here is a duplicate com.apple.SwiftUI.search on
        // the same NSToolbar and crashes at launch (#3163). The list shows all.
        .task {
            guard !Task.isCancelled else { return }
            guard FeatureManager.shared.isWorkflowChainsEnabled else {
                return
            }
            await chainStore.loadChains()
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
                chainsToDelete = []
            }
            Button("Delete", role: .destructive) {
                let chains = chainsToDelete
                if !chains.isEmpty {
                    Task { await deleteChains(chains) }
                }
            }
        } message: {
            if chainsToDelete.count == 1, let chain = chainsToDelete.first {
                Text("Are you sure you want to delete \"\(chain.name)\"? This action cannot be undone.")
            } else if !chainsToDelete.isEmpty {
                Text("Are you sure you want to delete \(chainsToDelete.count) chains? This action cannot be undone.")
            }
        }
    }

    private var selectedChain: Binding<WorkflowChain?> {
        Binding(
            get: {
                guard let id = selectedChainId else { return nil }
                return chainStore.chains.first { $0.id == id }
            },
            set: { newChain in
                selectedChainId = newChain?.id
            }
        )
    }

    private var filteredChains: [WorkflowChain] {
        if searchText.isEmpty {
            return chainStore.chains
        }
        return chainStore.chains.filter { chain in
            chain.name.localizedCaseInsensitiveContains(searchText) ||
                chain.description.localizedCaseInsensitiveContains(searchText)
        }
    }

    // MARK: - Actions

    private func createChain(name: String, description: String, steps: [ChainStep]) async {
        do {
            _ = try await chainStore.createChain(
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
            try await chainStore.deleteChain(chain.id)
            if selectedChainId == chain.id {
                selectedChainId = nil
            }
            logger.info("Deleted chain: \(chain.name)")
        } catch {
            logger.error("Failed to delete chain: \(error.localizedDescription)")
        }
    }

    private func deleteChains(_ chains: [WorkflowChain]) async {
        do {
            for chain in chains {
                try await chainStore.deleteChain(chain.id)
            }
            let deletedIds = Set(chains.map(\.id))
            selectedChainIds.subtract(deletedIds)
            selectedChainId = selectedChainIds.first
            chainsToDelete = []
            logger.info("Deleted \(chains.count, privacy: .public) chain(s)")
        } catch {
            logger.error("Failed to delete chains: \(error.localizedDescription)")
        }
    }

    private func confirmDelete(_ chain: WorkflowChain) {
        confirmDelete([chain])
    }

    private func confirmDelete(_ chains: [WorkflowChain]) {
        chainsToDelete = chains
        showDeleteConfirmation = !chains.isEmpty
    }

    private func confirmDeleteSelection() {
        let selectedChains = chainStore.chains.filter { selectedChainIds.contains($0.id) }
        guard !selectedChains.isEmpty else { return }
        confirmDelete(selectedChains)
    }

    private func executeChain(_ chain: WorkflowChain) {
        executingChainId = chain.id
        Task {
            do {
                let response = try await chainStore.executeChain(chainId: chain.id)
                logger.info("Started chain execution: \(response.executionId)")

                let result = try await chainStore.waitForExecution(response.executionId) { status in
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
    WorkflowChainListView()
}
