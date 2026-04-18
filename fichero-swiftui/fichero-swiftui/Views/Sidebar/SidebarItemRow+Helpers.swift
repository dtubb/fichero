import OSLog
import SwiftUI

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

/// Decision returned by `sidebarDropRoute(for:)` for a set of
/// drag-providers landing on a folder row. Pure enum so the drop
/// handler's routing logic is unit-testable independently of
/// NSItemProvider's async loading machinery.
enum SidebarDropRoute: Equatable {
    /// At least one provider is internal-sidebar-only (can load
    /// String but not URL). The handler should load the IDs and
    /// route them through `handleDropIntoFolder`.
    case internalMove

    /// At least one provider can produce something (URL, binary,
    /// or similar). Optimistic accept — the handler hands the full
    /// provider list to `handleProvidersDrop` which loads URLs
    /// asynchronously and silently no-ops if nothing URL-shaped
    /// materialises.
    case finderImport

    /// No providers at all. Drop destination returns false and the
    /// OS plays its bounce-back animation.
    case reject
}

/// Summary of a single NSItemProvider's classification capabilities —
/// everything the routing decision needs without an actual provider.
/// Lets tests exercise the classifier without mocking NSItemProvider.
struct SidebarDropProviderCapability: Equatable {
    let canLoadURL: Bool
    let canLoadString: Bool
}

/// Routes a sidebar folder drop based on what the pasteboard can
/// produce. Internal drags (`.draggable(item.id)` uses String's
/// Transferable representation, which advertises utf8-plain-text
/// only and cannot produce a URL) go through `.internalMove`;
/// everything else with at least one provider goes through
/// `.finderImport` optimistically. Empty provider list → `.reject`.
///
/// Pure function — unit-tested in `DragDropTests`.
func sidebarDropRoute(for providers: [SidebarDropProviderCapability]) -> SidebarDropRoute {
    guard !providers.isEmpty else { return .reject }
    let hasTextOnly = providers.contains { !$0.canLoadURL && $0.canLoadString }
    if hasTextOnly { return .internalMove }
    return .finderImport
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

        do {
            switch kind {
            case .document:
                guard let documentStore = documentStore else { return }
                let actualTargetId = extractActualId(from: targetFolder.id)
                _ = try await documentStore.moveDocument(actualItemId, toParent: actualTargetId)
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
                sidebarRowLogger.debug(" ⚠️ routeMove: kind \(String(describing: kind)) has no move handler")
                return
            }
            sidebarRowLogger.debug(" ✅ Move successful — UI updates via @Published")
        } catch {
            sidebarRowLogger.debug(" ❌ Move failed: \(error.localizedDescription)")
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
            sidebarRowLogger.debug(" ✅ Move successful - UI updates automatically via @Published")
        } catch {
            sidebarRowLogger.debug(" ❌ Move failed: \(error.localizedDescription)")
        }
    }
}
