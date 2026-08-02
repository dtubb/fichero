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

/// Hash of ONLY the fields of one document that shape the sidebar tree.
///
/// Deliberately excludes processing status and content, so a status poll that
/// mutates `currentDocuments` (or a status override on `collections`) does NOT
/// force a whole-tree rebuild — the sidebar never renders status
/// (`SidebarItem.fromDocument` sets `showProgress: false`).
///
/// Top-level rather than a member of `SidebarView`: statics on a `View` inherit
/// `@MainActor` under the macOS 26 SDK, which makes them unusable from a plain
/// test.
func sidebarTreeRowHash(_ doc: Document) -> Int {
    var hasher = Hasher()
    hasher.combine(doc.id)
    hasher.combine(doc.parentId)
    hasher.combine(doc.name)
    hasher.combine(doc.sortOrder)
    hasher.combine(doc.sequence)
    hasher.combine(doc.docType)
    hasher.combine(doc.fileType)
    // Structure drives PDF outline rows; ids catch a re-parse that keeps the
    // same count.
    hasher.combine(doc.structure.count)
    for node in doc.structure { hasher.combine(node.id) }
    return hasher.finalize()
}

/// Every row in the cached sidebar forest, keyed by `SidebarItem.id`.
///
/// Resolving one used to be `findItemById`, a recursive walk of the WHOLE
/// forest, and a single sidebar click performed at least four of them: one to
/// route the selection
/// (`handleSelectionDestination`), one for `hasSelection` on the bottom toolbar,
/// one for `selectedItem` in the focused-values config, and one per highlighted
/// row for `selectedItems` — and every one of those recomputes on every body
/// pass of `SidebarView`, because they are computed properties. That is
/// O(rows × selection) of String comparison on the main thread per click, for a
/// question a dictionary answers in O(1).
///
/// **First-in-DFS-preorder wins**, deliberately: that is exactly what the
/// recursive `findItemById` returns, and the forest is NOT guaranteed to have
/// unique ids (a workflow is mirrored into a same-id document node, #4186). A
/// last-wins index would silently reroute those clicks to the other row.
///
/// Top-level rather than a member of `SidebarView`: statics on a `View` inherit
/// `@MainActor` under the macOS 26 SDK, which makes them unusable from a plain
/// test (see `sidebarTreeRowHash` above, and the SIGTRAP in #4201).
func sidebarItemIndex(_ items: [SidebarItem]) -> [String: SidebarItem] {
    var index: [String: SidebarItem] = [:]
    sidebarIndexItems(items, into: &index)
    return index
}

private func sidebarIndexItems(_ items: [SidebarItem], into index: inout [String: SidebarItem]) {
    for item in items {
        if index[item.id] == nil {
            index[item.id] = item
        }
        if let children = item.children {
            sidebarIndexItems(children, into: &index)
        }
    }
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

    /// Resolve one cached row by id — a dictionary hit against the index built
    /// alongside the headers, NOT a walk of the forest. Every selection-path
    /// lookup goes through here; `findItemById` stays for callers that search a
    /// caller-supplied subtree (drop handlers, ancestor tests) rather than the
    /// cache.
    func cachedItem(id: String) -> SidebarItem? {
        cachedItemIndex[id]
    }

    /// Derive the selected SidebarItem from the ID
    var selectedItem: SidebarItem? {
        guard let id = selectedItemId else { return nil }
        return cachedItem(id: id)
    }

    /// Every highlighted row resolved to its SidebarItem — the multi-selection
    /// set that batch actions (delete, open-in-tabs) operate over.
    var selectedItems: [SidebarItem] {
        selectionState.selectedDestinations.compactMap {
            cachedItem(id: $0.serializedID)
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
        cachedItemIndex = sidebarItemIndex(cachedLibraryHeaders)

        // Drop derived state for libraries that are no longer open. Without
        // this, closing a library leaves its buckets and — since the index
        // answers every selection lookup — its ROWS resolvable, so a stale id
        // could route the content pane at a library that is gone.
        let openIds = Set(libraryManager.openLibraries.map(\.id))
        cachedLibraryItemBuckets = cachedLibraryItemBuckets.filter { openIds.contains($0.key) }
        sidebarTreeSignatures = sidebarTreeSignatures.filter { openIds.contains($0.key) }
    }

    /// Rebuild one library header in place, preserving every other library snapshot.
    func rebuildCaches(for libraryId: UUID) {
        guard let library = libraryManager.getLibrary(id: libraryId) else { return }
        let header = buildLibraryHeader(for: library)
        cacheLibraryDerivedState(header: header, library: library)
        cachedLibraryHeaders = sidebarReplacingLibraryHeader(cachedLibraryHeaders, with: header)
        // Reindexing the whole forest costs one pass over rows this call has
        // just rebuilt anyway; a per-library index would have to be merged on
        // every lookup, which is the cost we are removing.
        cachedItemIndex = sidebarItemIndex(cachedLibraryHeaders)
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
    /// iteration order is unstable, so the signature must not depend on order.
    /// It used to `.sorted(by: id)` first — an extra full-array copy and an
    /// O(N log N) sort on EVERY document-store mutation, including the status
    /// polls whose whole purpose here is to be cheaply rejected (#4228).
    /// XOR-combining per-row hashes is order-independent by construction and
    /// costs one pass. Rows cannot cancel each other out: `id` is unique and is
    /// part of every row hash.
    func sidebarTreeSignature(for library: LibraryManager.LibraryReference) -> Int {
        var accumulated = 0
        for doc in library.documentStore.sidebarDocuments {
            accumulated ^= sidebarTreeRowHash(doc)
        }
        return accumulated
    }

    /// `findItemById` used to live here. Every caller looked up the CACHED
    /// forest by id, which `cachedItem(id:)` now answers in O(1) — leaving the
    /// walk behind would invite the next caller to reach right back. Subtree
    /// searches over a caller-supplied node still use the top-level
    /// `findSidebarItemById` in SidebarItemRow+Helpers.

    func filteredSidebarItem(_ item: SidebarItem, query: String) -> SidebarItem? {
        Self.filteredSidebarItem(item, query: query, exempt: filterExemptIDs)
    }

    /// Rows the filter must never remove: everything currently selected (#4099).
    ///
    /// Recomputed from live selection on every access rather than accumulated,
    /// so exemptions cannot outlive the selection that earned them — the
    /// failure mode NetNewsWire's `resetFilterExceptions()` exists to prevent.
    /// Both the single `selectedItemId` and the multi-selection set count: a
    /// batch selection that half-vanishes is the same defect, only wider.
    var filterExemptIDs: Set<String> {
        var ids = Set(selectionState.selectedDestinations.map(\.serializedID))
        if let selectedItemId { ids.insert(selectedItemId) }
        return ids
    }

    /// Filter one item's subtree, keeping anything that matches the query, is
    /// EXEMPT, or has a surviving descendant.
    ///
    /// Static and exempt-injected so the rule is testable without standing up a
    /// SidebarView — the bug is in the predicate, and a test that needs a live
    /// view to reach it would not have been written.
    ///
    /// #4099: a filter that hides the selected row leaves the detail pane
    /// showing a document with no row in the sidebar — the UI asserting two
    /// contradictory things at once, and no way back to the item except
    /// clearing the filter.
    ///
    /// Ancestors need no special case: the existing "keep a parent whose
    /// children survived" rule already carries an exempt descendant's whole
    /// chain up to the root, so the child stays REACHABLE, not just present.
    /// Handling ancestors separately would be a second rule to keep in
    /// agreement with this one.
    static func filteredSidebarItem(
        _ item: SidebarItem,
        query: String,
        exempt: Set<String>
    ) -> SidebarItem? {
        // A match (or an exemption) returns the item UNCHANGED, subtree intact
        // — deliberately the pre-existing behaviour. Filtering a matched
        // folder's children too would be a second change riding along: search
        // "1893", match the folder, and then show it empty because none of its
        // children are called "1893".
        if item.name.localizedCaseInsensitiveContains(query) || exempt.contains(item.id) {
            return item
        }
        let children = item.children?.compactMap {
            filteredSidebarItem($0, query: query, exempt: exempt)
        }
        guard let children, !children.isEmpty else { return nil }
        var copy = item
        copy.children = children
        return copy
    }
}
