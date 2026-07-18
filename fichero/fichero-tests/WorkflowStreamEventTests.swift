@testable import Fichero
import XCTest

final class WorkflowStreamEventTests: XCTestCase {
    func testEqualityUsesStableEventIdentity() {
        let first = WorkflowStreamEvent.nodeBegin(threadId: "t-1", nodeId: "n-1", nodeName: "Load")
        let sameIdentity = WorkflowStreamEvent.nodeBegin(threadId: "t-1", nodeId: "n-1", nodeName: "Renamed")
        let otherNode = WorkflowStreamEvent.nodeBegin(threadId: "t-1", nodeId: "n-2", nodeName: "Load")

        XCTAssertEqual(first, sameIdentity)
        XCTAssertNotEqual(first, otherNode)
        XCTAssertNotEqual(first, .complete(threadId: "t-1", checkpointId: nil, finalState: nil))
    }
}
