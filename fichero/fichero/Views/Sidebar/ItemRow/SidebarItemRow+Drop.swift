import Foundation
import SwiftUI
import UniformTypeIdentifiers

extension SidebarItemRow {
    func handleRowDrop(_ providers: [NSItemProvider]) -> Bool {
        #if DEBUG
        sidebarRowLogger.debug("handleRowDrop fired on \(item.name) with \(providers.count) provider(s)")
        for (idx, provider) in providers.enumerated() {
            let utis = provider.registeredTypeIdentifiers.joined(separator: ", ")
            let canURL = provider.canLoadObject(ofClass: URL.self)
            let canString = provider.canLoadObject(ofClass: NSString.self)
            sidebarRowLogger.debug("  [\(idx)] UTIs: [\(utis)]  URL:\(canURL)  String:\(canString)")
        }
        #endif

        guard !providers.isEmpty else {
            // #4533: was a bare `return false`. A drop that arrives carrying
            // nothing is a real, reportable event — and silence here is
            // indistinguishable from the drop never reaching this row.
            DragDropLog.refused("sidebar-row", reason: "no providers in the drop")
            return false
        }

        // The drop is committed — end the hover feedback NOW (#4229). If the
        // row rebuilds mid-drag (tree reload) SwiftUI can drop the trailing
        // isTargeted=false, leaving the accent wash stuck on — which reads as
        // a persistent selection. The drop must never write actual selection
        // state; it doesn't (see SidebarSelectionState writes), and this keeps
        // the visual from imitating one.
        isDropTargeted = false

        let capabilities = sidebarDropCapabilities(of: providers)
        // Worth trying to read an id? Capabilities alone can no longer decide
        // the ROUTE (#4401) — since #4123 an internal document drag also vends
        // a file — so they only decide whether to attempt the read.
        let mightBeInternal = sidebarDropMightCarryInternalID(capabilities)
        let capabilityRoute = classifySidebarDropProviders(capabilities)
        guard mightBeInternal || capabilityRoute == .externalFiles else {
            // #4533: the single most common way a sidebar drop "does nothing".
            // Name the payload shape that failed to route, or the next report
            // is another round of guessing at UTIs.
            DragDropLog.refused(
                "sidebar-row",
                reason: "payload routed to \(capabilityRoute) and carries no internal id — "
                    + "UTIs [\(capabilities.flatMap(\.registeredTypeIdentifiers).joined(separator: ", "))]"
            )
            return false
        }

        // Read FIRST, route second — via the SHARED reader, which is also what
        // the library folder cell now uses (#4474). The plumbing used to be
        // inline here, so the library pane could not reuse it without copying
        // it, and a copied classifier is how the library section header ended
        // up with a second divergent routing rule (#4401).
        Task {
            switch await readSidebarDropPayload(providers, surface: "sidebar-row(\(item.name))") {
            case .internalItems(let ids):
                _ = handleDropIntoFolder(itemIDs: ids, targetFolder: item)

            case .externalFiles:
                let targetFolder = item.isFolder ? item : parentFolderItem(of: item)
                _ = handleProvidersDrop(providers, targetFolder: targetFolder)

            case .unreadableInternal:
                // Started inside the app and we could not read what it was.
                // Re-importing would create a hollow duplicate of something
                // already here — the #4401 data loss. Say so instead.
                sidebarRowLogger.error(
                    "Sidebar drop came from inside the app but carried no readable item id; refusing to import"
                )
                sidebarState.dropErrorMessage =
                    "Couldn't read what was dragged. Nothing was moved or imported."

            case .unsupported:
                // #4533 pattern: a silent no-op is indistinguishable from the
                // drop never arriving ("I tried to drag … and nothing
                // happened", Daniel 2026-08-08). Name the payload shape.
                DragDropLog.refused(
                    "sidebar-row",
                    reason: "unsupported payload — UTIs ["
                        + providers.flatMap(\.registeredTypeIdentifiers).joined(separator: ", ") + "]"
                )
            }
        }
        return true
    }

    @ViewBuilder
    func childrenList(_ children: [SidebarItem]) -> some View {
        // Cross-hierarchy / cross-section drops use SwiftUI's native
        // `.dropDestination(for:action:)` on the ForEach (DynamicViewContent)
        // which exposes the insertion offset — the same `.above`-targeting
        // capability NSTableView has, just one level up. Same-section
        // reorder via the row's native drag handle still goes through
        // `.onMove` and shows the system's row-drop indicator.
        ForEach(Array(children.enumerated()), id: \.element.id) { _, child in
            SidebarItemRow(
                item: child,
                lookupItem: lookupItem,
                expandedItems: $expandedItems,
                selectedItemId: $selectedItemId,
                selectedDestinations: selectedDestinations,
                renameState: renameState,
                deleteState: deleteState,
                sidebarState: sidebarState,
                libraryManager: libraryManager,
                onOpenChatWithCurrentScope: onOpenChatWithCurrentScope
            )
            .contentShape(Rectangle())
            // `.draggable` BEFORE `.tag` so NSTableView's row-drag
            // mechanism arms the Transferable at the row level before
            // the row identity is bound. Apple's ArticleCollectionView
            // sample puts `.draggable` directly on the leaf cell view
            // with no intervening `.tag` — order matters here.
            .draggable(child.icon == "tray.fill" ? SidebarDragID(id: "") : SidebarDragID(item: child))
            .moveDisabled(child.icon == "tray.fill")
            .tag(child.destination)
        }
        .dropDestination(for: SidebarDragID.self) { ids, offset in
            sidebarRowLogger.debug("nested .dropDestination FIRED with \(ids.count) ids at offset \(offset)")
            handleNestedInsertionDrop(
                droppedIds: ids.map(\.id),
                at: offset,
                into: children
            )
        }
        .onMove { source, destination in
            if source.contains(where: { children[$0].icon == "tray.fill" }) {
                return
            }
            guard let store = documentStore,
                  let orderedIds = sidebarReorderedDocIds(
                    children: children,
                    moving: source,
                    to: destination
                  ) else { return }
            store.reorderChildrenOptimistically(orderedIds: orderedIds)
        }
    }

    /// ⌥/⌘⌥ insertion handling — true when the drop was consumed as a
    /// copy/alias (see `sidebarApplyInsertionDropOperation`).
    private func handleNonMoveInsertion(
        bareIds: [String], parentId: String, offset: Int, children: [SidebarItem],
        modifiers: SidebarDropModifiers
    ) -> Bool {
        // Modifiers arrive already sampled from the drop entry point (#4475 C).
        // This used to call `.current()` itself, one frame later than the folder
        // drop path did. Both happened to agree, which is exactly the shape that
        // produced this family of bugs — so the rule is now structural: below an
        // entry point you take the sample you are given.
        let operation = sidebarDropOperation(modifiers: modifiers, kind: .document)
        guard operation != .move, let library else {
            // #4533: two different reasons shared one silent exit — a MOVE is
            // declined here by design (insertion drops copy/alias only), but a
            // missing library is a fault. Reporting them as one fact is how a
            // fault reads as intended behaviour.
            DragDropLog.refused(
                "sidebar-insertion",
                reason: operation == .move
                    ? "insertion drop does not accept MOVE (operation=\(operation))"
                    : "no library bound to this window"
            )
            return false
        }
        let request = SidebarInsertionDropRequest(
            operation: operation, bareIds: bareIds, parentId: parentId,
            offset: offset, children: children
        )
        Task {
            await sidebarApplyInsertionDropOperation(
                request, library: library, sidebarState: sidebarState
            )
        }
        return true
    }

    /// Cross-hierarchy insert into THIS folder's children at `offset`.
    /// Cycle-prevented: any dropped item that is an ancestor of this
    /// folder is silently skipped (can't make a folder a child of its
    /// own descendant).
    private func handleNestedInsertionDrop(
        droppedIds: [String],
        at offset: Int,
        into children: [SidebarItem]
    ) {
        // The drop entry point: sample modifier state ONCE, here, and pass it
        // down (#4475 C).
        let modifiersAtDrop = SidebarDropModifiers.current()
        guard case .document(let parentDoc) = item.itemType,
              parentDoc.docType == .folder,
              let store = documentStore else {
            return
        }

        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }
            .filter { bareId in
                !isDescendant(item.id, of: "doc:\(bareId)")
            }

        guard !bareIds.isEmpty else {
            // #4533: was silent. Dropping a row onto its own descendant is
            // filtered above BY DESIGN, and so are non-document ids — but a
            // correctly-refused drop and a swallowed one look identical.
            DragDropLog.refused(
                "sidebar-insertion",
                reason: "no eligible document ids after filtering self/descendants"
            )
            return
        }
        // Finder modifier grammar at the insertion line: ⌥ copies, ⌘⌥ makes
        // aliases into THIS folder at this offset; plain drops keep the
        // transactional move below.
        if handleNonMoveInsertion(
            bareIds: bareIds, parentId: parentDoc.id, offset: offset, children: children,
            modifiers: modifiersAtDrop
        ) {
            return
        }

        guard let newOrder = sidebarReorderedDocIdsWithInsert(
            children: children,
            inserting: bareIds,
            at: offset
        ) else { return }

        performNestedInsertionMove(bareIds: bareIds, parentDoc: parentDoc, newOrder: newOrder, store: store)
    }

    /// The transactional move + optimistic reorder for a nested insertion —
    /// extracted verbatim from `handleNestedInsertionDrop` (lint: function
    /// body length).
    private func performNestedInsertionMove(
        bareIds: [String],
        parentDoc: Document,
        newOrder: [String],
        store: DocumentStore
    ) {
        Task {
            await MainActor.run {
                sidebarState.dropErrorMessage = nil
            }
            let moveResult = await moveSidebarDocumentsTransactionally(
                bareIds,
                toParent: parentDoc.id,
                move: { itemId, parentId in
                    _ = try await store.moveDocument(itemId, toParent: parentId)
                },
                refresh: {
                    await store.refresh()
                }
            )

            guard moveResult.isSuccessful else {
                await MainActor.run {
                    sidebarState.dropErrorMessage = moveResult.errorMessage
                }
                return
            }
            await MainActor.run {
                store.reorderChildrenOptimistically(orderedIds: newOrder)
            }
        }
    }
}
