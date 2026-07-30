import SwiftUI

// MARK: - Fan role classification
//
// The backend's LangGraph builder runs implicit fan-out/fan-in around
// per-file tools: Transcribe runs N times in parallel, Catalogue collects
// the N results before running once. That structure is invisible in a
// linear `Files → Transcribe → Catalogue` canvas, which is exactly the
// confusion the user reported. These role annotations let us render a
// badge on the edge so the user can SEE when files fan out and when
// they merge back.
//
// Roles are DERIVED from registry metadata (#4322) — the source port's
// cardinality (a `files`/`array` payload is plural) and each tool's
// `supports_batch` capability — not from hardcoded tool-name allowlists,
// which omitted `zoom` (the real 1→N step) and decorated transcribe's
// outgoing edges spuriously.

enum EdgeFanRole: Equatable {
    case fanOut
    case fanIn
    case none

    func label(count: Int?) -> String {
        switch self {
        case .fanOut: return count.map { "→ \($0) files" } ?? "fan-out"
        case .fanIn:  return count.map { "∑ \($0) files" } ?? "merge"
        case .none:   return ""
        }
    }
}

enum EdgeFanRoleResolver {
    /// Data types that carry MANY items across one edge.
    private static let pluralDataTypes: Set<String> = ["files", "array"]
    /// Data types that carry ONE item across one edge. `any` is excluded:
    /// unknown cardinality must not fabricate a badge.
    private static let singularDataTypes: Set<String> = [
        "file", "text", "json", "image", "number", "boolean"
    ]

    /// Classify an edge from registry metadata:
    /// - fan-out: the edge carries a plural payload into a tool that
    ///   processes items in parallel (`supports_batch`) — e.g. files → zoom,
    ///   zoom → transcribe.
    /// - fan-in: a batch tool's per-item results collapse through a singular
    ///   payload into the next step — e.g. transcribe → catalogue.
    static func role(
        sourcePortDataType: String?,
        sourceSupportsBatch: Bool,
        targetSupportsBatch: Bool
    ) -> EdgeFanRole {
        guard let dataType = sourcePortDataType?.lowercased() else { return .none }
        if pluralDataTypes.contains(dataType) && targetSupportsBatch {
            return .fanOut
        }
        if sourceSupportsBatch && singularDataTypes.contains(dataType) {
            return .fanIn
        }
        return .none
    }

    /// Resolve an edge's source-port data type from the source node's output
    /// ports. Edges stored with the backend default port id `output` fall
    /// back to the node's first output port (mirrors the geometry fallback
    /// in `calculatePortPositions`).
    static func sourcePortDataType(edge: WorkflowEdge, sourceNode: WorkflowNode?) -> String? {
        guard let node = sourceNode else { return nil }
        if let port = node.outputPorts.first(where: { $0.id == edge.sourcePortId }) {
            return port.dataType
        }
        if edge.sourcePortId == "output" {
            return node.outputPorts.first?.dataType
        }
        return nil
    }

    /// Convenience: classify an edge given both endpoint nodes and the tool
    /// registry (keyed by lowercased tool name, as in WorkflowStore).
    static func role(
        edge: WorkflowEdge,
        sourceNode: WorkflowNode?,
        targetNode: WorkflowNode?,
        toolRegistry: [String: ToolInfo]
    ) -> EdgeFanRole {
        let sourceInfo = sourceNode.flatMap { toolRegistry[$0.tool.lowercased()] }
        let targetInfo = targetNode.flatMap { toolRegistry[$0.tool.lowercased()] }
        return role(
            sourcePortDataType: sourcePortDataType(edge: edge, sourceNode: sourceNode),
            sourceSupportsBatch: sourceInfo?.supportsBatch ?? false,
            targetSupportsBatch: targetInfo?.supportsBatch ?? false
        )
    }
}
