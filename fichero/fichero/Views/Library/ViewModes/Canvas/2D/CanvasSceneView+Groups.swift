import SwiftUI

// MARK: - Groups on the board (#5570, `library.canvas.a-group-is-a-container-card`)

/// The 2D canvas's half of "a group is a container": loading each group's pages and its own
/// layout, and making a page inside a group act as part of the group's card. The layout itself is
/// `CanvasGroupNesting` (pure, tested); the frame's drawing is `CanvasOrtho2DRenderer+Groups`.
extension CanvasSceneView {
    /// What each loaded group holds: its pages and its own saved layout (the group's scope is its
    /// document id, the same board its Preview shows).
    var groupContents: [CanvasGroupContents] {
        groupPages.keys.sorted().map { nodeId in
            let scope = SpatialLibraryProjector.documentId(fromNodeId: nodeId) ?? nodeId
            return CanvasGroupContents(
                groupNodeId: nodeId,
                pages: groupPages[nodeId] ?? [],
                layoutRows: layoutStore?.layout(for: scope) ?? []
            )
        }
    }

    /// Load every group's pages and layout once. The ones on the board at open load before its
    /// first frame (`settleBoard`); a group added later draws at once, empty, and fills.
    func loadGroupPages() async {
        guard let pagesOfGroup else { return }
        for nodeId in groupNodeIds.sorted() where groupPages[nodeId] == nil {
            let pages = await pagesOfGroup(nodeId)
            guard !Task.isCancelled else { return }
            // The group's own layout BEFORE its pages are shown (#5629): shown first, the pages
            // took the default grid and then slid to their saved places when the layout landed.
            if let scope = SpatialLibraryProjector.documentId(fromNodeId: nodeId) {
                await layoutStore?.loadLayout(folderId: scope)
                guard !Task.isCancelled else { return }
            }
            groupPages[nodeId] = pages
        }
    }

    /// The card a press, click or rubber band on `id` acts on: a page's group, else the card itself.
    func owningCardId(of id: String) -> String {
        renderer.placeablesById[id]?.containerId ?? id
    }

    /// Note the pages inside the groups being dragged, with where each starts, so they move with
    /// their group while the drag lasts. They are never saved: they follow their group's place.
    func beginCarryingNestedPages(of carriedIds: [String]) {
        let carried = Set(carriedIds)
        nestedDragOrigins = renderer.placeablesById.reduce(into: [:]) { origins, entry in
            if let container = entry.value.containerId, carried.contains(container) {
                origins[entry.key] = entry.value.position
            }
        }
    }
}
