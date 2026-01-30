import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowsSidebarContent")

/// Sidebar content for Workflows mode - shows workflow definitions and chains grouped by library
struct WorkflowsSidebarContent: View {
    @Binding var selectedItemId: String?
    @Binding var viewMode: AppViewMode
    @ObservedObject var libraryManager: LibraryManager

    // Window state for current library indicator
    @EnvironmentObject var windowState: WindowState

    // SidebarState for expansion persistence
    @ObservedObject var sidebarState: SidebarState

    // Rename and delete state
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager

    // Cached sidebar items
    let cachedLibraryHeaders: [SidebarItem]

    // Chains from parent (SidebarView manages via Combine)
    let chains: [WorkflowChain]

    // Chain service for operations (delete, rename, execute)
    @ObservedObject var chainService: ChainService

    // Chain delete confirmation state
    @State private var chainToDelete: WorkflowChain?
    @State private var showingChainDeleteConfirmation = false

    // Chain rename state
    @State private var chainToRename: WorkflowChain?
    @State private var chainRenameText: String = ""
    @State private var showingChainRenameAlert = false

    /// All cached items combined (for recursive searches)
    private var allCachedItems: [SidebarItem] {
        cachedLibraryHeaders
    }

    var body: some View {
        List(selection: $selectedItemId) {
            // Show libraries with workflows and chains
            ForEach(cachedLibraryHeaders) { libraryHeader in
                librarySection(libraryHeader)
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .onChange(of: selectedItemId) { handleSelectionChange($1) }
        .onChange(of: viewMode) { handleViewModeChange($1) }
        .onChange(of: cachedLibraryHeaders) { _, _ in clearInvalidSelection() }
        .alert("Delete Chain", isPresented: $showingChainDeleteConfirmation) {
            Button("Cancel", role: .cancel) {
                chainToDelete = nil
            }
            Button("Delete", role: .destructive) {
                if let chain = chainToDelete {
                    Task {
                        await deleteChain(chain)
                    }
                }
            }
        } message: {
            if let chain = chainToDelete {
                Text("Are you sure you want to delete \"\(chain.name)\"? This action cannot be undone.")
            }
        }
        .alert("Rename Chain", isPresented: $showingChainRenameAlert) {
            TextField("Name", text: $chainRenameText)
            Button("Cancel", role: .cancel) {
                chainToRename = nil
                chainRenameText = ""
            }
            Button("Rename") {
                if let chain = chainToRename {
                    Task {
                        await renameChain(chain, to: chainRenameText)
                    }
                }
            }
        } message: {
            Text("Enter a new name for the chain.")
        }
    }

    // MARK: - Selection Handling

    private func handleSelectionChange(_ newId: String?) {
        // When a chain is selected, update viewMode
        guard let newId = newId, newId.hasPrefix("chain-") else { return }
        let chainId = String(newId.dropFirst("chain-".count))
        if let chain = chains.first(where: { $0.id == chainId }) {
            viewMode = .chain(chain)
        }
    }

    private func handleViewModeChange(_ newMode: AppViewMode) {
        // Sync viewMode -> selection
        if case .chain(let chain?) = newMode {
            selectedItemId = "chain-\(chain.id)"
        }
    }

    private func clearInvalidSelection() {
        // Clear selection if the selected item no longer exists
        guard let selectedId = selectedItemId else { return }

        let allWorkflows = cachedLibraryHeaders.flatMap { $0.children ?? [] }
            .filter { item in
                if case .workflow = item.itemType { return true }
                return false
            }
        let workflowIds = Set(allWorkflows.map { $0.id })
        let chainIds = Set(chains.map { "chain-\($0.id)" })
        let validIds = workflowIds.union(chainIds)

        if !validIds.contains(selectedId) {
            selectedItemId = nil
        }
    }

    // MARK: - Library Section

    @ViewBuilder
    private func librarySection(_ libraryHeader: SidebarItem) -> some View {
        if let libraryId = libraryHeader.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            let workflows = workflowItems(from: libraryHeader.children ?? [])
            // Filter chains by library (TODO: Backend should support library filtering)
            let libraryChains = chains // For now show all chains under global library only
            let showChains = libraryId == LibraryManager.globalLibraryId

            // Library section - flat structure for proper List selection
            Section {
                // Render workflows directly (no DisclosureGroup nesting)
                renderWorkflowItems(workflows)

                // Render chains directly (only in global library for now)
                if showChains {
                    renderChainItems()
                }

                // Empty state
                let chainCount = showChains ? libraryChains.count : 0
                if workflows.isEmpty && chainCount == 0 {
                    Text("No workflows or chains yet")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                        .padding(.vertical, 8)
                }
            } header: {
                let chainCount = showChains ? libraryChains.count : 0
                LibrarySectionHeader(
                    library: library,
                    itemCount: workflows.count + chainCount,
                    isCurrentLibrary: library.id == windowState.libraryId
                )
            }
        }
    }

    /// Extract workflow items from a collection
    private func workflowItems(from items: [SidebarItem]) -> [SidebarItem] {
        items.filter { item in
            if case .workflow = item.itemType { return true }
            return false
        }
    }

    @ViewBuilder
    private func renderWorkflowItems(_ items: [SidebarItem]) -> some View {
        ForEach(items) { item in
            SidebarItemRow(
                item: item,
                allCachedItems: allCachedItems,
                expandedItems: Binding(
                    get: { sidebarState.expandedItems },
                    set: { sidebarState.expandedItems = $0 }
                ),
                selectedItemId: $selectedItemId,
                renameState: renameState,
                deleteState: deleteState,
                libraryManager: libraryManager
            )
            .tag(item.id)
        }
    }

    @ViewBuilder
    private func renderChainItems() -> some View {
        ForEach(chains) { chain in
            ChainSidebarRow(
                chain: chain,
                onRename: { chainToRename in
                    self.chainToRename = chainToRename
                    chainRenameText = chainToRename.name
                    showingChainRenameAlert = true
                },
                onExecute: { chainToExecute in
                    Task {
                        await executeChain(chainToExecute)
                    }
                },
                onDelete: { chainToDelete in
                    self.chainToDelete = chainToDelete
                    showingChainDeleteConfirmation = true
                }
            )
            .tag("chain-\(chain.id)")
        }
    }

    // MARK: - Chain Operations (using chainService from parent)

    private func deleteChain(_ chain: WorkflowChain) async {
        do {
            try await chainService.deleteChain(chain.id)
            chainToDelete = nil
            logger.info("Deleted chain: \(chain.name)")
        } catch {
            logger.error("Failed to delete chain: \(error.localizedDescription)")
        }
    }

    private func renameChain(_ chain: WorkflowChain, to newName: String) async {
        let trimmedName = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else {
            chainToRename = nil
            chainRenameText = ""
            return
        }

        do {
            var updatedChain = chain
            updatedChain.name = trimmedName
            _ = try await chainService.updateChain(updatedChain)
            // ChainService automatically updates $chains via loadChains()
            chainToRename = nil
            chainRenameText = ""
            logger.info("Renamed chain to: \(trimmedName)")
        } catch {
            logger.error("Failed to rename chain: \(error.localizedDescription)")
        }
    }

    private func executeChain(_ chain: WorkflowChain) async {
        do {
            let response = try await chainService.executeChain(chainId: chain.id)
            logger.info("Started chain execution: \(response.executionId)")
            // TODO: Navigate to activity view to show execution progress
        } catch {
            logger.error("Failed to execute chain: \(error.localizedDescription)")
        }
    }
}

// MARK: - Chain Sidebar Row

/// Row displaying a chain in the sidebar
struct ChainSidebarRow: View {
    let chain: WorkflowChain
    var onRename: ((WorkflowChain) -> Void)?
    var onExecute: ((WorkflowChain) -> Void)?
    var onDelete: ((WorkflowChain) -> Void)?

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "link")
                .foregroundStyle(.blue)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(chain.name)
                    .lineLimit(1)

                Text("\(chain.steps.count) step\(chain.steps.count == 1 ? "" : "s")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .contextMenu {
            Button {
                onRename?(chain)
            } label: {
                Label("Rename", systemImage: "pencil")
            }

            Button {
                onExecute?(chain)
            } label: {
                Label("Execute", systemImage: "play.fill")
            }

            Divider()

            Button(role: .destructive) {
                onDelete?(chain)
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }
}

#Preview {
    @Previewable @StateObject var chainService = ChainService(apiClient: APIClient())

    WorkflowsSidebarContent(
        selectedItemId: .constant(nil),
        viewMode: .constant(.workflow(nil)),
        libraryManager: .shared,
        sidebarState: SidebarState(),
        renameState: RenameStateManager(),
        deleteState: DeleteStateManager(),
        cachedLibraryHeaders: [],
        chains: [],
        chainService: chainService
    )
    .environmentObject(WindowState(libraryId: LibraryManager.globalLibraryId))
    .frame(width: 280, height: 500)
}
