import Foundation
import SwiftUI
import UniformTypeIdentifiers

enum SidebarDropProviderRoute: Equatable {
    case internalTextOnly
    case externalFiles
    case unsupported
}

struct SidebarDropProviderCapabilities: Equatable {
    let canLoadURL: Bool
    let canLoadString: Bool
    let registeredTypeIdentifiers: [String]
}

func classifySidebarDropProviders(_ providers: [SidebarDropProviderCapabilities]) -> SidebarDropProviderRoute {
    guard !providers.isEmpty else { return .unsupported }

    let hasExternalProvider = providers.contains { provider in
        provider.canLoadURL
            || provider.registeredTypeIdentifiers.contains {
                $0 != UTType.text.identifier && $0 != UTType.plainText.identifier
            }
    }
    if hasExternalProvider {
        return .externalFiles
    }

    let hasInternalTextProvider = providers.contains { provider in
        provider.canLoadString
    }
    if hasInternalTextProvider {
        return .internalTextOnly
    }

    return .unsupported
}

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

        let route = classifySidebarDropProviders(
            providers.map {
                SidebarDropProviderCapabilities(
                    canLoadURL: $0.canLoadObject(ofClass: URL.self),
                    canLoadString: $0.canLoadObject(ofClass: NSString.self),
                    registeredTypeIdentifiers: $0.registeredTypeIdentifiers
                )
            }
        )

        switch route {
        case .internalTextOnly:
            // Providers that only load String are internal sidebar drags.
            // `.draggable(item.id)` advertises the String via utf8PlainText.
            let textOnly = providers.filter {
                !$0.canLoadObject(ofClass: URL.self) && $0.canLoadObject(ofClass: NSString.self)
            }
            Task {
                var ids: [String] = []
                for provider in textOnly {
                    if let str = try? await Self.loadString(from: provider) {
                        ids.append(str)
                    }
                }
                guard !ids.isEmpty else { return }
                _ = handleDropIntoFolder(itemIDs: ids, targetFolder: item)
            }
            return true

        case .externalFiles:
            // Any mixed/internal+Finder payload is treated as external so we
            // don't partially route the same drop through document moves.
            let targetFolder = item.isFolder ? item : parentFolderItem(of: item)
            _ = handleProvidersDrop(providers, targetFolder: targetFolder)
            return true

        case .unsupported:
            return false
        }
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
            .draggable(child.icon == "tray.fill" ? SidebarDragID(id: "") : SidebarDragID(id: child.id))
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
