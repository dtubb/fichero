@testable import Fichero
import CoreGraphics
import Testing

/// A group is a container card on the canvas (#5570, `library.canvas.a-group-is-a-container-card`).
///
/// Drives the real scene resolution (`CanvasSceneState.resolve`, the one position rule) and then
/// the nesting the 2D canvas applies to it, with the same node ids, layout rows and grid the canvas
/// uses. Istmina's '1948 Sentencias' is the case: groups of 6 to 62 photographed leaves, each
/// group's own board an 8-column grid.
@MainActor
@Suite("A group is a container card on the canvas (#5570)")
struct CanvasGroupNestingTests {

    private func node(_ id: String) -> SpatialNode {
        SpatialNode(
            id: SpatialLibraryProjector.nodeId(forDocument: id), roomId: wholeLibraryRoomId,
            nodeType: .source, sourceId: id, label: id, positionX: 0, positionY: 0
        )
    }

    private let groupNode = SpatialLibraryProjector.nodeId(forDocument: "g")

    private func board(groupRow: CanvasItemLayout? = nil) -> CanvasSceneState {
        CanvasSceneState.resolve(
            nodes: [node("loose"), node("g")], connections: [], links: [],
            layoutRows: groupRow.map { [$0] } ?? [], items: [],
            defaultPlacement: .grid(columns: 2)
        )
    }

    private func pages(_ count: Int) -> [SpatialNode] {
        (1...count).map { node("leaf\($0)") }
    }

    /// The Istmina layouts: an 8-column grid on the group's own board, written with bare ids.
    private func eightColumnRows(_ pages: [SpatialNode]) -> [CanvasItemLayout] {
        pages.enumerated().map { index, page in
            CanvasItemLayout(itemId: page.sourceId ?? page.id, x: Double(index % 8) * 1.2, y: Double(index / 8) * 1.0)
        }
    }

    private func nested(_ state: CanvasSceneState, pages: [SpatialNode], rows: [CanvasItemLayout] = []) -> CanvasSceneState {
        CanvasGroupNesting.nest(
            state, groupNodeIds: [groupNode],
            contents: [CanvasGroupContents(groupNodeId: groupNode, pages: pages, layoutRows: rows)]
        )
    }

    private func frameOf(_ state: CanvasSceneState) throws -> CanvasPlaceable {
        try #require(state.placeables.first { $0.id == groupNode })
    }

    private func pagePlaceables(_ state: CanvasSceneState) -> [CanvasPlaceable] {
        state.placeables.filter { $0.containerId == groupNode }
    }

    @Test("the group is a frame from the first frame on, even before its pages load")
    func groupIsAFrameBeforeItsPagesLoad() throws {
        let state = CanvasGroupNesting.nest(board(), groupNodeIds: [groupNode], contents: [])
        #expect(try frameOf(state).isContainer)
        #expect(state.placeables.first { $0.id == SpatialLibraryProjector.nodeId(forDocument: "loose") }?.isContainer == false)
        #expect(pagePlaceables(state).isEmpty)
    }

    @Test("every page is drawn inside the group's frame, one step above it, in order")
    func pagesLieInsideTheFrame() throws {
        let leaves = pages(12)
        let state = nested(board(), pages: leaves)
        let frame = try frameOf(state)
        let inside = pagePlaceables(state)
        #expect(inside.map(\.id) == leaves.map(\.id))
        let halfWidth = CanvasGridPlacement.cardWidth / 2, halfHeight = CanvasGridPlacement.cardHeight / 2
        for page in inside {
            let size = try #require(page.size)
            #expect(page.zIndex == frame.zIndex + 1)
            #expect(abs(page.position.x - frame.position.x) + Double(size.width) / 2 <= halfWidth + 1e-9)
            #expect(abs(page.position.y - frame.position.y) + Double(size.height) / 2 <= halfHeight + 1e-9)
            #expect(Double(size.width) < CanvasGridPlacement.cardWidth)
        }
        // Read in order: the first leaf left of the second, on the same line.
        #expect(inside[0].position.x < inside[1].position.x)
        #expect(inside[0].position.y == inside[1].position.y)
    }

    @Test("the group's own saved layout is the arrangement inside the frame (bare or node ids)")
    func savedLayoutIsUsed() {
        let leaves = pages(20)
        let state = nested(board(), pages: leaves, rows: eightColumnRows(leaves))
        let inside = pagePlaceables(state)
        // Eight across: leaves 1-8 share a line, leaf 9 starts the next, under leaf 1.
        #expect(Set(inside[0..<8].map(\.position.y)).count == 1)
        #expect(inside[8].position.y != inside[0].position.y)
        #expect(abs(inside[8].position.x - inside[0].position.x) < 1e-9)
    }

    @Test("moving the group moves every page by the same amount; the pages are never rows of their own")
    func movingTheGroupMovesItsPages() throws {
        let leaves = pages(6)
        let before = nested(board(groupRow: CanvasItemLayout(itemId: groupNode, x: 0, y: 0)), pages: leaves)
        let after = nested(board(groupRow: CanvasItemLayout(itemId: groupNode, x: 5, y: -2)), pages: leaves)
        let delta = try frameOf(after).position - frameOf(before).position
        #expect(delta.x == 5 && delta.y == -2)
        for (old, new) in zip(pagePlaceables(before), pagePlaceables(after)) {
            let moved = new.position - old.position
            #expect(abs(moved.x - delta.x) < 1e-9 && abs(moved.y - delta.y) < 1e-9)
        }
    }

    @Test("a resized group keeps its size and its pages grow with it")
    func resizedGroupScalesItsPages() throws {
        let leaves = pages(6)
        let small = nested(board(groupRow: CanvasItemLayout(itemId: groupNode, w: 1.0, h: 0.75)), pages: leaves)
        let large = nested(board(groupRow: CanvasItemLayout(itemId: groupNode, w: 4.0, h: 3.0)), pages: leaves)
        #expect(try frameOf(large).size == CGSize(width: 4.0, height: 3.0))
        let smallWidth = try #require(pagePlaceables(small).first?.size?.width)
        let largeWidth = try #require(pagePlaceables(large).first?.size?.width)
        #expect(abs(Double(largeWidth / smallWidth) - 4.0) < 1e-6)
    }

    @Test("a click or drag on a page acts on its group; a loose card is itself")
    func pagesBelongToTheirGroupsCard() {
        let state = nested(board(), pages: pages(3))
        let leaf = SpatialLibraryProjector.nodeId(forDocument: "leaf2")
        #expect(CanvasGroupNesting.owningCardId(of: leaf, in: state) == groupNode)
        let loose = SpatialLibraryProjector.nodeId(forDocument: "loose")
        #expect(CanvasGroupNesting.owningCardId(of: loose, in: state) == loose)
    }

    @Test("an arrangement of the board leaves the pages out: they follow their group")
    func arrangementRowsSkipNestedPages() {
        let state = nested(board(), pages: pages(4))
        let rows = CanvasArrangement.rowsPinning(state.placeables.filter { $0.containerId == nil }, keeping: [])
        #expect(Set(rows.map(\.itemId)) == [groupNode, SpatialLibraryProjector.nodeId(forDocument: "loose")])
    }

    @Test("a group's pages become page nodes in the group's order, with the canvas's own ids")
    func pageNodesFollowTheGroupsOrder() {
        let docs = [
            Document(id: "b", parentId: "g", docType: .file, fileType: .image, name: "leaf 10", sortOrder: 1),
            Document(id: "a", parentId: "g", docType: .file, fileType: .image, name: "leaf 2", sortOrder: 1),
            Document(id: "c", parentId: "g", docType: .file, fileType: .image, name: "leaf 99", sortOrder: 0),
        ]
        let nodes = CanvasGroupNesting.pageNodes(docs)
        #expect(nodes.map(\.id) == ["doc:c", "doc:a", "doc:b"])
        #expect(nodes.map(\.sourceId) == ["c", "a", "b"])
        #expect(CanvasGroupNesting.groupNodeIds(in: docs + [Document(id: "g", docType: .group, name: "G")]) == ["doc:g"])
    }

    @Test("nesting is stable: the same inputs give the same board, so a reconcile emits no ops")
    func nestingIsStable() {
        let leaves = pages(8)
        let first = nested(board(), pages: leaves)
        let second = nested(board(), pages: leaves)
        #expect(CanvasSceneDiff.compute(from: first, to: second).isEmpty)
    }
}
