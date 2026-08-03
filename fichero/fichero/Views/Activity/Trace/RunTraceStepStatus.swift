import Foundation

// MARK: - Step records → trace status (#4284)
//
// The progress timeline can only speak about steps that emitted an entry, so
// a node missing from it is ambiguous: never started, or ran and said
// nothing? The typed step records answer that directly — the server emits one
// record per PLANNED step — so where a record exists it overrides whatever
// the timeline implied.
//
// Kept out of the view so the mapping is testable without a server or a
// SwiftUI host.

extension RunTraceModelBuilder {

    /// Overlay the run's step records onto a timeline-derived graph.
    ///
    /// Only nodes with a matching record are rewritten; legacy runs carry no
    /// records and pass through untouched. Timeline-derived `error` is kept
    /// when the record has none, because file-level failure detail lives in
    /// the timeline and not on the step.
    static func applying(
        steps: [WorkflowRunStep],
        to graph: RunTraceGraph
    ) -> RunTraceGraph {
        guard !steps.isEmpty else { return graph }
        let byNodeId = Dictionary(steps.map { ($0.nodeId, $0) }) { _, last in last }

        let nodes = graph.nodes.map { node -> RunTraceNode in
            guard let step = byNodeId[node.id] else { return node }
            return RunTraceNode(
                id: node.id,
                label: node.label,
                tool: node.tool,
                provider: node.provider,
                model: node.model,
                status: stepStatus(
                    status: step.status,
                    producedNothing: step.didProduceNothing
                ),
                durationMs: step.durationMs ?? node.durationMs,
                error: step.error ?? node.error,
                skipReason: step.skipReason ?? node.skipReason
            )
        }
        return RunTraceGraph(nodes: nodes, edges: graph.edges)
    }

    /// Map one step record onto a renderable status.
    ///
    /// `completed` splits on `producedNothing`: the same status string means
    /// two different things to the reader, and only the flag separates
    /// "here is your output" from "this ran and found nothing".
    ///
    /// An unrecognised status maps to `pending` — the state that claims the
    /// least. A status added server-side will read as "not reported" rather
    /// than borrowing the appearance of success or failure.
    static func stepStatus(status: String, producedNothing: Bool) -> RunTraceNodeStatus {
        switch status {
        case "completed", "success":
            return producedNothing ? .producedNothing : .success
        case "failed", "error":
            return .failed
        case "cancelled":
            return .cancelled
        case "skipped":
            return .skipped
        case "running":
            return .running
        case "not_run":
            return .pending
        default:
            return .pending
        }
    }
}
