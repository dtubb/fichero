import SwiftUI

// MARK: - Unified Library Sections

extension SidebarView {
    struct UnifiedLibraryBuckets {
        let documentItems: [SidebarItem]
        let searchItems: [SidebarItem]
        let workflowItems: [SidebarItem]
        let comparisonItems: [SidebarItem]
        let conversationItems: [SidebarItem]
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
        let conversationItems: [SidebarItem]
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
        // Views audit 2026-08-10 (#1 of the top-10): CONVERSATIONS were the
        // other still-live half of the same missing-bucket defect — built by
        // buildChatHierarchy, then filtered out here, so every chat row was
        // loaded and never rendered, and a newly created chat pointed
        // selection at a row that could not exist. Chats are nodes in the
        // one tree, like everything else (Daniel's node doctrine).
        let conversationItems = allChildren.filter { item in
            if case .conversation = item.itemType { return true }
            if case .folder = item.itemType, item.category == .chat { return true }
            return false
        }
        return CachedLibraryItemBuckets(
            documentItems: documentItems,
            searchItems: searchItems,
            workflowItems: workflowItems,
            comparisonItems: comparisonItems,
            conversationItems: conversationItems
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

            // Every project a person set up gets its own header row (#4102):
            // a disclosure group you can collapse, under the Projects heading.
            // The always-there project is drawn headless above them instead
            // (`alwaysThereProjectItems`, ruled 2026-10-10), so its items read
            // as the sidebar's own top section, not as floating rows.
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
                // The header paints the SAME grey platter as every other row
                // (#110, 2026-08-09), on the LABEL, never the DisclosureGroup
                // (#4229: the group's frame is the header plus its expanded
                // subtree). The header's own `sidebarDropHighlight` is the one
                // writer for both drop and selection (#5422).
                libraryDisclosureLabel(library: library, totalCount: totalCount)
            }
            // NO .tag — deliberately OUTSIDE List selection (#160, 2026-08-09:
            // 'sidebar should not have green when global library is selected').
            // The label-level platter cannot suppress the native emphasized
            // fill on a top-level DisclosureGroup row, so the row opts out of
            // native selection entirely: LibraryHeaderRow's own onTap routes
            // the destination (below), and the grey platter on the label is
            // the whole selection treatment. Ceiling: a ⇧-range cannot span a
            // library header — Finder's sidebar headers behave the same.
            .listRowInsets(SidebarRowMetrics.insets(.library))
        }
    }

    /// The always-there project at the sidebar's top (ruled 2026-10-10,
    /// `sidebar.top-section-is-the-always-there-project`): its own items (Sources, Workflows,
    /// Models, and its knowledge rows while they hold something) drawn at the top level with no
    /// heading row, since it has no name. The rows are the same nodes, with the same ids, as when
    /// they sat under its header, so selection and routing are unchanged.
    @ViewBuilder
    func alwaysThereProjectItems(_ libraryHeader: SidebarItem) -> some View {
        if let libraryId = libraryHeader.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            let buckets = unifiedLibraryBuckets(for: libraryHeader, library: library, libraryId: libraryId)
            unifiedLibrarySections(libraryId: libraryId, buckets: buckets)
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
        let conversationItems = itemBuckets.conversationItems
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
            conversationItems: conversationItems,
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
        if let library = libraryManager.getLibrary(id: libraryId) {
            // The project's own nodes after its items, in `SidebarProjectNode.order`; Trash last (#5243).
            ForEach(SidebarProjectNode.order, id: \.self) { node in
                switch node {
                case .knowledge:
                    // Each knowledge row draws only while it holds an item (#5413); the bottom bar's
                    // control hides them all.
                    SidebarKnowledgeRowsNode(store: library.knowledgeRowCountsStore, libraryId: libraryId)
                case .models:
                    // Training is a node of the project (#5439); it draws nothing until a model is trained.
                    SidebarTrainingNode(store: library.trainedModelsStore, libraryId: libraryId)
                case .trash:
                    SidebarTrashRow(store: library.trashStore, libraryId: libraryId)
                }
            }
        }
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

        // Conversations are nodes in the same one list (views audit #1) —
        // the missing bucket made every chat row invisible.
        if FeatureManager.shared.isChatEnabled {
            items.append(contentsOf: buckets.conversationItems)
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

    // MARK: - ⌘A over the sidebar (Daniel, 2026-08-23)

    /// The destinations ⌘A selects in the sidebar: the CURRENT library's
    /// visible rows, in the order they are drawn — **never across libraries**
    /// (Daniel's ruling; several libraries open at once is the normal state,
    /// and a chord that reached all of them would select things the user
    /// cannot see and did not open).
    ///
    /// VISIBLE has two halves and both matter: the library's disclosure group
    /// must be expanded, and the rows are the same `flattenedLibraryItems` the
    /// view renders — so a feature-gated bucket that draws no rows contributes
    /// no destinations either.
    var currentLibraryVisibleDestinations: [SidebarDestination] {
        // The always-there project has no header to collapse: its items are always visible.
        guard let libraryId = libraryManager.currentLibraryId,
              libraryId == LibraryManager.globalLibraryId || sidebarState.isLibraryExpanded(libraryId),
              let library = libraryManager.getLibrary(id: libraryId),
              let header = filteredLibraryHeaders.first(where: { $0.libraryId == libraryId })
        else { return [] }
        let buckets = unifiedLibraryBuckets(for: header, library: library, libraryId: libraryId)
        return flattenedLibraryItems(libraryId: libraryId, buckets: buckets).map(\.destination)
    }

}
