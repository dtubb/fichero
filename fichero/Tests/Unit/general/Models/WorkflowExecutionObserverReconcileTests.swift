@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// #4346/#4349 — the launchers' wait loops watched only for a terminal SSE
/// frame or the reducer's `isRunning` flip; a stream that died without a
/// terminal frame hung them (and every spinner) forever. `waitForTerminal`
/// is the shared replacement: it settles on event, reducer flip, untracked
/// execution, or (after ~5s without a live stream) the persisted run record.
@MainActor
final class WorkflowExecutionObserverReconcileTests: XCTestCase {

    private func makeStream() -> WorkflowStreamService {
        WorkflowStreamService(ficheroClient: FicheroClient())
    }

    func testReturnsWhenExecutionIsNoLongerTracked() async {
        let observer = WorkflowExecutionObserver()
        let done = await observer.waitForTerminal(
            stream: makeStream(),
            threadId: { "thread-gone" },
            streamCompleted: { false }
        )
        XCTAssertTrue(done, "an untracked execution has already settled — the wait must end")
    }

    func testReturnsImmediatelyWhenStreamAlreadyCompleted() async {
        let observer = WorkflowExecutionObserver()
        observer.startExecution(workflowId: "wf", name: "WF", threadId: "t1")
        let done = await observer.waitForTerminal(
            stream: makeStream(),
            threadId: { "t1" },
            streamCompleted: { true }
        )
        XCTAssertTrue(done)
    }

    func testReturnsWhenReducerFlipsIsRunning() async {
        let observer = WorkflowExecutionObserver()
        observer.startExecution(workflowId: "wf", name: "WF", threadId: "t1")

        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(300))
            observer.handleEvent(.cancelled(threadId: "t1"), forThreadId: "t1")
        }
        let done = await observer.waitForTerminal(
            stream: makeStream(),
            threadId: { "t1" },
            streamCompleted: { false }
        )
        XCTAssertTrue(done)
        XCTAssertEqual(observer.activeExecutions["t1"]?.status, .cancelled)
        XCTAssertEqual(observer.activeExecutions["t1"]?.isRunning, false)
    }

    func testHasRunningExecutionTracksTerminalTransitions() {
        let observer = WorkflowExecutionObserver()
        XCTAssertFalse(observer.hasRunningExecution)

        observer.startExecution(workflowId: "wf", name: "WF", threadId: "t1")
        observer.startExecution(workflowId: "wf2", name: "WF2", threadId: "t2")
        XCTAssertTrue(observer.hasRunningExecution)

        observer.endExecution(threadId: "t1", status: .completed)
        XCTAssertTrue(observer.hasRunningExecution, "t2 is still live")

        observer.endExecution(threadId: "t2", status: .cancelled)
        XCTAssertFalse(observer.hasRunningExecution)
    }
}
