@testable import Fichero
import XCTest

/// The workflow inspector's Run and Chain tabs.
/// spec: workflows `workflows.inspector.run-rows-are-runs`.
final class WorkflowInspectorListsTests: XCTestCase {

    private func inspectorSource() throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Inspector/WorkflowInspector.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// `WorkflowExecution.id` is the WORKFLOW's id, so every run of the
    /// workflow this tab lists has the same one. The rows are keyed by the
    /// run's thread.
    @MainActor
    func testTwoRunsOfOneWorkflowShareAnIdAndDifferByThread() {
        let observer = WorkflowExecutionObserver()
        observer.startExecution(workflowId: "wf", name: "Transcribe", threadId: "thread-1")
        observer.startExecution(workflowId: "wf", name: "Transcribe", threadId: "thread-2")

        let runs = Array(observer.activeExecutions.values)

        XCTAssertEqual(runs.map(\.id), ["wf", "wf"])
        XCTAssertEqual(Set(runs.map(\.threadId)), ["thread-1", "thread-2"])
    }

    func testTheRunTabKeysItsRowsByThread() throws {
        let source = try inspectorSource()
        XCTAssertTrue(source.contains(#"List(workflowRuns, id: \.threadId)"#))
        XCTAssertFalse(source.contains("List(workflowRuns) {"))
    }
}
