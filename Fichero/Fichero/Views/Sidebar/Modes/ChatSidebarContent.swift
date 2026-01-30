import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ChatSidebarContent")

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
            if let newId = newId, newId.hasPrefix("comparison-") {
                let comparisonId = String(newId.dropFirst("comparison-".count))
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
                let comparisonIds = Set(comparisons.map { "comparison-\($0.id)" })
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

            // Library section - flat structure for proper List selection
            Section {
                // Render chats directly (no DisclosureGroup nesting)
                renderChatItems(chats)

                // Render comparisons directly
                renderComparisonItems()

                // Empty state
                if chats.isEmpty && comparisons.isEmpty && !isLoadingComparisons {
                    Text("No conversations or comparisons yet")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                        .padding(.vertical, 8)
                }
            } header: {
                LibrarySectionHeader(
                    library: library,
                    itemCount: chats.count + comparisons.count,
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
    private func renderChatItems(_ items: [SidebarItem]) -> some View {
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
    private func renderComparisonItems() -> some View {
        ForEach(comparisons) { comparison in
            ComparisonSidebarRow(
                comparison: comparison,
                onViewDetails: { selected in
                    // Select this comparison - detail view will show based on selection
                    selectedItemId = "comparison-\(selected.id)"
                },
                onRerun: { toRerun in
                    // TODO: Navigate to model comparison view with prompt pre-filled
                    logger.info("Re-run comparison: \(toRerun.prompt)")
                }
            )
            .tag("comparison-\(comparison.id)")
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
struct ComparisonSidebarRow: View {
    let comparison: ComparisonSummary
    var onViewDetails: ((ComparisonSummary) -> Void)?
    var onRerun: ((ComparisonSummary) -> Void)?
    var onDelete: ((ComparisonSummary) -> Void)?

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.left.arrow.right")
                .foregroundStyle(.purple)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(truncatedPrompt)
                    .lineLimit(1)

                HStack(spacing: 4) {
                    Text("\(comparison.modelsCompared.count) models")
                        .font(.caption2)
                        .foregroundStyle(.secondary)

                    if comparison.totalCostUsd > 0 {
                        Text("• $\(String(format: "%.4f", comparison.totalCostUsd))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .contextMenu {
            Button {
                onViewDetails?(comparison)
            } label: {
                Label("View Details", systemImage: "info.circle")
            }

            Button {
                onRerun?(comparison)
            } label: {
                Label("Re-run", systemImage: "arrow.clockwise")
            }

            // Note: Delete is disabled - no backend endpoint exists yet
            // Uncomment when DELETE /api/model-comparison/{id} is implemented
            // Divider()
            // Button(role: .destructive) {
            //     onDelete?(comparison)
            // } label: {
            //     Label("Delete", systemImage: "trash")
            // }
        }
    }

    private var truncatedPrompt: String {
        let prompt = comparison.prompt
        if prompt.count > 40 {
            return String(prompt.prefix(40)) + "..."
        }
        return prompt
    }
}

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
