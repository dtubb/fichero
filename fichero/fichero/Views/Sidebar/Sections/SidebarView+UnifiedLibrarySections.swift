import SwiftUI

// MARK: - Unified Library Sections

extension SidebarView {
    struct UnifiedLibraryBuckets {
        let documentItems: [SidebarItem]
        let searchItems: [SidebarItem]
        let workflowItems: [SidebarItem]
        let comparisonItems: [SidebarItem]
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
        let comparisonItems: [SidebarItem]
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
        // #4335: comparison history rows are nodes in the tree too. Without a
        // bucket of their own the filter above silently dropped them — the
        // "loaded but never rendered" half of the missing-bucket defect.
        let comparisonItems = allChildren.filter { item in
            if case .comparison = item.itemType { return true }
            return false
        }
        return CachedLibraryItemBuckets(
            documentItems: documentItems,
            searchItems: searchItems,
            workflowItems: workflowItems,
            comparisonItems: comparisonItems
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

            // EVERY library — including the global one — gets its own header
            // row (#4102). The global library used to render headless, from
            // when it was the only library and the row was dead chrome (#608).
            // With several libraries open that made its contents look like
            // they belonged to no library, and floated its "Default Workflows"
            // subfolders at the sidebar's top level next to the real library
            // rows. One consistent shape: a library is always a disclosure
            // group you can collapse.
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
        let comparisonItems = itemBuckets.comparisonItems
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
            comparisonItems: comparisonItems,
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

        // #4335: comparison history rows follow the same one-list rule —
        // every node type in one continuous list, kind conveyed by icon.
        if FeatureManager.shared.isVisible(.modelComparison) {
            items.append(contentsOf: buckets.comparisonItems)
        }

        // Default Workflows is a global-only destination, same as chains/
        // schedules/ triggers above: the "Default Workflows" folder ships in
        // every library's DB (each library is self-contained) but the sidebar
        // only surfaces it under the Global library so it isn't duplicated
        // across every individual library (#4060).
        //
        // Since #4186 this bucket is EMPTY: SidebarItemBuilder no longer
        // builds the client-side virtual workflow hierarchy — workflows
        // reach the tree as engine-mirrored document nodes instead. The
        // append stays as the one-line reversal point.
        if FeatureManager.shared.isWorkflowsEnabled && libraryId == LibraryManager.globalLibraryId {
            items.append(contentsOf: buckets.workflowItems)
        }

        return items
    }
}
