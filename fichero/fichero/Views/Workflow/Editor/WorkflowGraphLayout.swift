import Foundation
import SwiftUI

// MARK: - Topological ordering (shared by list view, canvas step badges, tidy)

/// Pure graph ordering for a workflow: the same topological sort backs the
/// list view's numbering, the canvas step badges, and the Tidy layout, so
/// every surface agrees on what "step 3" means (#4322 / #4323).
enum WorkflowTopology {

    /// Nodes in execution order when the graph is acyclic; falls back to a
    /// deterministic visual (left-to-right, top-to-bottom) order otherwise.
    static func orderedNodes(nodes: [WorkflowNode], edges: [WorkflowEdge]) -> [WorkflowNode] {
        guard !nodes.isEmpty else { return [] }

        let nodeById = Dictionary(uniqueKeysWithValues: nodes.map { ($0.id, $0) })
        var indegree = Dictionary(uniqueKeysWithValues: nodes.map { ($0.id, 0) })
        var outgoing: [String: [String]] = [:]

        for edge in edges {
            guard nodeById[edge.sourceNodeId] != nil, nodeById[edge.targetNodeId] != nil else { continue }
            outgoing[edge.sourceNodeId, default: []].append(edge.targetNodeId)
            indegree[edge.targetNodeId, default: 0] += 1
        }

        // Stable tie-breaker by canvas position for deterministic ordering.
        let positionSorted = nodes.sorted(by: isOrderedBefore)

        var queue = positionSorted.filter { indegree[$0.id, default: 0] == 0 }.map(\.id)
        var ordered: [WorkflowNode] = []

        while !queue.isEmpty {
            let currentId = queue.removeFirst()
            guard let node = nodeById[currentId] else { continue }
            ordered.append(node)

            for nextId in outgoing[currentId, default: []] {
                let nextIn = (indegree[nextId] ?? 0) - 1
                indegree[nextId] = nextIn
                if nextIn == 0 {
                    queue.append(nextId)
                    queue.sort { lhs, rhs in
                        guard let lhsNode = nodeById[lhs], let rhsNode = nodeById[rhs] else { return lhs < rhs }
                        return isOrderedBefore(lhsNode, rhsNode)
                    }
                }
            }
        }

        // Cycles or malformed graph: fall back to visual order.
        if ordered.count != nodes.count {
            return positionSorted
        }
        return ordered
    }

    /// 1-based execution step for each node id, from the topological sort.
    static func stepNumbers(nodes: [WorkflowNode], edges: [WorkflowEdge]) -> [String: Int] {
        Dictionary(
            uniqueKeysWithValues: orderedNodes(nodes: nodes, edges: edges)
                .enumerated()
                .map { ($0.element.id, $0.offset + 1) }
        )
    }

    /// Deterministic canvas-position ordering used to break topological ties.
    static func isOrderedBefore(_ lhs: WorkflowNode, _ rhs: WorkflowNode) -> Bool {
        if lhs.positionX == rhs.positionX {
            return lhs.positionY < rhs.positionY
        }
        return lhs.positionX < rhs.positionX
    }
}

// MARK: - Tidy layout

/// Left-to-right layered layout driven by the topological sort (#4323).
/// Column = longest-path depth from the roots; rows stack within a column
/// in execution order. Pure — returns target center positions by node id.
enum WorkflowTidyLayout {
    static func positions(
        nodes: [WorkflowNode],
        edges: [WorkflowEdge],
        nodeSize: CGSize = CGSize(width: 140, height: 100),
        horizontalSpacing: CGFloat = 80,
        verticalSpacing: CGFloat = 40,
        origin: CGPoint = CGPoint(x: 150, y: 150)
    ) -> [String: CGPoint] {
        let ordered = WorkflowTopology.orderedNodes(nodes: nodes, edges: edges)
        guard !ordered.isEmpty else { return [:] }

        let validIds = Set(nodes.map(\.id))
        var incoming: [String: [String]] = [:]
        for edge in edges where validIds.contains(edge.sourceNodeId) && validIds.contains(edge.targetNodeId) {
            incoming[edge.targetNodeId, default: []].append(edge.sourceNodeId)
        }

        // Longest-path depth: sources at column 0, each node one column right
        // of its deepest predecessor. Ordered traversal guarantees predecessors
        // are resolved first in the acyclic case; in the cycle fallback the
        // compactMap simply ignores unresolved predecessors.
        var depth: [String: Int] = [:]
        for node in ordered {
            let predecessorDepths = (incoming[node.id] ?? []).compactMap { depth[$0] }
            depth[node.id] = predecessorDepths.max().map { $0 + 1 } ?? 0
        }

        var rowsUsedInColumn: [Int: Int] = [:]
        var positions: [String: CGPoint] = [:]
        for node in ordered {
            let column = depth[node.id] ?? 0
            let row = rowsUsedInColumn[column] ?? 0
            rowsUsedInColumn[column] = row + 1
            positions[node.id] = CGPoint(
                x: origin.x + CGFloat(column) * (nodeSize.width + horizontalSpacing),
                y: origin.y + CGFloat(row) * (nodeSize.height + verticalSpacing)
            )
        }
        return positions
    }
}

// MARK: - Add-node placement

/// Placement for a node added from the palette: after the selected node when
/// there is one, otherwise after the LAST node in execution order — never at
/// the rightmost X of an arbitrary branch (#4323).
enum WorkflowNodePlacement {
    static func nextNodePosition(
        nodes: [WorkflowNode],
        edges: [WorkflowEdge],
        selectedNodeIds: Set<String>,
        nodeSize: CGSize = CGSize(width: 140, height: 100),
        horizontalGap: CGFloat = 160,
        verticalGap: CGFloat = 20
    ) -> CGPoint {
        guard !nodes.isEmpty else { return CGPoint(x: 150, y: 200) }

        let ordered = WorkflowTopology.orderedNodes(nodes: nodes, edges: edges)
        let anchor = ordered.last(where: { selectedNodeIds.contains($0.id) })
            ?? ordered.last
            ?? nodes[0]

        var candidate = CGPoint(x: anchor.positionX + horizontalGap, y: anchor.positionY)

        // Nudge downward while the spot is occupied so the new node never
        // lands on top of an existing one. Bounded by the node count.
        var attempts = 0
        while attempts <= nodes.count && isOccupied(candidate, nodes: nodes, nodeSize: nodeSize) {
            candidate.y += nodeSize.height + verticalGap
            attempts += 1
        }
        return candidate
    }

    private static func isOccupied(_ point: CGPoint, nodes: [WorkflowNode], nodeSize: CGSize) -> Bool {
        nodes.contains { node in
            abs(node.positionX - point.x) < nodeSize.width * 0.75
                && abs(node.positionY - point.y) < nodeSize.height * 0.75
        }
    }
}
