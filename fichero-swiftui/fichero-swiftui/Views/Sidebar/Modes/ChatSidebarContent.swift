import SwiftUI
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ChatSidebarContent")

/// Sidebar content for Chat mode - shows conversations and comparisons grouped by library
struct ChatSidebarContent: View {
    @Binding var selectedItemId: String?
    @Binding var viewMode: AppViewMode
    @Binding var sidebarMode: SidebarMode  // To detect when returning to chat mode
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

    // Comparisons state
    @EnvironmentObject var apiClient: APIClient
    @State private var comparisons: [ComparisonSummary] = []
    @State private var isLoadingComparisons = false

    /// All cached items combined (for recursive searches)
    private var allCachedItems: [SidebarItem] {
        cachedLibraryHeaders
    }

    var body: some View {
        List(selection: $selectedItemId) {
            // Show libraries with chats and comparisons
            ForEach(cachedLibraryHeaders) { libraryHeader in
                librarySection(libraryHeader)
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)  // Transparent background for sidebar
        .onChange(of: selectedItemId) { _, newId in
            // When a comparison is selected, update viewMode
            if let newId = newId, newId.hasPrefix("comparison:") {
                let comparisonId = String(newId.dropFirst("comparison:".count))
                if let comparison = comparisons.first(where: { $0.id == comparisonId }) {
                    viewMode = .comparison(comparison)
                }
            }
        }
        .onChange(of: cachedLibraryHeaders) { _, _ in
            // Clear selection if the selected item no longer exists
            if let selectedId = selectedItemId {
                let allChats = cachedLibraryHeaders.flatMap { $0.children ?? [] }
                    .filter { item in
                        if case .conversation = item.itemType { return true }
                        return false
                    }
                let chatIds = Set(allChats.map { $0.id })
                let comparisonIds = Set(comparisons.map { "comparison:\($0.id)" })
                let validIds = chatIds.union(comparisonIds)

                if !validIds.contains(selectedId) {
                    selectedItemId = nil
                }
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadComparisons()
        }
        .onChange(of: sidebarMode) { _, newMode in
            // Reload comparisons whenever we switch TO chat mode
            // (comparison may have been created/run in comparison view)
            if case .chat = newMode {
                Task {
                    await loadComparisons()
                }
            }
        }
    }

    // MARK: - Library Section

    @ViewBuilder
    private func librarySection(_ libraryHeader: SidebarItem) -> some View {
        if let libraryId = libraryHeader.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            let chats = chatItems(from: libraryHeader.children ?? [])
            // Convert comparisons to SidebarItems
            let comparisonItems = comparisons.map { SidebarItem.fromComparison($0, libraryId: libraryId) }

            // Combine chats and comparisons into a single array
            let allItems = chats + comparisonItems

            // Library section - flat structure for proper List selection
            Section {
                renderItems(allItems)

                // Empty state
                if allItems.isEmpty && !isLoadingComparisons {
                    Text("No conversations or comparisons yet")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                        .padding(.vertical, 8)
                }
            } header: {
                LibrarySectionHeader(
                    library: library,
                    itemCount: allItems.count,
                    isCurrentLibrary: library.id == windowState.libraryId
                )
            }
        }
    }

    /// Extract chat items from a collection
    private func chatItems(from items: [SidebarItem]) -> [SidebarItem] {
        items.filter { item in
            if case .conversation = item.itemType { return true }
            return false
        }
    }

    @ViewBuilder
    private func renderItems(_ items: [SidebarItem]) -> some View {
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

    // MARK: - Data Loading

    private func loadComparisons() async {
        isLoadingComparisons = true
        defer { isLoadingComparisons = false }

        // Check cancellation before async work
        guard !Task.isCancelled else { return }

        do {
            // Load comparison history from API using APIClient
            let response: ComparisonHistoryResponse = try await apiClient.get(
                "/model-comparison/history?limit=20"
            )

            // Check cancellation after async call
            guard !Task.isCancelled else { return }

            comparisons = response.history
            logger.info("Loaded \(comparisons.count) comparisons")
        } catch {
            // Only log if not cancelled
            guard !Task.isCancelled else { return }
            logger.error("Failed to load comparisons: \(error.localizedDescription)")
        }
    }
}

// MARK: - Comparison Types (local for sidebar display)

/// Summary of a comparison for sidebar display
struct ComparisonSummary: Codable, Identifiable, Equatable, Hashable {
    var id: String { comparisonId }
    let prompt: String
    let modelsCompared: [String]
    let totalCostUsd: Double
    let comparisonId: String
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case prompt
        case modelsCompared = "models_compared"
        case totalCostUsd = "total_cost_usd"
        case comparisonId = "comparison_id"
        case timestamp
    }
}

struct ComparisonHistoryResponse: Codable {
    let history: [ComparisonSummary]
}

// MARK: - Comparison Sidebar Row

/// Row displaying a comparison in the sidebar

#Preview {
    ChatSidebarContent(
        selectedItemId: .constant(nil),
        viewMode: .constant(.chat(nil)),
        sidebarMode: .constant(.chat),
        libraryManager: .shared,
        sidebarState: SidebarState(),
        renameState: RenameStateManager(),
        deleteState: DeleteStateManager(),
        cachedLibraryHeaders: []
    )
    .environmentObject(APIClient())
    .environmentObject(WindowState(libraryId: LibraryManager.globalLibraryId))
    .frame(width: 280, height: 500)
}
