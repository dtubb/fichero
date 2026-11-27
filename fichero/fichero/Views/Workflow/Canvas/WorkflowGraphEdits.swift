import Foundation

/// Canvas edits that keep a node's input mappings in step with its edges.
///
/// The engine wires a node from its input mappings when it has any, and from
/// its incoming edges only when it has none (`workflows/builder.py`, the
/// auto-wire branch). So an edge removed without its mapping still feeds the
/// node at run, and one mapped edge stops the node's unmapped edges from being
/// wired. Every canvas edit that adds or removes an edge goes through here.
extension Workflow {
    /// The source path an edge from this output port writes into a mapping.
    static func mappingPath(sourceNodeId: String, sourcePortId: String) -> String {
        "$.nodes.\(sourceNodeId).\(sourcePortId)"
    }

    func node(withId id: String) -> WorkflowNode? {
        nodes.first { $0.id == id }
    }

    /// Adds an edge and the mapping that makes the engine read it. Returns
    /// false, changing nothing, when either node is gone or the same edge
    /// (same nodes, same ports) is already there.
    @discardableResult
    mutating func connect(
        sourceNodeId: String,
        sourcePortId: String,
        targetNodeId: String,
        targetPortId: String
    ) -> Bool {
        guard nodes.contains(where: { $0.id == sourceNodeId }),
              let targetIndex = nodes.firstIndex(where: { $0.id == targetNodeId }) else { return false }
        let alreadyConnected = edges.contains {
            $0.sourceNodeId == sourceNodeId && $0.sourcePortId == sourcePortId
                && $0.targetNodeId == targetNodeId && $0.targetPortId == targetPortId
        }
        guard !alreadyConnected else { return false }

        edges.append(WorkflowEdge(
            sourceNodeId: sourceNodeId,
            targetNodeId: targetNodeId,
            sourcePortId: sourcePortId,
            targetPortId: targetPortId
        ))
        let mapping = InputMapping(
            portId: targetPortId,
            sourcePath: Self.mappingPath(sourceNodeId: sourceNodeId, sourcePortId: sourcePortId)
        )
        nodes[targetIndex].inputMappings.removeAll { $0.portId == targetPortId }
        nodes[targetIndex].inputMappings.append(mapping)
        return true
    }

    /// Removes an edge and the mapping that read it. A mapping on the same
    /// port that reads another source is not this edge's and stays. When
    /// another edge still enters the port, the mapping moves to that edge.
    mutating func removeEdge(id: String) {
        guard let edgeIndex = edges.firstIndex(where: { $0.id == id }) else { return }
        let edge = edges.remove(at: edgeIndex)
        guard let targetIndex = nodes.firstIndex(where: { $0.id == edge.targetNodeId }) else { return }

        let path = Self.mappingPath(sourceNodeId: edge.sourceNodeId, sourcePortId: edge.sourcePortId)
        guard let mappingIndex = nodes[targetIndex].inputMappings.firstIndex(where: {
            $0.portId == edge.targetPortId && $0.sourcePath == path
        }) else { return }

        let other = edges.first {
            $0.targetNodeId == edge.targetNodeId && $0.targetPortId == edge.targetPortId
        }
        if let other {
            nodes[targetIndex].inputMappings[mappingIndex].sourcePath = Self.mappingPath(
                sourceNodeId: other.sourceNodeId, sourcePortId: other.sourcePortId
            )
        } else {
            nodes[targetIndex].inputMappings.remove(at: mappingIndex)
        }
    }

    /// Removes nodes, their edges, and every mapping on a remaining node that
    /// read one of them (a mapping can exist with no edge drawn).
    mutating func removeNodes(ids: Set<String>) {
        let touching = edges.filter { ids.contains($0.sourceNodeId) || ids.contains($0.targetNodeId) }
        for edge in touching {
            removeEdge(id: edge.id)
        }
        nodes.removeAll { ids.contains($0.id) }
        let prefixes = ids.map { "$.nodes.\($0)." }
        for index in nodes.indices {
            nodes[index].inputMappings.removeAll { mapping in
                prefixes.contains { mapping.sourcePath.hasPrefix($0) }
            }
        }
    }
}
