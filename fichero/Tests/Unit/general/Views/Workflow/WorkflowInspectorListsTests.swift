@testable import Fichero
import XCTest

/// The rows of the workflow inspector's Run and Chain tabs.
/// spec: workflows `workflows.inspector.run-rows-are-runs`,
/// `workflows.inspector.chain-in-execution-order`.
final class WorkflowInspectorListsTests: XCTestCase {

    /// `WorkflowExecution.id` is the WORKFLOW's id, so two runs of one
    /// workflow share it. The tab's rows are told apart by the run's thread.
    @MainActor
    func testEachRunOfTheWorkflowIsItsOwnRow() {
        let observer = WorkflowExecutionObserver()
        observer.startExecution(workflowId: "wf", name: "Transcribe", threadId: "thread-1")
        observer.startExecution(workflowId: "wf", name: "Transcribe", threadId: "thread-2")
        observer.startExecution(workflowId: "other", name: "Translate", threadId: "thread-3")
        let executions = Array(observer.activeExecutions.values)

        let rows = WorkflowInspectorLists.runRows(of: "wf", among: executions)

        XCTAssertEqual(rows.map(\.run.id), ["wf", "wf"])
        XCTAssertEqual(Set(rows.map(\.id)), ["thread-1", "thread-2"])
    }

    /// The Chain tab numbers the steps as the canvas badges do: by execution
    /// order, not by the order the nodes are stored in.
    func testTheChainListsStepsInExecutionOrder() {
        let workflow = Workflow(
            name: "w",
            nodes: [
                WorkflowNode(id: "c", tool: "catalogue", positionX: 0, positionY: 0),
                WorkflowNode(id: "a", tool: "files", positionX: 900, positionY: 0),
                WorkflowNode(id: "b", tool: "transcribe", positionX: 400, positionY: 0)
            ],
            edges: [
                WorkflowEdge(sourceNodeId: "a", targetNodeId: "b"),
                WorkflowEdge(sourceNodeId: "b", targetNodeId: "c")
            ]
        )

        XCTAssertEqual(WorkflowInspectorLists.chainSteps(of: workflow).map(\.id), ["a", "b", "c"])
    }
}
