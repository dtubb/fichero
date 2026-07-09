@testable import Fichero
import XCTest

@MainActor
final class ActivityWindowSelectionStateTests: XCTestCase {
    func testSelectReplacesSharedSelection() {
        let state = ActivityWindowSelectionState()
        let run = SelectedActivityRun(
            id: "run-1",
            name: "Workflow",
            workflowId: "wf-1",
            threadId: "thread-1",
            timestamp: Date(timeIntervalSince1970: 1_700_000_000),
            status: .running,
            isLive: true
        )

        state.select(run)

        XCTAssertEqual(state.selectedRun?.id, "run-1")
        XCTAssertEqual(state.selectedRun?.threadId, "thread-1")
    }

    func testSelectCanClearSelection() {
        let state = ActivityWindowSelectionState()
        state.select(SelectedActivityRun(
            id: "run-1",
            name: "Workflow",
            workflowId: "wf-1",
            threadId: "thread-1",
            timestamp: Date(timeIntervalSince1970: 1_700_000_000),
            status: .running,
            isLive: true
        ))

        state.select(nil)

        XCTAssertNil(state.selectedRun)
    }
}
