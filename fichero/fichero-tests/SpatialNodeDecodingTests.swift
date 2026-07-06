@testable import Fichero
import XCTest

/// Tests for the SpatialModels struct decoders + SpatialNode pure helpers.
/// SpatialNodeTypeTests covers the node-kind enum and CanvasSceneContractTests
/// covers SpatialConnection, but SpatialNode / SpatialStack / SpatialViewport
/// tolerant decoders and the snap/thumbnail/displayLabel helpers were untested.
/// All headless value logic (thumbnailUrl's MainActor variant is excluded; the
/// pure static thumbnailURL is tested instead).
final class SpatialNodeDecodingTests: XCTestCase {

    // MARK: - SpatialNode.init(from:) tolerant decode

    func testNodeDecodesFullPayload() throws {
        let json = Data("""
        {
            "id": "n-1", "roomId": "r-1", "nodeType": "claim",
            "sourceId": "doc-9", "label": "A claim",
            "positionX": 1.5, "positionY": 2.5, "positionZ": 3.5,
            "rotationX": 0.1, "rotationY": 0.2, "rotationZ": 0.3, "scale": 2.0
        }
        """.utf8)
        let node = try JSONDecoder().decode(SpatialNode.self, from: json)
        XCTAssertEqual(node.id, "n-1")
        XCTAssertEqual(node.roomId, "r-1")
        XCTAssertEqual(node.nodeType, .claim)
        XCTAssertEqual(node.sourceId, "doc-9")
        XCTAssertEqual(node.label, "A claim")
        XCTAssertEqual(node.positionZ, 3.5)
        XCTAssertEqual(node.scale, 2.0)
    }

    /// Missing scalars degrade to their defaults (0 / scale 1) and a missing id
    /// gets a generated UUID — one malformed row can't drop the scene.
    func testNodeToleratesMissingScalars() throws {
        let json = Data("""
        { "roomId": "r-1", "nodeType": "source" }
        """.utf8)
        let node = try JSONDecoder().decode(SpatialNode.self, from: json)
        XCTAssertFalse(node.id.isEmpty)          // generated UUID
        XCTAssertNil(node.sourceId)
        XCTAssertEqual(node.label, "")
        XCTAssertEqual(node.positionX, 0)
        XCTAssertEqual(node.positionY, 0)
        XCTAssertEqual(node.positionZ, 0)
        XCTAssertEqual(node.scale, 1)            // scale defaults to 1, not 0
    }

    /// nodeType and roomId are the hard-required fields — a missing nodeType
    /// throws (the tolerance boundary).
    func testNodeMissingNodeTypeThrows() {
        let json = Data("""
        { "roomId": "r-1" }
        """.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(SpatialNode.self, from: json))
    }

    // MARK: - SpatialNode helpers

    func testDisplayLabelFallsBackToNodeTypeLabel() {
        let unlabeled = SpatialNode(roomId: "r", nodeType: .claim, label: "",
                                    positionX: 0, positionY: 0)
        XCTAssertEqual(unlabeled.displayLabel, "Claim")   // nodeType.label
        let labeled = SpatialNode(roomId: "r", nodeType: .claim, label: "Mine",
                                  positionX: 0, positionY: 0)
        XCTAssertEqual(labeled.displayLabel, "Mine")
    }

    func testSnapRoundsToGrid() {
        XCTAssertEqual(SpatialNode.snap(1.1, to: 0.25), 1.0, accuracy: 1e-9)
        XCTAssertEqual(SpatialNode.snap(0.13, to: 0.25), 0.25, accuracy: 1e-9)
        XCTAssertEqual(SpatialNode.snap(-0.13, to: 0.25), -0.25, accuracy: 1e-9)
        // Non-positive grid is a no-op (guards against NaN).
        XCTAssertEqual(SpatialNode.snap(3.7, to: 0), 3.7)
        XCTAssertEqual(SpatialNode.snap(3.7, to: -1), 3.7)
    }

    func testSnappedPositionSnapsAllAxes() {
        let node = SpatialNode(roomId: "r", nodeType: .note, label: "x",
                               positionX: 1.1, positionY: 0.13, positionZ: 0.0)
        let snapped = node.snappedPosition(gridSize: 0.25)
        XCTAssertEqual(snapped.x, 1.0, accuracy: 1e-9)
        XCTAssertEqual(snapped.y, 0.25, accuracy: 1e-9)
        XCTAssertEqual(snapped.z, 0.0, accuracy: 1e-9)
    }

    func testThumbnailURLComposition() {
        let base = URL(string: "https://host.test/api/")!
        let url = SpatialNode.thumbnailURL(forSourceId: "doc-1", baseURL: base)
        XCTAssertEqual(url?.absoluteString, "https://host.test/api/storage/thumbnail/doc-1")
        // Guards: empty source or nil base → nil.
        XCTAssertNil(SpatialNode.thumbnailURL(forSourceId: "", baseURL: base))
        XCTAssertNil(SpatialNode.thumbnailURL(forSourceId: "doc-1", baseURL: nil))
    }

    // MARK: - SpatialStack.init(from:)

    func testStackToleratesMissingIdAndNodeIds() throws {
        let json = Data("""
        { "roomId": "r-1" }
        """.utf8)
        let stack = try JSONDecoder().decode(SpatialStack.self, from: json)
        XCTAssertFalse(stack.id.isEmpty)   // generated UUID
        XCTAssertEqual(stack.roomId, "r-1")
        XCTAssertNil(stack.name)
        XCTAssertEqual(stack.nodeIds, [])  // absent → []
    }

    // MARK: - SpatialViewport.init(from:) camera defaults

    func testViewportAppliesCameraDefaults() throws {
        let json = Data("""
        { "roomId": "r-1" }
        """.utf8)
        let viewport = try JSONDecoder().decode(SpatialViewport.self, from: json)
        XCTAssertEqual(viewport.roomId, "r-1")
        XCTAssertEqual(viewport.cameraX, 0)
        XCTAssertEqual(viewport.cameraY, 0)
        XCTAssertEqual(viewport.cameraZ, 10)     // default pulls the camera back
        XCTAssertEqual(viewport.zoomLevel, 1)
        XCTAssertNil(viewport.focusNodeId)
        XCTAssertNil(viewport.bookmarkName)
    }

    // MARK: - SpatialConnectionType tolerant decode

    func testConnectionTypeDecodesKnownAndUnknown() throws {
        XCTAssertEqual(try JSONDecoder().decode(SpatialConnectionType.self,
                                                from: Data("\"user_drawn\"".utf8)), .userDrawn)
        XCTAssertEqual(try JSONDecoder().decode(SpatialConnectionType.self,
                                                from: Data("\"brand_new\"".utf8)), .unknown)
    }
}
