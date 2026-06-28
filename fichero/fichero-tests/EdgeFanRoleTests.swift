@testable import Fichero
import Foundation
import XCTest

/// Tests for EdgeFanRole + EdgeFanRoleResolver — the workflow-edge fan badge
/// logic (#1993 Views). Locks the resolver priority (a fan-in target wins over a
/// fan-out source) and the label formatting incl. the nil-count fallbacks.
final class EdgeFanRoleTests: XCTestCase {

    // MARK: - EdgeFanRole.label

    func testFanOutLabel() {
        XCTAssertEqual(EdgeFanRole.fanOut.label(count: 3), "→ 3 files")
        XCTAssertEqual(EdgeFanRole.fanOut.label(count: nil), "fan-out")
    }

    func testFanInLabel() {
        XCTAssertEqual(EdgeFanRole.fanIn.label(count: 5), "∑ 5 files")
        XCTAssertEqual(EdgeFanRole.fanIn.label(count: nil), "merge")
    }

    func testNoneLabelIsEmptyRegardlessOfCount() {
        XCTAssertEqual(EdgeFanRole.none.label(count: 9), "")
        XCTAssertEqual(EdgeFanRole.none.label(count: nil), "")
    }

    // MARK: - EdgeFanRoleResolver.role

    func testFanOutSourceProducesFanOut() {
        // "transcribe" is a per-file fan-out tool.
        XCTAssertEqual(EdgeFanRoleResolver.role(sourceTool: "transcribe", targetTool: nil), .fanOut)
    }

    func testFanInTargetProducesFanIn() {
        // "aggregate" collapses many inputs into one.
        XCTAssertEqual(EdgeFanRoleResolver.role(sourceTool: nil, targetTool: "aggregate"), .fanIn)
    }

    func testFanInTargetTakesPriorityOverFanOutSource() {
        // Both sides classified: the fan-in target must win.
        XCTAssertEqual(
            EdgeFanRoleResolver.role(sourceTool: "transcribe", targetTool: "aggregate"),
            .fanIn
        )
    }

    func testUnknownOrNilToolsAreNone() {
        XCTAssertEqual(EdgeFanRoleResolver.role(sourceTool: "mystery", targetTool: "unknown"), .none)
        XCTAssertEqual(EdgeFanRoleResolver.role(sourceTool: nil, targetTool: nil), .none)
    }
}
