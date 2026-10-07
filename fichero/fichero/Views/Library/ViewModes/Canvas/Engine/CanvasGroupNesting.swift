import CoreGraphics
import Foundation
import simd

// MARK: - A group is a container card (#5570, `library.canvas.a-group-is-a-container-card`)

/// What one group on the board holds: its pages, in the group's order, and the group's OWN saved
/// layout (the board its Preview shows, one layout per group — `FolderContentsPreview`).
struct CanvasGroupContents: Equatable {
    /// The group's node id on the board (`doc:<groupId>`).
    let groupNodeId: String
    /// The pages, in order, as page nodes (`doc:<pageId>`).
    let pages: [SpatialNode]
    /// The group's own layout rows, read under the group's scope. Empty → a grid in page order.
    let layoutRows: [CanvasItemLayout]
}

/// Lays each group's pages INSIDE the group's card, as a window onto the group's own board.
///
/// Pure, renderer-free and unit-tested, like the rest of the canvas engine. Applied after
/// `CanvasSceneState.resolve`, so the group itself is placed by the ONE position rule (a saved row
/// wins, else its grid slot) and its pages follow it: they are never rows on the parent board, so
/// moving the group moves them, and nothing the parent board saves can pull a page out of its
/// group.
///
/// The frame is one card's footprint unless the group was resized (its saved `w`/`h`); its pages
/// are the group's layout scaled uniformly into the frame's inner rect. Zoomed out, a box of
/// groups reads as framed tiles; zoomed in, the pages read as pages.
enum CanvasGroupNesting {
    /// The frame's inner margin, as a fraction of its smaller side.
    static let insetFraction = 0.06

    /// The id under which a page's row is read from the group's layout: the app writes node ids
    /// (`doc:<id>`), and a layout written through the engine or the CLI may hold bare ids.
    private static func savedRow(for page: SpatialNode, in rows: [String: CanvasItemLayout]) -> CanvasItemLayout? {
        rows[page.id] ?? page.sourceId.flatMap { rows[$0] }
    }

    /// The scene with every listed group drawn as a container holding its pages.
    ///
    /// - Every group placeable in `groupNodeIds` is marked a container, whether or not its pages
    ///   have loaded, so its card never draws as a picture and then turns into a frame.
    /// - Pages are added after the top-level placeables, one step above their group, each tagged
    ///   with its `containerId`.
    static func nest(
        _ state: CanvasSceneState,
        groupNodeIds: Set<String>,
        contents: [CanvasGroupContents]
    ) -> CanvasSceneState {
        guard !groupNodeIds.isEmpty else { return state }
        var nested = state
        var byGroup: [String: CanvasGroupContents] = [:]
        for content in contents { byGroup[content.groupNodeId] = content }
        let topLevelIds = Set(state.placeables.map(\.id))
        var pagePlaceables: [CanvasPlaceable] = []
        for index in nested.placeables.indices where groupNodeIds.contains(nested.placeables[index].id) {
            nested.placeables[index].isContainer = true
            let group = nested.placeables[index]
            guard let content = byGroup[group.id] else { continue }
            // A page also listed on the parent board (it should not be: it lives in the group)
            // stays where the board put it rather than being drawn twice.
            let pages = content.pages.filter { !topLevelIds.contains($0.id) }
            pagePlaceables += layOut(pages: pages, rows: content.layoutRows, in: group)
        }
        nested.placeables += pagePlaceables
        return nested
    }

    /// The group whose card a placeable belongs to on this board: a page's group, else itself.
    /// Clicks and drags on a page act on its group (the pages are worked on inside the group,
    /// where the group's own board shows them).
    static func owningCardId(of id: String, in state: CanvasSceneState) -> String {
        state.placeables.first { $0.id == id }?.containerId ?? id
    }

    /// The page placeables of one group, laid out inside its frame.
    static func layOut(pages: [SpatialNode], rows: [CanvasItemLayout], in group: CanvasPlaceable) -> [CanvasPlaceable] {
        guard !pages.isEmpty else { return [] }
        let rowsById = Dictionary(rows.map { ($0.itemId, $0) }, uniquingKeysWith: { _, latest in latest })
        let cell = CanvasGridPlacement.nominalCell
        let columns = defaultColumns(pageCount: pages.count)
        // Each page's place on the group's own board: its saved row, else its grid slot in order.
        let local: [SIMD2<Double>] = pages.enumerated().map { index, page in
            if let row = savedRow(for: page, in: rowsById) { return SIMD2(row.x, row.y) }
            let slot = CanvasGridPlacement.position(index: index, columns: columns, cell: cell)
            return SIMD2(slot.x, slot.y)
        }
        let cardWidth = CanvasGridPlacement.cardWidth, cardHeight = CanvasGridPlacement.cardHeight
        let minX = local.map(\.x).min()! - cardWidth / 2, maxX = local.map(\.x).max()! + cardWidth / 2
        let minY = local.map(\.y).min()! - cardHeight / 2, maxY = local.map(\.y).max()! + cardHeight / 2
        let frame = group.size ?? CGSize(width: cardWidth, height: cardHeight)
        let inset = insetFraction * Double(min(frame.width, frame.height))
        let innerWidth = max(Double(frame.width) - 2 * inset, 0.01)
        let innerHeight = max(Double(frame.height) - 2 * inset, 0.01)
        let scale = min(innerWidth / (maxX - minX), innerHeight / (maxY - minY))
        let centre = SIMD2((minX + maxX) / 2, (minY + maxY) / 2)
        return pages.enumerated().map { index, page in
            let offset = (local[index] - centre) * scale
            return CanvasPlaceable(
                id: page.id,
                content: .node(page),
                position: SIMD3(group.position.x + offset.x, group.position.y + offset.y, group.position.z),
                size: CGSize(width: cardWidth * scale, height: cardHeight * scale),
                zIndex: group.zIndex + 1,
                containerId: group.id
            )
        }
    }

    /// Columns for a group with no saved layout: roughly square, so a frame of one card's shape
    /// is filled rather than threaded with one long row.
    static func defaultColumns(pageCount: Int) -> Int {
        max(Int(Double(pageCount).squareRoot().rounded(.up)), 1)
    }

    /// A group's pages as page nodes, in the group's order (sort order, then name naturally), the
    /// same node ids the rest of the canvas uses (`doc:<id>`).
    static func pageNodes(_ pages: [Document]) -> [SpatialNode] {
        pages.sorted { $0.filedOrder < $1.filedOrder }.map { page in
            SpatialNode(
                id: SpatialLibraryProjector.nodeId(forDocument: page.id),
                roomId: wholeLibraryRoomId,
                nodeType: .source,
                sourceId: page.id,
                label: page.name,
                positionX: 0,
                positionY: 0
            )
        }
    }

    /// The board's group node ids, from the documents it lists.
    static func groupNodeIds(in documents: [Document]) -> Set<String> {
        Set(documents.filter(\.isGroup).map { SpatialLibraryProjector.nodeId(forDocument: $0.id) })
    }
}

extension DocumentStore {
    /// A group's pages as canvas page nodes (#5570), through the store's one cached child fetch.
    func canvasPageNodes(ofGroupNode nodeId: String) async -> [SpatialNode] {
        guard let groupId = SpatialLibraryProjector.documentId(fromNodeId: nodeId) else { return [] }
        return CanvasGroupNesting.pageNodes(await children(of: groupId))
    }
}
