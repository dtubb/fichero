import SwiftUI
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "LibrarySidebarContent")

/// Sidebar content for Library mode - shows documents and folders grouped by library
/// This extracts the existing library browsing behavior from SidebarView
struct LibrarySidebarContent: View {
    @Binding var selectedItemId: String?
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

    /// All cached items combined (for recursive searches)
    private var allCachedItems: [SidebarItem] {
        cachedLibraryHeaders
    }

    var body: some View {
        List(selection: $selectedItemId) {
            // Always show all libraries (Global first, then others)
            ForEach(cachedLibraryHeaders) { libraryHeader in
                librarySection(libraryHeader)
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)  // Transparent background for sidebar
    }

    // MARK: - Library Section

    @ViewBuilder
    private func librarySection(_ libraryHeader: SidebarItem) -> some View {
        if let libraryId = libraryHeader.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            let documents = documentItems(from: libraryHeader.children ?? [])

            Section {
                renderDocumentItems(documents)
            } header: {
                LibrarySectionHeader(
                    library: library,
                    itemCount: documents.count,
                    isCurrentLibrary: library.id == windowState.libraryId
                )
            }
        }
    }

    /// Extract document/folder items from a collection
    private func documentItems(from items: [SidebarItem]) -> [SidebarItem] {
        items.filter { item in
            if case .document = item.itemType { return true }
            if case .folder = item.itemType { return true }
            return false
        }
    }

    @ViewBuilder
    private func renderDocumentItems(_ items: [SidebarItem]) -> some View {
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
}

#Preview {
    LibrarySidebarContent(
        selectedItemId: .constant(nil),
        libraryManager: .shared,
        sidebarState: SidebarState(),
        renameState: RenameStateManager(),
        deleteState: DeleteStateManager(),
        cachedLibraryHeaders: []
    )
    .environmentObject(WindowState(libraryId: LibraryManager.globalLibraryId))
    .frame(width: 280, height: 500)
}
