import SwiftUI

// MARK: - Unified Library Sections

extension SidebarView {
    struct UnifiedLibraryBuckets {
        let documentItems: [SidebarItem]
        let searchItems: [SidebarItem]
        let workflowItems: [SidebarItem]
        let chainItems: [SidebarItem]
        let scheduleItems: [SidebarItem]
        let triggerItems: [SidebarItem]
        let activityItems: [SidebarItem]
    }

    /// The header-derived buckets that only change when the library header is
    /// rebuilt (#3862). Cached in `rebuildCaches` so the body stops re-filtering
    /// `header.children` on every sidebar state change. The chain/schedule/
    /// trigger buckets are NOT cached here — they're small @State maps that
    /// mutate outside `rebuildCaches`, so they stay computed live.
    struct CachedLibraryItemBuckets {
        let documentItems: [SidebarItem]
        let searchItems: [SidebarItem]
        let workflowItems: [SidebarItem]
    }

    /// Filter a library header's children into the document / search / workflow
    /// buckets. Pure over the header, so it can be memoised per library.
    static func computeLibraryItemBuckets(from libraryHeader: SidebarItem) -> CachedLibraryItemBuckets {
        let allChildren = libraryHeader.children ?? []
        let documentItems = allChildren.filter { item in
            if case .document = item.itemType { return true }
            if case .folder = item.itemType, item.category == .folder { return true }
            return false
        }
        let searchItems = allChildren.filter { item in
            if case .savedSearch = item.itemType { return true }
            if case .folder = item.itemType, item.category == .search { return true }
            return false
        }
        let workflowItems = allChildren.filter { item in
            if case .workflow = item.itemType { return true }
            if case .folder = item.itemType, item.category == .workflow { return true }
            return false
        }
        return CachedLibraryItemBuckets(
            documentItems: documentItems,
            searchItems: searchItems,
            workflowItems: workflowItems
        )
    }

    @ViewBuilder
    func unifiedLibrarySection(_ libraryHeader: SidebarItem) -> some View {
        if let libraryId = libraryHeader.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            let buckets = unifiedLibraryBuckets(for: libraryHeader, library: library, libraryId: libraryId)
            // Match the header's count to the rows actually rendered below. In
            // particular, workflow nodes are intentionally global-only and must
            // not inflate an individual library's disclosure label.
            let totalCount = flattenedLibraryItems(libraryId: libraryId, buckets: buckets).count

            if library.id == LibraryManager.globalLibraryId {
                // Global library is headless — with a single library in
                // 0.0.2 there's nothing to switch between, so the
                // "Global" row was dead chrome (#608). Library-root
                // Finder drops still work via the section headers
                // inside (Library / Saved Searches / etc.).
                unifiedLibrarySections(
                    libraryId: libraryId,
                    buckets: buckets
                )
            } else {
                DisclosureGroup(
                    isExpanded: Binding(
                        get: { sidebarState.isLibraryExpanded(library.id) },
                        set: { sidebarState.libraryExpansionStates[library.id.uuidString] = $0 }
                    )
                ) {
                    unifiedLibrarySections(
                        libraryId: libraryId,
                        buckets: buckets
                    )
                } label: {
                    libraryDisclosureLabel(library: library, totalCount: totalCount)
                }
                .tag(SidebarDestination.library(library.id))
                .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
            }
        }
    }

    @MainActor
    func unifiedLibraryBuckets(
        for libraryHeader: SidebarItem,
        library: LibraryManager.LibraryReference,
        libraryId: UUID
    ) -> UnifiedLibraryBuckets {
        // Reuse the header-derived filtering cached by `rebuildCaches` (#3862);
        // fall back to computing it for a header not yet cached (first render).
        // While a search filter is active the passed header has FILTERED
        // children, so bypass the (unfiltered) cache and compute from it — a
        // rare, user-driven path, unlike the poll/scroll churn the cache targets.
        let query = sidebarFilterText.trimmingCharacters(in: .whitespacesAndNewlines)
        let itemBuckets = query.isEmpty
            ? (cachedLibraryItemBuckets[libraryId] ?? Self.computeLibraryItemBuckets(from: libraryHeader))
            : Self.computeLibraryItemBuckets(from: libraryHeader)
        let documentItems = itemBuckets.documentItems
        let searchItems = itemBuckets.searchItems
        let workflowItems = itemBuckets.workflowItems
        let isGlobalLibrary = libraryId == LibraryManager.globalLibraryId
        let chainItems = (isGlobalLibrary && FeatureManager.shared.isWorkflowChainsEnabled)
            ? chains.map { SidebarItem.fromChain($0, libraryId: libraryId) }
            : []
        let scheduleItems = (isGlobalLibrary && FeatureManager.shared.isAutomationEnabled)
            ? schedules.map { SidebarItem.fromSchedule($0, libraryId: libraryId) }
            : []
        let triggerItems = (isGlobalLibrary && FeatureManager.shared.isAutomationEnabled)
            ? triggers.map { SidebarItem.fromTrigger($0, libraryId: libraryId) }
            : []
        let activityItems: [SidebarItem] = []

        return UnifiedLibraryBuckets(
            documentItems: documentItems,
            searchItems: searchItems,
            workflowItems: workflowItems,
            chainItems: chainItems,
            scheduleItems: scheduleItems,
            triggerItems: triggerItems,
            activityItems: activityItems
        )
    }

    /// ONE unified node list per library (per tab). The old Library / Saved
    /// Searches / Automation section headers (and the divider between them) are
    /// gone: every row is just a node, and its kind — folder, saved search,
    /// schedule, trigger — is conveyed by its own icon. Documents are the
    /// source-of-truth tree; saved searches and automation are node tools over
    /// it, so they follow the document tree in one continuous list.
    ///
    /// A single flattened array backs the library rows. Documents always lead;
    /// schedule / trigger, saved-search, and workflow items append only under
    /// their existing feature gates. Empty arrays render nothing — no empty
    /// headers, no separate move/drop dispatch surface.
    ///
    /// Workflows / Batches / Activity are app-level destinations (fixed tags, no
    /// library scope) and stay pinned once at the bottom — see
    /// `pinnedGlobalNavigationRows()` in `unifiedContent` (#1456).
    @ViewBuilder
    func unifiedLibrarySections(
        libraryId: UUID,
        buckets: UnifiedLibraryBuckets
    ) -> some View {
        let libraryItems = flattenedLibraryItems(libraryId: libraryId, buckets: buckets)
        unifiedRows(libraryItems, libraryId: libraryId)
    }

    private func flattenedLibraryItems(
        libraryId: UUID,
        buckets: UnifiedLibraryBuckets
    ) -> [SidebarItem] {
        var items = buckets.documentItems

        if FeatureManager.shared.isAutomationEnabled {
            items.append(contentsOf: buckets.scheduleItems + buckets.triggerItems)
        }

        if FeatureManager.shared.isSearchEnabled {
            items.append(contentsOf: buckets.searchItems)
        }

        // Default Workflows is a global-only destination, same as chains/
        // schedules/ triggers above: the "Default Workflows" folder ships in
        // every library's DB (each library is self-contained) but the sidebar
        // only surfaces it under the Global library so it isn't duplicated
        // across every individual library (#4060).
        if FeatureManager.shared.isWorkflowsEnabled && libraryId == LibraryManager.globalLibraryId {
            items.append(contentsOf: buckets.workflowItems)
        }

        return items
    }
}
