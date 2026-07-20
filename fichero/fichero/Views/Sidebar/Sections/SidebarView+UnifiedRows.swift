import SwiftUI

// MARK: - Unified Rows

extension SidebarView {
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
        if source.contains(where: { items[$0].icon == "tray.fill" }) {
            sidebarRowLogger.debug("unifiedRows .onMove BAILED — Inbox guard")
            return
        }
        guard let libraryId, let library = libraryManager.getLibrary(id: libraryId) else {
            sidebarRowLogger.debug("unifiedRows .onMove BAILED — no libraryId/library")
            return
        }

        // Dispatch by section kind — documents, saved searches, and workflows
        // each have their own reorder endpoint (#611).
        var reordered = items
        reordered.move(fromOffsets: source, toOffset: destination)
        let kind = items.first.map { SidebarItemKind(prefixedId: $0.id) } ?? .unknown

        switch kind {
        case .document, .folder:
            reorderDocumentRows(items: items, source: source, destination: destination, library: library)
        case .savedSearch:
            reorderSavedSearchRows(reordered, library: library)
        case .workflow, .chain:
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

    /// Activity rows need a tap gesture to read `modifierFlags` for
    /// cmd-click multi-select — `List(selection:)`'s `String?` binding
    /// can't express a `Set<String>`. All other rows rely on native
    /// List selection via `.tag(item.id)`.
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
            renameState: renameState,
            deleteState: deleteState,
            sidebarState: sidebarState,
            libraryManager: libraryManager,
            onOpenChatWithCurrentScope: onOpenChatWithCurrentScope
        )
        .contentShape(Rectangle())
        .draggable(item.icon == "tray.fill" ? SidebarDragID(id: "") : SidebarDragID(id: item.id))
        .listRowInsets(EdgeInsets(top: 0, leading: 12, bottom: 0, trailing: 8))
        .moveDisabled(item.icon == "tray.fill")
        .tag(item.destination)

        if item.category == .activity {
            row.simultaneousGesture(
                TapGesture().onEnded { handleUnifiedRowTap(item) }
            )
        } else {
            row
        }
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
        guard let libraryId = libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else { return }

        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }

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
