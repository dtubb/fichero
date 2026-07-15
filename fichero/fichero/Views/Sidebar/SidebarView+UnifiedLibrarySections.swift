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
            let totalCount = buckets.documentItems.count + buckets.searchItems.count + buckets.workflowItems.count +
                buckets.chainItems.count + buckets.scheduleItems.count + buckets.triggerItems.count +
                buckets.activityItems.count

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

    @ViewBuilder
    func unifiedLibrarySections(
        libraryId: UUID,
        buckets: UnifiedLibraryBuckets
    ) -> some View {
        unifiedDisclosureSection(
            title: "Library",
            icon: "books.vertical",
            sectionKey: "library",
            libraryId: libraryId,
            items: buckets.documentItems
        )

        // Visual separator between document library and tools section.
        // Non-interactive: must not be selectable or receive clicks (#2310).
        Divider()
            .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
            .allowsHitTesting(false)
            .selectionDisabled()

        // Workflows / Batches / Activity used to render here, once per
        // library. They are app-level destinations (fixed selection tags, no
        // library scope), so repeating them under every library both
        // duplicated the rows and made all copies highlight together. They are
        // now pinned ONCE at the bottom of the sidebar — see
        // `pinnedGlobalNavigationRows()` in `unifiedContent`. (#1456)

        if FeatureManager.shared.isAutomationEnabled {
            unifiedDisclosureSection(
                title: "Automation",
                icon: "gearshape.2",
                sectionKey: "automation",
                libraryId: libraryId,
                items: buckets.scheduleItems + buckets.triggerItems
            )
        }

        // Saved Searches at the bottom — Daniel: 'saved searches should
        // be down beside Workflows and Activity'. Mental model: Library
        // is the source-of-truth tree; Workflows / Activity / Saved
        // Searches are *tools and history* over that tree, so they
        // belong together below the library.
        if FeatureManager.shared.isSearchEnabled {
            unifiedDisclosureSection(
                title: "Saved Searches",
                icon: "magnifyingglass",
                sectionKey: "search",
                libraryId: libraryId,
                items: buckets.searchItems
            )
        }
    }

    @ViewBuilder
    func unifiedDisclosureSection(
        title: String,
        icon: String,
        sectionKey: String,
        libraryId: UUID,
        items: [SidebarItem]
    ) -> some View {
        if !items.isEmpty {
            DisclosureGroup(
                isExpanded: Binding(
                    get: { isUnifiedSectionExpanded(libraryId: libraryId, sectionKey: sectionKey) },
                    set: { setUnifiedSectionExpanded($0, libraryId: libraryId, sectionKey: sectionKey) }
                ),
                content: {
                    unifiedRows(items, libraryId: libraryId)
                        // Let the section open/close drive the reveal. If the
                        // nested rows animate their own insertion, SwiftUI can
                        // slide them in from the wrong lateral origin when a
                        // disclosure expands (#3165).
                        .transaction { transaction in
                            transaction.animation = nil
                        }
                },
                label: {
                    Label(title, systemImage: icon)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(.primary)
                        .selectionDisabled()
                }
            )
        }
    }

    func unifiedSectionStorageKey(libraryId: UUID, sectionKey: String) -> String {
        "unified-section:\(libraryId.uuidString):\(sectionKey)"
    }

    func isUnifiedSectionExpanded(libraryId: UUID, sectionKey: String) -> Bool {
        let key = unifiedSectionStorageKey(libraryId: libraryId, sectionKey: sectionKey)
        return sidebarState.unifiedSectionExpansionStates[key] ?? true
    }

    func setUnifiedSectionExpanded(_ expanded: Bool, libraryId: UUID, sectionKey: String) {
        let key = unifiedSectionStorageKey(libraryId: libraryId, sectionKey: sectionKey)
        sidebarState.unifiedSectionExpansionStates[key] = expanded
    }
}
