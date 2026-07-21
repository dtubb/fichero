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

    /// Every highlighted row resolved to its SidebarItem — the multi-selection
    /// set that batch actions (delete, open-in-tabs) operate over.
    var selectedItems: [SidebarItem] {
        selectionState.selectedDestinations.compactMap {
            findItemById($0.serializedID, in: allCachedItems)
        }
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
        cachedLibraryHeaders = libraryManager.openLibraries.map { library in
            let header = buildLibraryHeader(for: library)
            cacheLibraryDerivedState(header: header, library: library)
            return header
        }
    }

    /// Rebuild one library header in place, preserving every other library snapshot.
    func rebuildCaches(for libraryId: UUID) {
        guard let library = libraryManager.getLibrary(id: libraryId) else { return }
        let header = buildLibraryHeader(for: library)
        cacheLibraryDerivedState(header: header, library: library)
        cachedLibraryHeaders = sidebarReplacingLibraryHeader(cachedLibraryHeaders, with: header)
    }

    /// Recompute and store the per-library derived state that used to be redone
    /// on every body eval / poll (#3862): the filtered item buckets (so the body
    /// stops re-filtering `header.children`) and the tree signature (so the
    /// documentStore observer can skip a no-op rebuild).
    private func cacheLibraryDerivedState(header: SidebarItem, library: LibraryManager.LibraryReference) {
        cachedLibraryItemBuckets[library.id] = Self.computeLibraryItemBuckets(from: header)
        sidebarTreeSignatures[library.id] = sidebarTreeSignature(for: library)
    }

    /// Hash of ONLY the fields that shape the sidebar document tree (#3862).
    /// Deliberately excludes per-doc processing status/content, so a status poll
    /// that mutates `currentDocuments` (or a status override on `collections`)
    /// does NOT force a whole-tree rebuild — the sidebar never renders status
    /// (`SidebarItem.fromDocument` sets `showProgress: false`).
    ///
    /// `sidebarDocuments` is `collections + childrenCache.values` and dictionary
    /// iteration order is unstable, so sort by id for a deterministic signature.
    func sidebarTreeSignature(for library: LibraryManager.LibraryReference) -> Int {
        var hasher = Hasher()
        for doc in library.documentStore.sidebarDocuments.sorted(by: { $0.id < $1.id }) {
            hasher.combine(doc.id)
            hasher.combine(doc.parentId)
            hasher.combine(doc.name)
            hasher.combine(doc.sortOrder)
            hasher.combine(doc.sequence)
            hasher.combine(doc.docType)
            hasher.combine(doc.fileType)
            // Structure drives PDF outline rows; ids catch a re-parse that keeps
            // the same count.
            hasher.combine(doc.structure.count)
            for node in doc.structure { hasher.combine(node.id) }
        }
        return hasher.finalize()
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
