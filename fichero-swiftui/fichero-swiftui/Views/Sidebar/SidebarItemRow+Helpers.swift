import OSLog
import SwiftUI

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

    func extractActualId(from prefixedId: String) -> String {
        if prefixedId.contains(":") {
            return String(prefixedId.split(separator: ":")[1])
        }
        return prefixedId
    }

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
