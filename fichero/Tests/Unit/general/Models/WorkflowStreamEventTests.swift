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

    func testTerminalEventsIncludeCancellationButNotPause() {
        XCTAssertTrue(WorkflowStreamEvent.complete(threadId: "t", checkpointId: nil, finalState: nil).isTerminal)
        XCTAssertTrue(WorkflowStreamEvent.cancelled(threadId: "t").isTerminal)
        XCTAssertTrue(WorkflowStreamEvent.error(threadId: "t", error: "failed").isTerminal)
        XCTAssertTrue(WorkflowStreamEvent.systemicError(
            threadId: "t",
            error: "failed",
            errorCount: 1,
            totalCount: 1
        ).isTerminal)
        XCTAssertFalse(WorkflowStreamEvent.pause(threadId: "t", checkpointId: nil, currentState: nil).isTerminal)
    }
}
