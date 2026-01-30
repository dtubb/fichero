import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "BatchesSidebarContent")

/// Sidebar content for Batches mode - shows batch jobs grouped by library
/// Now uses SidebarItemRow for consistent CRUD behavior
struct BatchesSidebarContent: View {
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var windowState: WindowState
    @ObservedObject var libraryManager: LibraryManager

    // Selection binding from parent (following Library pattern)
    @Binding var selectedItemId: String?
    @Binding var viewMode: AppViewMode

    // SidebarState for expansion persistence
    @ObservedObject var sidebarState: SidebarState

    // Rename and delete state
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager

    // Data from parent (SidebarView manages loading via Combine pattern)
    let batches: [BatchInfo]
    let isLoading: Bool
    var onRefresh: (() -> Void)?

    var body: some View {
        List(selection: $selectedItemId) {
            if isLoading && batches.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
                    .listRowSeparator(.hidden)
            } else {
                // Always show all open libraries (Global first, then others)
                ForEach(libraryManager.openLibraries, id: \.id) { library in
                    let libraryBatches = batchesForLibrary(library)
                    Section {
                        // Build SidebarItems for consistent rendering
                        let batchItems = libraryBatches.map { batch in
                            SidebarItem.fromBatch(batch, libraryId: library.id)
                        }

                        ForEach(batchItems) { item in
                            SidebarItemRow(
                                item: item,
                                allCachedItems: batchItems,
                                expandedItems: Binding(
                                    get: { sidebarState.expandedItems },
                                    set: { sidebarState.expandedItems = $0 }
                                ),
                                selectedItemId: $selectedItemId,
                                renameState: renameState,
                                deleteState: deleteState,
                                libraryManager: libraryManager,
                                onAutomationPause: batchActionCallback(item, .pause),
                                onAutomationResume: nil,  // Batches don't have resume
                                onAutomationTrigger: nil,
                                onAutomationCancel: batchActionCallback(item, .cancel)
                            )
                            .tag(item.id)
                        }
                    } header: {
                        LibrarySectionHeader(
                            library: library,
                            itemCount: libraryBatches.count,
                            isCurrentLibrary: library.id == windowState.libraryId
                        )
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)  // Transparent background for sidebar
        .onChange(of: selectedItemId) { _, newId in
            handleSelection(newId)
        }
    }

    // MARK: - Computed Properties

    private func batchesForLibrary(_ library: LibraryManager.LibraryReference) -> [BatchInfo] {
        // TODO: Filter batches by library when library scoping is implemented
        // For now, show all batches under Global
        if library.id == LibraryManager.globalLibraryId {
            return batches
        }
        return []
    }

    // MARK: - Selection Handling

    private func handleSelection(_ id: String?) {
        guard let id = id, id.hasPrefix("batch:") else { return }
        let batchId = String(id.dropFirst("batch:".count))
        if let batch = batches.first(where: { $0.batchId == batchId }) {
            viewMode = .batch(batch)
        }
    }

    // MARK: - Action Callbacks

    /// Create a callback for batch actions (pause/cancel)
    /// Returns nil if the item is not a batch
    private func batchActionCallback(_ item: SidebarItem, _ action: BatchAction) -> (() -> Void)? {
        guard case .batch(let batch) = item.itemType else { return nil }

        return {
            Task {
                do {
                    guard let library = libraryManager.openLibraries.first else {
                        logger.error("No library available for batch action")
                        return
                    }
                    switch action {
                    case .pause:
                        _ = try await library.batchService.pauseBatchAsInfo(batchId: batch.batchId)
                    case .cancel:
                        _ = try await library.batchService.cancelBatchAsInfo(batchId: batch.batchId)
                    case .delete:
                        // Delete is handled by SidebarItemRow's performDelete
                        break
                    }
                    // Trigger parent to reload batch data
                    await MainActor.run {
                        onRefresh?()
                    }
                } catch {
                    logger.error("Failed to perform batch action: \(error.localizedDescription)")
                }
            }
        }
    }
}

#Preview {
    BatchesSidebarContent(
        libraryManager: .shared,
        selectedItemId: .constant(nil),
        viewMode: .constant(.batches),
        sidebarState: SidebarState(),
        renameState: RenameStateManager(),
        deleteState: DeleteStateManager(),
        batches: [],
        isLoading: false,
        onRefresh: nil
    )
    .environmentObject(APIClient())
    .environmentObject(WindowState(libraryId: LibraryManager.globalLibraryId))
    .frame(width: 280, height: 500)
}
