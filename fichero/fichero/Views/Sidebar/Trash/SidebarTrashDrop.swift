import SwiftUI

/// The documents a drop onto the Trash sends there (`safety.trash.drop-to-trash`, #5243): the `doc:` ids dropped, as bare
/// ids in the order dropped, minus any row whose ancestor is also dropped (the ancestor takes it; deleting it again
/// would 404 part-way through the step). Anything that is not a document id is left out. `parentOf` answers a document
/// id's parent id.
func sidebarTrashDropRoots(_ droppedIds: [String], parentOf: (String) -> String?) -> [String] {
    let bare = droppedIds.filter { $0.hasPrefix("doc:") }.map { extractActualId(from: $0) }
    let going = Set(bare)
    return bare.filter { id in
        var cursor = parentOf(id)
        var hops = 0
        while let ancestor = cursor, hops < 256 {
            if going.contains(ancestor) { return false }
            cursor = parentOf(ancestor)
            hops += 1
        }
        return true
    }
}

extension SidebarTrashRow {
    /// A drag dropped on the Trash row: an in-app item is sent to this project's Trash, the same `document.delete` a Delete
    /// key sends. Files from Finder and every other payload are refused and logged (the Trash imports nothing).
    func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard !providers.isEmpty, let onDropIds else { return false }
        let eager = eagerSidebarDropLoads(providers)
        Task {
            switch await readSidebarDropPayload(providers, surface: "sidebar-trash", preloaded: eager) {
            case .internalItems(let ids):
                await MainActor.run { onDropIds(ids) }
            default:
                DragDropLog.refused("sidebar-trash", reason: "only an item already in the library goes to the Trash")
            }
        }
        return true
    }
}
