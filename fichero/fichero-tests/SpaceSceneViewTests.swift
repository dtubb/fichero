@testable import Fichero
import XCTest

/// Unit tests for the restored RealityKit 3D renderer, `SpaceSceneView` (#3088,
/// renamed from `SpatialScene3D`). The drag-end snap math is pure (no
/// RealityKit) so it is exercised directly here.
final class SpaceSceneViewTests: XCTestCase {

    func testPersistedDragEndPositionPrefersTrackedDragPosition() {
        let originalNode = SpatialNode(
            id: "node-1",
            roomId: "room-1",
            nodeType: .source,
            label: "Dragged",
            positionX: 0,
            positionY: 0,
            positionZ: 0
        )

        let position = SpaceSceneView.persistedDragEndPosition(
            nodeId: originalNode.id,
            dragPositions: [originalNode.id: SIMD3<Double>(1.13, -0.37, 0.12)],
            nodes: [originalNode]
        )

        XCTAssertEqual(position?.x, 1.25)
        XCTAssertEqual(position?.y, -0.25)
        XCTAssertEqual(position?.z, 0.0)
    }

    func testPersistedDragEndPositionFallsBackToNodeSnapshot() {
        let node = SpatialNode(
            id: "node-1",
            roomId: "room-1",
            nodeType: .source,
            label: "Dragged",
            positionX: 0.62,
            positionY: -0.62,
            positionZ: 0.13
        )

        let position = SpaceSceneView.persistedDragEndPosition(
            nodeId: node.id,
            dragPositions: [:],
            nodes: [node]
        )

        XCTAssertEqual(position?.x, 0.5)
        XCTAssertEqual(position?.y, -0.5)
        XCTAssertEqual(position?.z, 0.25)
    }

    /// An unknown node with no tracked drag position has nothing to persist —
    /// guards the `.onDisappear` flush from writing a phantom row.
    func testPersistedDragEndPositionUnknownNodeIsNil() {
        let position = SpaceSceneView.persistedDragEndPosition(
            nodeId: "missing",
            dragPositions: [:],
            nodes: []
        )
        XCTAssertNil(position)
    }
}
