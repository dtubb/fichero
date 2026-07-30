import CoreGraphics
import Foundation

// MARK: - Run trace model (#4320)
//
// A read-only "what actually happened" graph for one workflow run, built
// entirely from data the server already persists on the run record:
// - topology + effective per-node provider/model from `workflow_snapshot`
//   (#4314 persists the FULL node shape, run-level overrides applied),
// - per-node timing/status from `progress_timeline` (flushed per node),
// - step → artifact links from the run's artifact provenance (#4313).
//
// Everything here is pure so status mapping and layout are unit-testable
// without a view or a server.

/// Executed status of one node in a finished (or in-flight) run.
enum RunTraceNodeStatus: Equatable {
    /// Never reached (run failed/cancelled upstream, or still queued).
    case pending
    case running
    case success
    case failed
    case skipped
}

/// One node of the trace graph: the snapshot node joined with its timeline
/// outcome and any file-level errors recorded under it.
struct RunTraceNode: Identifiable, Equatable {
    let id: String
    let label: String
    let tool: String
    /// Provider/model actually used (effective values from the snapshot);
    /// empty strings normalize to nil.
    let provider: String?
    let model: String?
    let status: RunTraceNodeStatus
    let durationMs: Double?
    /// Error detail for a failed node — the node's file-level errors, or the
    /// run-level error when the failure aborted the run at this node.
    let error: String?
    let skipReason: String?

    // NOTE (#4343 seam): per-step tokens/cost is not in the timeline yet.
    // When the runner drains the `_record_usage` collector into per-node
    // timeline entries, surface it here as `costText` and render it beside
    // the duration in `RunTraceNodeDetail`.

    var providerModelText: String? {
        let parts = [provider, model].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// A directed edge between two trace nodes (snapshot edge).
struct RunTraceEdge: Hashable {
    let source: String
    let target: String
}

/// The full trace graph for one run.
struct RunTraceGraph: Equatable {
    let nodes: [RunTraceNode]
    let edges: [RunTraceEdge]

    func node(withId id: String) -> RunTraceNode? {
        nodes.first { $0.id == id }
    }
}

enum RunTraceModelBuilder {
    /// Build the trace graph from a fetched run. Returns nil when the run
    /// has no snapshot (pre-snapshot legacy runs).
    static func graph(from run: WorkflowRunResponse) -> RunTraceGraph? {
        guard let snapshot = run.workflowSnapshot else { return nil }
        return graph(
            snapshot: snapshot,
            timeline: run.progressTimeline,
            nodeNameMap: run.nodeNameMap,
            runStatus: run.status,
            runError: run.error
        )
    }

    /// Pure core: join snapshot topology with timeline outcomes.
    static func graph(
        snapshot: [String: Any],
        timeline: [String: Any]?,
        nodeNameMap: [String: String]?,
        runStatus: String,
        runError: String?
    ) -> RunTraceGraph? {
        guard let rawNodes = snapshot["nodes"] as? [[String: Any]], !rawNodes.isEmpty else {
            return nil
        }
        let rawEdges = snapshot["edges"] as? [[String: Any]] ?? []
        let steps = timeline?["steps"] as? [[String: Any]] ?? []

        // Last NODE-level timeline entry per node id (later entries win — a
        // retried node reports its final outcome).
        var nodeSteps: [String: [String: Any]] = [:]
        // File-level errors per node id, in order.
        var fileErrors: [String: [String]] = [:]
        for step in steps {
            guard let nodeId = step["node_id"] as? String, !nodeId.isEmpty else { continue }
            if step["type"] as? String == "file" {
                if step["status"] as? String == "error",
                   let message = step["error"] as? String, !message.isEmpty {
                    fileErrors[nodeId, default: []].append(message)
                }
            } else {
                nodeSteps[nodeId] = step
            }
        }

        let runFailed = ["failed", "error"].contains(runStatus.lowercased())
        let runTerminal = !["running", "paused", "accepted"].contains(runStatus.lowercased())

        var nodes: [RunTraceNode] = []
        for raw in rawNodes {
            guard let id = raw["id"] as? String, !id.isEmpty else { continue }
            let label = normalized(nodeNameMap?[id])
                ?? normalized(raw["label"] as? String)
                ?? normalized(raw["tool"] as? String)
                ?? id
            let step = nodeSteps[id]
            let status = nodeStatus(
                stepStatus: step?["status"] as? String,
                runFailed: runFailed,
                runTerminal: runTerminal
            )
            nodes.append(
                RunTraceNode(
                    id: id,
                    label: label,
                    tool: (raw["tool"] as? String) ?? "unknown",
                    provider: normalized(raw["provider_name"] as? String),
                    model: normalized(raw["model_name"] as? String),
                    status: status,
                    durationMs: doubleValue(step?["duration_ms"]),
                    error: errorText(
                        for: id,
                        status: status,
                        fileErrors: fileErrors,
                        runError: runError
                    ),
                    skipReason: normalized(step?["skip_reason"] as? String)
                )
            )
        }

        let nodeIds = Set(nodes.map(\.id))
        let edges: [RunTraceEdge] = rawEdges.compactMap { raw in
            guard let source = raw["source"] as? String,
                  let target = raw["target"] as? String,
                  nodeIds.contains(source), nodeIds.contains(target) else { return nil }
            return RunTraceEdge(source: source, target: target)
        }

        return RunTraceGraph(nodes: nodes, edges: edges)
    }

    /// Map one node's last timeline status into an executed status, folding in
    /// the run outcome: a node still marked "running" in a failed run is the
    /// failing node; in any other terminal run it never completed (pending —
    /// e.g. killed mid-flight, timeline flushed at the previous boundary).
    static func nodeStatus(
        stepStatus: String?,
        runFailed: Bool,
        runTerminal: Bool
    ) -> RunTraceNodeStatus {
        switch stepStatus {
        case "success":
            return .success
        case "error":
            return .failed
        case "skipped":
            return .skipped
        case "running":
            if runFailed { return .failed }
            return runTerminal ? .pending : .running
        default:
            return .pending
        }
    }

    private static func errorText(
        for nodeId: String,
        status: RunTraceNodeStatus,
        fileErrors: [String: [String]],
        runError: String?
    ) -> String? {
        guard status == .failed else { return nil }
        if let errors = fileErrors[nodeId], !errors.isEmpty {
            let extra = errors.count - 1
            return extra > 0 ? "\(errors[0])\n(+\(extra) more file errors)" : errors[0]
        }
        return normalized(runError)
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func doubleValue(_ value: Any?) -> Double? {
        if let double = value as? Double { return double }
        if let int = value as? Int { return Double(int) }
        if let number = value as? NSNumber { return number.doubleValue }
        return nil
    }
}

// MARK: - Layout

/// Node positions (centers) plus the canvas extent that contains them.
struct RunTraceLayout: Equatable {
    let positions: [String: CGPoint]
    let size: CGSize
}

/// Deterministic layered DAG layout for the trace canvas. The run snapshot
/// carries no editor positions, so the trace lays nodes out itself: each
/// node's column is its longest-path depth from the roots; rows within a
/// column keep snapshot order. Pure + static so it is unit-testable (#4320).
enum RunTraceLayoutEngine {
    static func layout(
        nodes: [RunTraceNode],
        edges: [RunTraceEdge],
        nodeSize: CGSize = CGSize(width: 160, height: 88),
        horizontalGap: CGFloat = 72,
        verticalGap: CGFloat = 28,
        margin: CGFloat = 32
    ) -> RunTraceLayout {
        guard !nodes.isEmpty else {
            return RunTraceLayout(positions: [:], size: CGSize(width: 0, height: 0))
        }

        let depths = nodeDepths(nodeIds: nodes.map(\.id), edges: edges)
        var columns: [Int: [String]] = [:]
        for node in nodes {
            columns[depths[node.id] ?? 0, default: []].append(node.id)
        }

        var positions: [String: CGPoint] = [:]
        var maxX: CGFloat = 0
        var maxY: CGFloat = 0
        for (depth, ids) in columns {
            let colX = margin + CGFloat(depth) * (nodeSize.width + horizontalGap) + nodeSize.width / 2
            for (row, id) in ids.enumerated() {
                let rowY = margin + CGFloat(row) * (nodeSize.height + verticalGap) + nodeSize.height / 2
                positions[id] = CGPoint(x: colX, y: rowY)
                maxX = max(maxX, colX + nodeSize.width / 2)
                maxY = max(maxY, rowY + nodeSize.height / 2)
            }
        }
        return RunTraceLayout(
            positions: positions,
            size: CGSize(width: maxX + margin, height: maxY + margin)
        )
    }

    /// Longest-path depth from the roots for every node. Cycle-safe: the
    /// relaxation is bounded by the node count, so a malformed snapshot with
    /// a cycle terminates with the depths reached so far.
    static func nodeDepths(nodeIds: [String], edges: [RunTraceEdge]) -> [String: Int] {
        var depths: [String: Int] = Dictionary(uniqueKeysWithValues: nodeIds.map { ($0, 0) })
        guard !edges.isEmpty else { return depths }
        for _ in 0..<nodeIds.count {
            var changed = false
            for edge in edges {
                guard let sourceDepth = depths[edge.source],
                      let targetDepth = depths[edge.target] else { continue }
                if targetDepth < sourceDepth + 1 {
                    depths[edge.target] = sourceDepth + 1
                    changed = true
                }
            }
            if !changed { break }
        }
        return depths
    }
}
