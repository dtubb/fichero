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

        guard !providers.isEmpty else { return false }

        // The drop is committed — end the hover feedback NOW (#4229). If the
        // row rebuilds mid-drag (tree reload) SwiftUI can drop the trailing
        // isTargeted=false, leaving the accent wash stuck on — which reads as
        // a persistent selection. The drop must never write actual selection
        // state; it doesn't (see SidebarSelectionState writes), and this keeps
        // the visual from imitating one.
        isDropTargeted = false

        let capabilities = providers.map {
            SidebarDropProviderCapabilities(
                canLoadURL: $0.canLoadObject(ofClass: URL.self),
                canLoadString: $0.canLoadObject(ofClass: NSString.self),
                registeredTypeIdentifiers: $0.registeredTypeIdentifiers
            )
        }
        let hasFileURL = capabilities.contains(where: \.canLoadURL)
        // Worth trying to read an id? Capabilities alone can no longer decide
        // the ROUTE (#4401) — since #4123 an internal document drag also vends
        // a file — so they only decide whether to attempt the read.
        let mightBeInternal = sidebarDropMightCarryInternalID(capabilities)
        let capabilityRoute = classifySidebarDropProviders(capabilities)
        guard mightBeInternal || capabilityRoute == .externalFiles else { return false }

        // Read FIRST, route second. Every provider is asked for a string,
        // including ones that can also vend a URL — that inclusion is the fix,
        // because the document drags this bug destroyed vend both.
        Task {
            var loadedIDs: [String] = []
            for provider in providers where provider.canLoadObject(ofClass: NSString.self) {
                if let string = try? await Self.loadString(from: provider) {
                    loadedIDs.append(string)
                }
            }
            let payload = classifySidebarDropPayload(
                loadedIDs: loadedIDs,
                hasFileURL: hasFileURL,
                carriesOwnProcessFlavor: mightBeInternal
            )
            switch payload {
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
                break
            }
        }
        return true
    }

    /// Async helper to unwrap a plain-text NSItemProvider into a String.
    /// Matches the `loadURL` helper's pattern on `SidebarItemRow+DropHandlers`.
    private static func loadString(from provider: NSItemProvider) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: NSString.self) { value, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let nsString = value as? NSString {
                    continuation.resume(returning: nsString as String)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarRowDrop", code: -1))
                }
            }
        }
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
                allCachedItems: allCachedItems,
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
        bareIds: [String], parentId: String, offset: Int, children: [SidebarItem]
    ) -> Bool {
        let operation = sidebarDropOperation(modifiers: .current(), kind: .document)
        guard operation != .move, let library else { return false }
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

        guard !bareIds.isEmpty else { return }
        // Finder modifier grammar at the insertion line: ⌥ copies, ⌘⌥ makes
        // aliases into THIS folder at this offset; plain drops keep the
        // transactional move below.
        if handleNonMoveInsertion(
            bareIds: bareIds, parentId: parentDoc.id, offset: offset, children: children
        ) {
            return
        }

        guard let newOrder = sidebarReorderedDocIdsWithInsert(
            children: children,
            inserting: bareIds,
            at: offset
        ) else { return }

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
