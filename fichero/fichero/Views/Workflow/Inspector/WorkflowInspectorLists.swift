import Foundation

/// The rows of the workflow inspector's Chain and Run tabs.
enum WorkflowInspectorLists {
    /// One row of the Run tab. Its identity is the run's thread:
    /// `WorkflowExecution.id` is the workflow's id, the same for every run
    /// the tab lists.
    struct RunRow: Identifiable {
        let run: WorkflowExecution

        var id: String { run.threadId }
    }

    /// The Chain tab's steps, in execution order: the order the canvas badges
    /// and the editor's list number them in.
    static func chainSteps(of workflow: Workflow) -> [WorkflowNode] {
        WorkflowTopology.orderedNodes(nodes: workflow.nodes, edges: workflow.edges)
    }

    /// The Run tab's rows: the runs of one workflow, newest first.
    static func runRows(of workflowId: String, among executions: [WorkflowExecution]) -> [RunRow] {
        executions
            .filter { $0.id == workflowId }
            .sorted { $0.startTime > $1.startTime }
            .map(RunRow.init)
    }
}
