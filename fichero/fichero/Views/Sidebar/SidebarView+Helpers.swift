import SwiftUI

// MARK: - Helpers

func sidebarReplacingLibraryHeader(_ headers: [SidebarItem], with header: SidebarItem) -> [SidebarItem] {
    guard let index = headers.firstIndex(where: { $0.id == header.id }) else {
        return headers + [header]
    }
    var updated = headers
    updated[index] = header
    return updated
}

extension SidebarView {
    func sidebarLibrarySelectionId(_ libraryId: UUID) -> String {
        "library:\(libraryId.uuidString)"
    }

    func selectedLibraryId(from selectionId: String) -> UUID? {
        guard selectionId.hasPrefix("library:") else { return nil }
        let rawId = String(selectionId.dropFirst("library:".count))
        return UUID(uuidString: rawId)
    }

    /// All cached items combined (for recursive searches)
    var allCachedItems: [SidebarItem] {
        cachedLibraryHeaders
    }

    var filteredLibraryHeaders: [SidebarItem] {
        let query = sidebarFilterText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return cachedLibraryHeaders }
        return cachedLibraryHeaders.compactMap { filteredSidebarItem($0, query: query) }
    }

    /// Derive the selected SidebarItem from the ID
    var selectedItem: SidebarItem? {
        guard let id = selectedItemId else { return nil }
        return findItemById(id, in: allCachedItems)
    }

    /// Get library that owns the selected item
    var selectedItemLibrary: LibraryManager.LibraryReference? {
        guard let item = selectedItem, let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    func buildLibraryHeader(for library: LibraryManager.LibraryReference) -> SidebarItem {
        let libraryContent = SidebarItemBuilder.buildLibraryGroup(library: library)
        return SidebarItem.libraryHeader(library: library, children: libraryContent)
    }

    /// Rebuild all sidebar item caches from ALL libraries
    func rebuildCaches() {
        cachedLibraryHeaders = libraryManager.openLibraries.map { buildLibraryHeader(for: $0) }
    }

    /// Rebuild one library header in place, preserving every other library snapshot.
    func rebuildCaches(for libraryId: UUID) {
        guard let library = libraryManager.getLibrary(id: libraryId) else { return }
        let header = buildLibraryHeader(for: library)
        cachedLibraryHeaders = sidebarReplacingLibraryHeader(cachedLibraryHeaders, with: header)
    }

    /// Recursively find an item by ID
    func findItemById(_ id: String, in items: [SidebarItem]) -> SidebarItem? {
        for item in items {
            if item.id == id {
                return item
            }
            if let children = item.children,
               let found = findItemById(id, in: children) {
                return found
            }
        }
        return nil
    }

    func filteredSidebarItem(_ item: SidebarItem, query: String) -> SidebarItem? {
        if item.name.localizedCaseInsensitiveContains(query) {
            return item
        }
        let children = item.children?.compactMap { filteredSidebarItem($0, query: query) }
        guard let children, !children.isEmpty else { return nil }
        var copy = item
        copy.children = children
        return copy
    }
}
