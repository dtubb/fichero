import SwiftUI

// MARK: - Unified Rows

extension SidebarView {
    static func sidebarUnifiedRowsReorderKind(
        items: [SidebarItem],
        source: IndexSet,
        destination: Int
    ) -> SidebarItemKind? {
        let sourceItems = source.compactMap { index -> SidebarItem? in
            guard items.indices.contains(index) else { return nil }
            return items[index]
        }
        guard sourceItems.count == source.count else { return nil }
        guard let movedKind = sourceItems.first.map(unifiedRowsReorderKind(for:)) else { return nil }
        guard sourceItems.allSatisfy({ unifiedRowsReorderKind(for: $0) == movedKind }) else { return nil }
        guard movedKind != .unknown else { return nil }

        let kindPositions = items.indices.filter { unifiedRowsReorderKind(for: items[$0]) == movedKind }
        guard let firstKindPosition = kindPositions.first,
              let lastKindPosition = kindPositions.last else { return nil }
        guard kindPositions == Array(firstKindPosition...lastKindPosition) else { return nil }
        guard source.allSatisfy({ kindPositions.contains($0) }) else { return nil }

        var reordered = items
        reordered.move(fromOffsets: source, toOffset: destination)
        let reorderedKindPositions = reordered.indices.filter { unifiedRowsReorderKind(for: reordered[$0]) == movedKind }
        guard reorderedKindPositions == kindPositions else { return nil }

        return movedKind
    }

    static func unifiedRowsReorderKind(for item: SidebarItem) -> SidebarItemKind {
        switch item.itemType {
        case .document:
            return .document
        case .savedSearch:
            return .savedSearch
        case .workflow:
            return .workflow
        case .folder:
            switch item.category {
            case .folder:
                return .document
            case .search:
                return .savedSearch
            case .workflow:
                return .workflow
            default:
                return .unknown
            }
        default:
            return .unknown
        }
    }

    @ViewBuilder
    func unifiedRows(
        _ items: [SidebarItem],
        libraryId: UUID? = nil
    ) -> some View {
        // Cross-hierarchy / cross-section drops at the root level use
        // `.dropDestination(for:action:)` on the ForEach — SwiftUI's
        // built-in between-row insertion API, which receives the offset
        // natively (no custom overlay strip needed). Same-section
        // reorder still goes through `.onMove` and shows the system's
        // row-drop indicator.
        ForEach(Array(items.enumerated()), id: \.element.id) { _, item in
            unifiedRow(for: item)
        }
        .dropDestination(for: SidebarDragID.self) { ids, offset in
            sidebarRowLogger.debug("unifiedRows .dropDestination FIRED with \(ids.count) ids at offset \(offset)")
            handleExternalInsertionDrop(
                droppedIds: ids.map(\.id),
                at: offset,
                into: items,
                libraryId: libraryId
            )
        }
        .onMove { source, destination in
            handleUnifiedRowsMove(source: source, destination: destination, items: items, libraryId: libraryId)
        }
    }

    private func handleUnifiedRowsMove(
        source: IndexSet,
        destination: Int,
        items: [SidebarItem],
        libraryId: UUID?
    ) {
        let sourceDesc = source.map(\.description).joined(separator: ",")
        sidebarRowLogger.debug(
            "unifiedRows .onMove FIRED — source=\(sourceDesc) dest=\(destination) items=\(items.count)"
        )

        // Defensive Inbox guard (belt + suspenders with `.moveDisabled`).
        if source.contains(where: { items.indices.contains($0) && items[$0].icon == "tray.fill" }) {
            sidebarRowLogger.debug("unifiedRows .onMove BAILED — Inbox guard")
            return
        }
        guard let libraryId, let library = libraryManager.getLibrary(id: libraryId) else {
            sidebarRowLogger.debug("unifiedRows .onMove BAILED — no libraryId/library")
            return
        }

        guard let kind = Self.sidebarUnifiedRowsReorderKind(
            items: items,
            source: source,
            destination: destination
        ) else {
            sidebarRowLogger.debug("unifiedRows .onMove BAILED — invalid cross-kind reorder")
            // The system shows an insertion indicator, then the rows snap
            // back — say why instead of leaving a silent no-op (#7).
            sidebarState.dropErrorMessage =
                "Rows of different kinds can't be reordered together — drag rows of one kind at a time."
            return
        }

        // Dispatch by the moved row's actual kind — documents, saved searches,
        // and workflows each have their own reorder endpoint (#611). The
        // flattened library list intentionally rejects cross-kind moves instead
        // of routing them through whichever kind happens to be first in the list.
        var reordered = items
        reordered.move(fromOffsets: source, toOffset: destination)

        switch kind {
        case .document:
            reorderDocumentRows(items: items, source: source, destination: destination, library: library)
        case .savedSearch:
            reorderSavedSearchRows(reordered, library: library)
        case .workflow:
            reorderWorkflowRows(reordered, library: library)
        default:
            return
        }
    }

    private func reorderDocumentRows(
        items: [SidebarItem],
        source: IndexSet,
        destination: Int,
        library: LibraryManager.LibraryReference
    ) {
        if let orderedIds = sidebarReorderedDocIds(children: items, moving: source, to: destination) {
            library.documentStore.reorderChildrenOptimistically(orderedIds: orderedIds)
        }
    }

    private func reorderSavedSearchRows(_ reordered: [SidebarItem], library: LibraryManager.LibraryReference) {
        let ordered = reordered.compactMap { item -> String? in
            guard case .savedSearch(let search) = item.itemType else { return nil }
            return search.id
        }
        guard !ordered.isEmpty else { return }
        Task {
            try? await library.savedSearchService.reorderSavedSearches(ordered)
            try? await library.savedSearchService.loadSavedSearches()
        }
    }

    private func reorderWorkflowRows(_ reordered: [SidebarItem], library: LibraryManager.LibraryReference) {
        let ordered = reordered.compactMap { item -> String? in
            if case .workflow(let workflow) = item.itemType { return workflow.id }
            return nil
        }
        guard !ordered.isEmpty else { return }
        Task {
            try? await library.workflowService.reorderWorkflows(ordered)
            await library.workflowStore.loadWorkflows()
        }
    }

    /// Rows rely on native `List(selection: Set)` for click / shift-range /
    /// cmd-toggle selection via `.tag(item.destination)`.
    @ViewBuilder
    private func unifiedRow(for item: SidebarItem) -> some View {
        // `.moveDisabled` blocks AppKit-level reorder drag on Inbox
        // (#621). `.draggable` lives here on the row container — not
        // inside SidebarItemRow's body — so NSTableView's native
        // row-drag picks up the Transferable uniformly across the
        // whole row (including taps on the inner icon/name).
        let row = SidebarItemRow(
            item: item,
            allCachedItems: allCachedItems,
            expandedItems: Binding(
                get: { sidebarState.expandedItems },
                set: { sidebarState.expandedItems = $0 }
            ),
            selectedItemId: Binding(
                get: { selectionState.selectedItemId },
                set: { selectionState.selectedItemId = $0 }
            ),
            selectedDestinations: selectionState.selectedDestinations,
            renameState: renameState,
            deleteState: deleteState,
            sidebarState: sidebarState,
            libraryManager: libraryManager,
            onOpenChatWithCurrentScope: onOpenChatWithCurrentScope
        )
        .contentShape(Rectangle())
        // Full payload (#4123): document rows export a real file copy + RTF
        // transcript to other apps; the in-process id flavor is unchanged.
        .draggable(item.icon == "tray.fill" ? SidebarDragID(id: "") : SidebarDragID(item: item))
        .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
        // Inbox is anchored (#621); non-reorderable kinds (schedules, triggers,
        // conversations…) disable the move drag so they don't show a system
        // insertion indicator that snaps back with no effect.
        .moveDisabled(item.icon == "tray.fill" || !item.supportsSidebarReorder)
        .tag(item.destination)

        row
    }

    /// Cross-hierarchy insert: reparent dragged docs to library root
    /// and drop them at position `offset` in the root's children.
    /// Called by overlay insertion-line strips in `unifiedRows`.
    ///
    /// Guards:
    ///   - Only "doc:" prefixed IDs (documents / folders) accepted.
    ///   - No cycle check needed: library root has no ancestors, so
    ///     any item can become a root child without forming a loop.
    private func handleExternalInsertionDrop(
        droppedIds: [String],
        at offset: Int,
        into items: [SidebarItem],
        libraryId: UUID?
    ) {
        // The drop entry point: sample modifier state ONCE, here, and pass the
        // sampled value down (#4475 C). Nothing below re-reads live flags.
        let modifiersAtDrop = SidebarDropModifiers.current()
        guard let libraryId = libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else { return }

        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }
        guard !bareIds.isEmpty else { return }

        // Finder modifier grammar at the insertion line: ⌥ copies, ⌘⌥ makes
        // aliases — both land at exactly this offset; plain drops keep the
        // existing transactional move below.
        let operation = sidebarDropOperation(modifiers: modifiersAtDrop, kind: .document)
        if operation != .move {
            let request = SidebarInsertionDropRequest(
                operation: operation, bareIds: bareIds, parentId: nil,
                offset: offset, children: items
            )
            Task {
                await sidebarApplyInsertionDropOperation(
                    request, library: library, sidebarState: sidebarState
                )
            }
            return
        }

        guard let newOrder = sidebarReorderedDocIdsWithInsert(
            children: items,
            inserting: bareIds,
            at: offset
        ) else { return }

        Task {
            await MainActor.run {
                sidebarState.dropErrorMessage = nil
            }
            let moveResult = await moveSidebarDocumentsTransactionally(
                bareIds,
                toParent: nil,
                move: { itemId, parentId in
                    _ = try await library.documentStore.moveDocument(itemId, toParent: parentId)
                },
                refresh: {
                    await library.documentStore.refresh()
                }
            )

            guard moveResult.isSuccessful else {
                await MainActor.run {
                    sidebarState.dropErrorMessage = moveResult.errorMessage
                }
                return
            }
            await MainActor.run {
                library.documentStore.reorderChildrenOptimistically(orderedIds: newOrder)
            }
        }
    }
}
