import OSLog
import SwiftUI

/// Shared, pure move-eligibility decision for moving a document into a folder
/// (#3014). The drag-drop handler and the compact "Move to Folder" menu both
/// obey it, so the menu offers exactly the targets a drop would accept — no
/// divergent second path, and the menu can no longer create a circular move.
enum SidebarMovePolicy {
    /// A folder is a valid move target for `sourceId` only when it isn't the
    /// source itself and isn't a descendant of it. Walks the target's ancestor
    /// chain over `documents` (all docs + their `parentId`s); if `sourceId`
    /// appears as an ancestor of the target, the target is inside the source and
    /// the move would be circular. `guardCount` bounds the walk against a
    /// malformed (cyclic) parent chain.
    static func isValidTarget(sourceId: String, targetId: String, documents: [Document]) -> Bool {
        if sourceId == targetId { return false }
        let parentById = Dictionary(documents.map { ($0.id, $0.parentId) }, uniquingKeysWith: { first, _ in first })
        var current: String? = targetId
        var guardCount = 0
        while let id = current, guardCount <= documents.count {
            if id == sourceId { return false }
            current = parentById[id] ?? nil
            guardCount += 1
        }
        return true
    }
}

/// Strip the type-prefix from a sidebar-item or drag-source ID.
///
/// Sidebar items carry typed IDs (`doc:UUID`, `folder:path`, `workflow:wf-42`
/// etc.) so the tree can distinguish kinds at lookup time. Drag sources in
/// other views (notably the library grid at
/// `LibraryView+DisplayModes.swift:25,110`) emit the raw UUID directly. This
/// helper normalises both forms to the bare identifier the backend API
/// expects.
///
/// - Returns: everything after the first `:` if present; the unchanged input
///   otherwise (so bare UUIDs from cross-view drags pass through).
///
/// Free function rather than a method so tests can call the real logic
/// directly — see `IDPrefixStrippingTests` in `DragDropTests.swift`.
func extractActualId(from prefixedId: String) -> String {
    if prefixedId.contains(":") {
        return String(prefixedId.split(separator: ":")[1])
    }
    return prefixedId
}

/// Classify a drag-source ID by its type prefix so the drop handler can
/// route the move to the right service (sidebar plan Step 9, #585).
///
/// Cross-section drops make sense only when the source kind matches the
/// target folder's section (e.g. dropping a saved search onto a
/// saved-search folder). The dispatcher in
/// `SidebarItemRow+DropHandlers.swift` uses this to pick between
/// `documentStore.moveDocument`, `savedSearchService.updateSavedSearch`,
/// `conversationService.moveToFolder`, and `workflowStore.moveWorkflow`.
enum SidebarItemKind: Equatable {
    case document
    case savedSearch
    case conversation
    case workflow
    case chain
    case schedule
    case trigger
    case folder
    case unknown

    /// Prefix → kind lookup. Kept as a static so callers constructing many
    /// SidebarItemKinds in a tight loop (drop handler iterating dropped
    /// item IDs) don't rebuild the dictionary per call.
    private static let prefixes: [String: SidebarItemKind] = [
        "doc": .document,
        "search": .savedSearch,
        "chat": .conversation,
        "workflow": .workflow,
        "chain": .chain,
        "schedule": .schedule,
        "trigger": .trigger,
        "folder": .folder
    ]

    init(prefixedId: String) {
        if prefixedId.isEmpty {
            self = .unknown
            return
        }
        guard prefixedId.contains(":") else {
            // Bare UUIDs (no colon) arrive from cross-view drags out of
            // the library grid (`LibraryView+DisplayModes.swift:25,110`)
            // — those always represent documents.
            self = .document
            return
        }
        let prefix = String(prefixedId.split(separator: ":", maxSplits: 1)[0])
        self = Self.prefixes[prefix] ?? .unknown
    }
}

/// Compute the new ordered list of doc IDs for a cross-hierarchy drop
/// (drag a folder/PDF from ANOTHER part of the tree and drop it at
/// `offset` within `children`). Dedupes items being moved — if a
/// dropped id is already present in children, it's removed from its
/// current position before being inserted at the new offset (so same-
/// list reorders via this path work too).
///
/// Returns nil when there's nothing to insert OR when the insertion
/// would be a no-op relative to the original order.
///
/// Pure function — unit-tested below without SwiftUI / DocumentStore.
func sidebarReorderedDocIdsWithInsert(
    children: [SidebarItem],
    inserting bareIds: [String],
    at offset: Int
) -> [String]? {
    guard !bareIds.isEmpty else { return nil }
    let existingDocIds = children.compactMap { item -> String? in
        if case .document(let doc) = item.itemType { return doc.id }
        return nil
    }
    var newOrder = existingDocIds.filter { !bareIds.contains($0) }
    let insertAt = min(max(offset, 0), newOrder.count)
    newOrder.insert(contentsOf: bareIds, at: insertAt)
    guard newOrder != existingDocIds else { return nil }
    return newOrder
}

/// Result for a transactional sidebar move batch.
struct SidebarDocumentMoveBatchResult: Equatable {
    let movedIds: [String]
    let failedItemId: String?
    let errorMessage: String?

    var isSuccessful: Bool {
        errorMessage == nil
    }
}

/// Move a set of sidebar documents to a new parent, stopping on the first
/// failure. Successful moves stay committed; the caller can then reorder the
/// successfully moved items. On failure, the authoritative store should be
/// refreshed so the UI reflects the backend's actual state.
@MainActor
func moveSidebarDocumentsTransactionally(
    _ itemIds: [String],
    toParent parentId: String?,
    move: @escaping @MainActor (String, String?) async throws -> Void,
    refresh: @escaping @MainActor () async -> Void
) async -> SidebarDocumentMoveBatchResult {
    var movedIds: [String] = []
    for itemId in itemIds {
        do {
            try await move(itemId, parentId)
            movedIds.append(itemId)
        } catch {
            await refresh()
            return SidebarDocumentMoveBatchResult(
                movedIds: movedIds,
                failedItemId: itemId,
                errorMessage: error.localizedDescription
            )
        }
    }

    return SidebarDocumentMoveBatchResult(
        movedIds: movedIds,
        failedItemId: nil,
        errorMessage: nil
    )
}

/// Compute the new ordered list of document IDs for a `.onMove` reorder.
/// Tolerates mixed-kind children: non-document items (virtual folders,
/// saved-search partitions, etc.) move along with the reorder but are
/// ignored for the reorder-endpoint payload — only documents have a
/// sortOrder to persist, so only their IDs are returned.
///
/// Returns nil when the resulting document order equals the original —
/// i.e., the move was a no-op in terms of document positions (e.g. the
/// user dragged a non-document item, or dragged a document zero net
/// positions relative to other documents).
///
/// Pure function so the index-math is unit-testable without standing
/// up a SwiftUI List or DocumentStore.
func sidebarReorderedDocIds(
    children: [SidebarItem],
    moving source: IndexSet,
    to destination: Int
) -> [String]? {
    guard !source.isEmpty else { return nil }

    // Apply the move on the full child array so non-document items
    // (virtual folder partitions) keep their relative position in the
    // displayed list while documents get their new positions.
    var reordered = children
    reordered.move(fromOffsets: source, toOffset: destination)

    let beforeDocIds = children.compactMap { item -> String? in
        if case .document(let doc) = item.itemType { return doc.id }
        return nil
    }
    let afterDocIds = reordered.compactMap { item -> String? in
        if case .document(let doc) = item.itemType { return doc.id }
        return nil
    }

    guard !afterDocIds.isEmpty else { return nil }
    guard afterDocIds != beforeDocIds else { return nil }

    return afterDocIds
}

extension SidebarItemRow {
    func isDescendant(_ potentialDescendant: String, of ancestorId: String) -> Bool {
        guard let ancestorItem = findItemById(ancestorId, in: allCachedItems) else {
            return false
        }
        return containsDescendant(potentialDescendant, in: ancestorItem)
    }

    func findItemById(_ id: String, in items: [SidebarItem]) -> SidebarItem? {
        for item in items {
            if item.id == id {
                return item
            }
            if let children = item.children,
               let found = findItemById(id, in: children) {
                return found
            }
        }
        return nil
    }

    func containsDescendant(_ targetId: String, in item: SidebarItem) -> Bool {
        if item.id == targetId {
            return true
        }
        if let children = item.children {
            for child in children where containsDescendant(targetId, in: child) {
                return true
            }
        }
        return false
    }

    /// Resolve the folder-row that should receive a file-drop when the user drops
    /// onto a leaf non-folder row (e.g. a PDF or image file). Returns nil if the
    /// item has no parent folder (drop should fall through to library root) or if
    /// the item isn't a Document at all (searches, workflows — drop to root).
    ///
    /// Used so that dropping a file onto `page1.pdf` imports the new file next to
    /// it (into the same folder), matching Finder's sibling-drop behaviour.
    func parentFolderItem(of item: SidebarItem) -> SidebarItem? {
        guard case .document(let doc) = item.itemType,
              let parentId = doc.parentId else {
            return nil
        }
        return findItemById("doc:\(parentId)", in: allCachedItems)
    }

    /// Dispatch a sidebar drag-drop move to the appropriate backend service
    /// based on the source item's kind. Sidebar plan Step 9 (#585).
    ///
    /// For documents: calls `documentStore.moveDocument` with `parent_id`.
    /// For non-documents (searches, conversations, workflows): calls the
    /// corresponding service's folder-path update. Each virtual folder
    /// carries its `folderPath` inside `ItemType.folder(folderPath:)`, so
    /// the target's folder path becomes the new `folder_path` for the
    /// moved item.
    ///
    /// Cross-section moves (e.g. dropping a document onto a search folder)
    /// are rejected upstream in `handleDropIntoFolder`; this method assumes
    /// the caller has already validated source-kind vs target-kind.
    func routeMove(itemId: String, targetFolder: SidebarItem) async {
        let kind = SidebarItemKind(prefixedId: itemId)
        let actualItemId = extractActualId(from: itemId)
        sidebarRowLogger.debug(" routeMove: \(itemId) (kind=\(String(describing: kind))) → \(targetFolder.name)")

        // Documents share ONE executor with the compact "Move to Folder" menu
        // (#3014) — same store call + error surfacing, no divergent path.
        if kind == .document {
            await moveDocumentToFolder(
                documentId: actualItemId,
                folderId: extractActualId(from: targetFolder.id)
            )
            return
        }

        do {
            switch kind {
            case .document:
                return  // handled above
            case .savedSearch:
                guard let service = savedSearchService,
                      case .folder(let folderPath) = targetFolder.itemType else { return }
                _ = try await service.updateSavedSearch(actualItemId, folderPath: folderPath)
            case .conversation:
                guard let service = conversationService,
                      case .folder(let folderPath) = targetFolder.itemType else { return }
                _ = try await service.moveToFolder(actualItemId, folderPath: folderPath)
            case .workflow:
                guard let store = workflowStore,
                      case .folder(let folderPath) = targetFolder.itemType else { return }
                try await store.moveWorkflow(actualItemId, toFolder: folderPath)
            default:
                sidebarRowLogger.debug(" routeMove: kind \(String(describing: kind)) has no move handler")
                return
            }
            sidebarRowLogger.debug(" Move successful — UI updates via @Published")
        } catch {
            // Surface the failure instead of a silent no-op (#3027 /
            // prefer-raise-over-silent-fallback). Same channel the compact
            // "Move to Folder" menu already uses, so drag-drop moves that fail
            // now show the user feedback rather than appearing to do nothing.
            sidebarRowLogger.error("Move failed: \(error.localizedDescription)")
            sidebarState.dropErrorMessage = error.localizedDescription
        }
    }

    /// Shared document-move executor (#3014): the store call + error surfacing
    /// both the drag-drop path (`routeMove`) and the compact "Move to Folder"
    /// menu use, so document moves have exactly one executor. Ids are raw
    /// (already un-prefixed).
    func moveDocumentToFolder(documentId: String, folderId: String) async {
        guard let documentStore else { return }
        do {
            _ = try await documentStore.moveDocument(documentId, toParent: folderId)
            sidebarRowLogger.debug(" Move successful — UI updates via @Published")
        } catch {
            sidebarRowLogger.error("Move failed: \(error.localizedDescription)")
            sidebarState.dropErrorMessage = error.localizedDescription
        }
    }

    /// Legacy single-target mover retained so existing call sites keep
    /// compiling while we migrate them to `routeMove`. Documents-only.
    func moveItemToFolder(itemId: String, targetFolderId: String) async {
        sidebarRowLogger.debug(" moveItemToFolder: \(itemId) → \(targetFolderId)")

        guard let documentStore = documentStore else { return }

        let actualItemId = extractActualId(from: itemId)
        let actualTargetId = extractActualId(from: targetFolderId)

        do {
            _ = try await documentStore.moveDocument(actualItemId, toParent: actualTargetId)
            sidebarRowLogger.debug(" Move successful - UI updates automatically via @Published")
        } catch {
            sidebarRowLogger.debug(" Move failed: \(error.localizedDescription)")
        }
    }
}
