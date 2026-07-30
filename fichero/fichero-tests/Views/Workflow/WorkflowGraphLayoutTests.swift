@testable import Fichero
import Foundation
import XCTest

/// Pure graph-layout logic (#4322/#4323): topological step numbering shared
/// by list view + canvas badges, the Tidy layered layout, and add-node
/// placement.
final class WorkflowGraphLayoutTests: XCTestCase {

    private func node(_ id: String, x: Double, y: Double, tool: String = "transcribe") -> WorkflowNode {
        WorkflowNode(id: id, tool: tool, positionX: x, positionY: y)
    }

    private func edge(_ source: String, _ target: String) -> WorkflowEdge {
        WorkflowEdge(sourceNodeId: source, targetNodeId: target)
    }

    // MARK: - Step numbers

    func testLinearChainNumbersInExecutionOrder() {
        // Visual positions deliberately reversed — execution order must win.
        let nodes = [node("c", x: 0, y: 0), node("a", x: 900, y: 0), node("b", x: 400, y: 0)]
        let edges = [edge("a", "b"), edge("b", "c")]
        let steps = WorkflowTopology.stepNumbers(nodes: nodes, edges: edges)
        XCTAssertEqual(steps, ["a": 1, "b": 2, "c": 3])
    }

    func testDiamondBreaksTiesByCanvasPosition() {
        let nodes = [
            node("root", x: 0, y: 0),
            node("top", x: 200, y: 0),
            node("bottom", x: 200, y: 200),
            node("sink", x: 400, y: 100)
        ]
        let edges = [edge("root", "top"), edge("root", "bottom"), edge("top", "sink"), edge("bottom", "sink")]
        let steps = WorkflowTopology.stepNumbers(nodes: nodes, edges: edges)
        XCTAssertEqual(steps["root"], 1)
        XCTAssertEqual(steps["top"], 2)      // same X as bottom, smaller Y
        XCTAssertEqual(steps["bottom"], 3)
        XCTAssertEqual(steps["sink"], 4)
    }

    func testCycleFallsBackToVisualOrder() {
        let nodes = [node("a", x: 100, y: 0), node("b", x: 0, y: 0)]
        let edges = [edge("a", "b"), edge("b", "a")]
        let steps = WorkflowTopology.stepNumbers(nodes: nodes, edges: edges)
        // Visual order: b (x=0) before a (x=100).
        XCTAssertEqual(steps, ["b": 1, "a": 2])
    }

    func testEdgesReferencingMissingNodesAreIgnored() {
        let nodes = [node("a", x: 0, y: 0), node("b", x: 100, y: 0)]
        let edges = [edge("a", "ghost"), edge("ghost", "b"), edge("a", "b")]
        let steps = WorkflowTopology.stepNumbers(nodes: nodes, edges: edges)
        XCTAssertEqual(steps, ["a": 1, "b": 2])
    }

    // MARK: - Tidy layout

    func testTidyLaysChainOutLeftToRight() throws {
        let nodes = [node("a", x: 500, y: 900), node("b", x: 100, y: 100), node("c", x: 300, y: 700)]
        let edges = [edge("a", "b"), edge("b", "c")]
        let positions = WorkflowTidyLayout.positions(nodes: nodes, edges: edges)

        let ax = try XCTUnwrap(positions["a"]).x
        let bx = try XCTUnwrap(positions["b"]).x
        let cx = try XCTUnwrap(positions["c"]).x
        XCTAssertLessThan(ax, bx)
        XCTAssertLessThan(bx, cx)
        // A pure chain shares one row.
        XCTAssertEqual(positions["a"]?.y, positions["b"]?.y)
        XCTAssertEqual(positions["b"]?.y, positions["c"]?.y)
    }

    func testTidyStacksBranchesVerticallyInOneColumn() throws {
        // files → (transcribe, describe) → catalogue: the two branches share
        // a column and must not overlap.
        let nodes = [
            node("files", x: 0, y: 0),
            node("t", x: 10, y: 10),
            node("d", x: 20, y: 20),
            node("cat", x: 30, y: 30)
        ]
        let edges = [edge("files", "t"), edge("files", "d"), edge("t", "cat"), edge("d", "cat")]
        let positions = WorkflowTidyLayout.positions(nodes: nodes, edges: edges)

        XCTAssertEqual(positions["t"]?.x, positions["d"]?.x)
        XCTAssertNotEqual(positions["t"]?.y, positions["d"]?.y)
        // Sink lands one column right of the deepest branch.
        XCTAssertGreaterThan(try XCTUnwrap(positions["cat"]).x, try XCTUnwrap(positions["t"]).x)
    }

    func testTidyUsesLongestPathDepth() throws {
        // a → b → d and a → d: d must sit one column right of b, not of a.
        let nodes = [node("a", x: 0, y: 0), node("b", x: 1, y: 0), node("d", x: 2, y: 0)]
        let edges = [edge("a", "b"), edge("b", "d"), edge("a", "d")]
        let positions = WorkflowTidyLayout.positions(nodes: nodes, edges: edges)
        XCTAssertGreaterThan(try XCTUnwrap(positions["d"]).x, try XCTUnwrap(positions["b"]).x)
    }

    func testTidyEmptyGraphIsEmpty() {
        XCTAssertTrue(WorkflowTidyLayout.positions(nodes: [], edges: []).isEmpty)
    }

    func testTidyAssignsEveryNodeAPosition() {
        let nodes = (0..<7).map { node("n\($0)", x: Double($0 * 13 % 5), y: Double($0 * 7 % 3)) }
        let edges = [edge("n0", "n1"), edge("n1", "n2"), edge("n0", "n3"), edge("n3", "n2")]
        let positions = WorkflowTidyLayout.positions(nodes: nodes, edges: edges)
        XCTAssertEqual(Set(positions.keys), Set(nodes.map(\.id)))
    }

    // MARK: - Add-node placement

    func testFirstNodeGoesNearCenterLeft() {
        let point = WorkflowNodePlacement.nextNodePosition(nodes: [], edges: [], selectedNodeIds: [])
        XCTAssertEqual(point, CGPoint(x: 150, y: 200))
    }

    func testPlacementAnchorsOnSelectedNode() {
        // Selection on a MIDDLE node of a chain — the old rightmost-X rule
        // would have anchored on "c" instead.
        let nodes = [node("a", x: 100, y: 100), node("b", x: 300, y: 100), node("c", x: 900, y: 500)]
        let edges = [edge("a", "b"), edge("b", "c")]
        let point = WorkflowNodePlacement.nextNodePosition(
            nodes: nodes, edges: edges, selectedNodeIds: ["b"]
        )
        XCTAssertEqual(point.x, 300 + 160)
        XCTAssertEqual(point.y, 100)
    }

    func testPlacementWithoutSelectionFollowsExecutionTailNotRightmostX() {
        // "stray" sits far right on an arbitrary branch; the execution tail
        // is "end". New nodes continue the flow after "end".
        let nodes = [node("start", x: 100, y: 100), node("stray", x: 2000, y: 800), node("end", x: 400, y: 100)]
        let edges = [edge("start", "stray"), edge("start", "end"), edge("stray", "end")]
        let point = WorkflowNodePlacement.nextNodePosition(nodes: nodes, edges: edges, selectedNodeIds: [])
        XCTAssertEqual(point.x, 400 + 160)
        XCTAssertEqual(point.y, 100)
    }

    func testPlacementNudgesDownWhenSpotIsOccupied() {
        let nodes = [
            node("a", x: 100, y: 100),
            node("occupier", x: 260, y: 100)  // exactly where a+160 would land
        ]
        let point = WorkflowNodePlacement.nextNodePosition(
            nodes: nodes, edges: [], selectedNodeIds: ["a"]
        )
        XCTAssertEqual(point.x, 260)
        XCTAssertGreaterThan(point.y, 100)
    }
}
