@testable import Fichero
import XCTest

/// The workflow inspector's Run and Chain tabs.
/// spec: workflows `workflows.inspector.run-rows-are-runs`,
/// `workflows.inspector.chain-in-execution-order`.
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

    /// The Chain tab numbers the steps as the canvas badges and the editor's
    /// list do: by `WorkflowTopology`, not by the order the nodes are stored in.
    func testTheChainTabListsStepsInExecutionOrder() throws {
        let source = try inspectorSource()
        XCTAssertTrue(source.contains(
            "let ordered = WorkflowTopology.orderedNodes(nodes: workflow.nodes, edges: workflow.edges)"
        ))
        XCTAssertTrue(source.contains(#"List(Array(ordered.enumerated()), id: \.element.id)"#))
        XCTAssertFalse(source.contains("List(Array(workflow.nodes.enumerated())"))
    }
}
