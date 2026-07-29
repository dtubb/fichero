@testable import Fichero
import Foundation
import XCTest

/// Tests for WorkflowCanvasView.fittedCanvasSize (#3191) — the canvas grows to
/// fit placed nodes + margin instead of a fixed 2000×1500 wall. Pure geometry;
/// no view.
final class WorkflowCanvasSizeTests: XCTestCase {

    private let nodeSize = CGSize(width: 140, height: 100)

    private func node(posX: Double, posY: Double) -> WorkflowNode {
        WorkflowNode(tool: "t", positionX: posX, positionY: posY)
    }

    /// Empty / small workflows keep the comfortable minimum.
    func testEmptyReturnsMinimum() {
        XCTAssertEqual(WorkflowCanvasView.fittedCanvasSize(for: [], nodeSize: nodeSize),
                       CGSize(width: 2000, height: 1500))
    }

    func testNodesWithinMinimumKeepMinimum() {
        let nodes = [node(posX: 100, posY: 100), node(posX: 500, posY: 400)]
        XCTAssertEqual(WorkflowCanvasView.fittedCanvasSize(for: nodes, nodeSize: nodeSize),
                       CGSize(width: 2000, height: 1500))
    }

    /// A node beyond the minimum grows the canvas to its extent + half node + margin.
    func testGrowsToFitFarNode() {
        let nodes = [node(posX: 3000, posY: 100)]
        let size = WorkflowCanvasView.fittedCanvasSize(for: nodes, nodeSize: nodeSize, margin: 400)
        // 3000 + 140/2 + 400 = 3470
        XCTAssertEqual(size.width, 3470, accuracy: 0.5)
        XCTAssertEqual(size.height, 1500, accuracy: 0.5)  // y within minimum
    }

    func testGrowsBothAxesIndependently() {
        let nodes = [node(posX: 4000, posY: 100), node(posX: 100, posY: 2500)]
        let size = WorkflowCanvasView.fittedCanvasSize(for: nodes, nodeSize: nodeSize, margin: 400)
        XCTAssertEqual(size.width, 4000 + 70 + 400, accuracy: 0.5)   // 4470
        XCTAssertEqual(size.height, 2500 + 50 + 400, accuracy: 0.5)  // 2950
    }

    /// Uses the MAX extent, not the last/first node.
    func testUsesMaxExtent() {
        let nodes = [node(posX: 5000, posY: 5000), node(posX: 100, posY: 100)]
        let size = WorkflowCanvasView.fittedCanvasSize(for: nodes, nodeSize: nodeSize, margin: 400)
        XCTAssertEqual(size.width, 5000 + 70 + 400, accuracy: 0.5)
        XCTAssertEqual(size.height, 5000 + 50 + 400, accuracy: 0.5)
    }
}
