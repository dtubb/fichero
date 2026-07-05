import Observation
import FicheroAPIClient
import SwiftUI

// Force-directed graph model + simulation extracted from OntologyBrowser.swift
// (#1703). Nodes = entities, edges = co-occurrence in claims. The simulation
// is a Coulomb/Hooke layout that converges in ~4 seconds and then freezes.
// swiftlint:disable identifier_name
// Force-directed physics uses standard short names (i, j, dx, dy, fx, fy)
// for clarity in the math. Re-enabled after the private struct
// definitions at the end of the file.

@MainActor
@Observable
final class OntologyBrowserLoadState {
    var entities: [Components.Schemas.KnowledgeEntity] = []
    var claimCounts: [String: Int] = [:]
    var loadError: String?
    var isLoading = false
    var entityClaims: [Components.Schemas.KnowledgeClaim] = []
    var isLoadingClaims = false
}

// MARK: - Model

struct GraphNode: Identifiable {
    let id: String
    let name: String
    let kind: Components.Schemas.EntityTypeOutput?
    var position: CGPoint
    var velocity: CGVector
}

struct GraphEdge {
    let source: String
    let target: String
    /// SVO predicate verb from the backend (e.g. "served as", "founded").
    /// Drawn mid-edge so the user sees the relationship type at a glance.
    let predicate: String
    /// Claim ID — so click-edge can focus the source without navigating.
    let claimId: String
    /// Source document ID + page label for cross-view KG focus.
    let sourceDocumentId: String
    let pageLabel: String?
    /// Aggregate weight (how many claims connect these two entities).
    /// Used by the render to set line opacity / thickness.
    let weight: Int
}

private struct EdgeKey: Hashable {
    let source: String
    let target: String
}

struct EpistemologyGraphEdgeInput {
    let sourceId: String
    let targetId: String
    let predicate: String
    let claimId: String
    let sourceDocumentId: String
    let sourcePageLabel: String?
}

struct EpistemologyGraphReducedEdge: Equatable {
    let source: String
    let target: String
    let predicate: String
    let claimId: String
    let sourceDocumentId: String
    let pageLabel: String?
    let weight: Int
}

enum EpistemologyGraphReducer {
    static func reduce(
        edges: [EpistemologyGraphEdgeInput],
        allowedNodeIds: Set<String>,
        maxEdges: Int
    ) -> [EpistemologyGraphReducedEdge] {
        var byPair: [EdgeKey: EpistemologyGraphReducedEdge] = [:]
        var weights: [EdgeKey: Int] = [:]
        for edge in edges {
            collect(edge, into: &byPair, weights: &weights, allowedNodeIds: allowedNodeIds)
        }
        return byPair.compactMap { pair, edge in
            EpistemologyGraphReducedEdge(
                source: edge.source,
                target: edge.target,
                predicate: edge.predicate,
                claimId: edge.claimId,
                sourceDocumentId: edge.sourceDocumentId,
                pageLabel: edge.pageLabel,
                weight: weights[pair] ?? 1
            )
        }
        .sorted { lhs, rhs in
            if lhs.weight == rhs.weight {
                return lhs.predicate.count > rhs.predicate.count
            }
            return lhs.weight > rhs.weight
        }
        .prefix(maxEdges)
        .map { $0 }
    }

    private static func collect(
        _ edge: EpistemologyGraphEdgeInput,
        into byPair: inout [EdgeKey: EpistemologyGraphReducedEdge],
        weights: inout [EdgeKey: Int],
        allowedNodeIds: Set<String>
    ) {
        guard allowedNodeIds.contains(edge.sourceId), allowedNodeIds.contains(edge.targetId) else {
            return
        }
        let source = min(edge.sourceId, edge.targetId)
        let target = max(edge.sourceId, edge.targetId)
        let key = EdgeKey(source: source, target: target)
        weights[key, default: 0] += 1
        if byPair[key] == nil {
            byPair[key] = EpistemologyGraphReducedEdge(
                source: edge.sourceId,
                target: edge.targetId,
                predicate: edge.predicate,
                claimId: edge.claimId,
                sourceDocumentId: edge.sourceDocumentId,
                pageLabel: edge.sourcePageLabel,
                weight: 1
            )
        } else if let existing = byPair[key], edge.predicate.count > existing.predicate.count {
            byPair[key] = EpistemologyGraphReducedEdge(
                source: existing.source,
                target: existing.target,
                predicate: edge.predicate,
                claimId: existing.claimId,
                sourceDocumentId: existing.sourceDocumentId,
                pageLabel: existing.pageLabel,
                weight: 1
            )
        }
    }
}

/// Mutable force-directed simulation state, held as a plain reference type
/// so the per-frame physics writes from inside the `Canvas` render closure
/// don't trip SwiftUI's "Modifying state during view update" check (#1019).
/// The view keeps this in `@State` purely for a stable instance; redraws
/// are driven by `TimelineView`, and the empty-state branch is flipped by
/// a separate observed `graphRevision` counter after each load.
final class GraphSimulation {
    private let maxNeighbors = 24
    private let maxEdges = 80
    var nodes: [GraphNode] = []
    var edges: [GraphEdge] = []
    /// Precomputed degree (number of edges) per node id, rebuilt in `rebuild(from:)`.
    var nodeDegrees: [String: Int] = [:]
    private var startTime: Date = .now
    private var lastTick: Date = .now

    /// Lay out the focus at the origin + neighbor entities on a circle
    /// around it. Edges carry the predicate (verb) from the backend.
    func rebuild(from response: Components.Schemas.NeighborhoodResponse) {
        let newNodes = buildNodes(from: response)
        let nodeIds = Set(newNodes.map(\.id))
        edges = buildEdges(from: response, allowedNodeIds: nodeIds)
        nodes = newNodes
        // Precompute degree per node so drawNodes can scale radius without
        // filtering edges on every frame.
        var deg: [String: Int] = [:]
        for edge in edges {
            deg[edge.source, default: 0] += 1
            deg[edge.target, default: 0] += 1
        }
        nodeDegrees = deg
        startTime = .now
        lastTick = .now
    }

    private func buildNodes(
        from response: Components.Schemas.NeighborhoodResponse
    ) -> [GraphNode] {
        let focusKind = response.focusEntityType
        var newNodes: [GraphNode] = []
        newNodes.append(GraphNode(
            id: response.focusEntityId,
            name: response.focusCanonicalName,
            kind: focusKind.flatMap { Components.Schemas.EntityTypeOutput(rawValue: $0) },
            position: .zero,
            velocity: .zero
        ))
        let neighbors = Array(response.neighbors.prefix(maxNeighbors))
        let count = max(neighbors.count, 1)
        let radius: CGFloat = 220
        for (idx, neighbor) in neighbors.enumerated() {
            let angle = Double(idx) / Double(count) * 2.0 * .pi
            newNodes.append(GraphNode(
                id: neighbor.id,
                name: neighbor.canonicalName,
                kind: neighbor.entityType.flatMap {
                    Components.Schemas.EntityTypeOutput(rawValue: $0)
                },
                position: CGPoint(x: cos(angle) * radius, y: sin(angle) * radius),
                velocity: .zero
            ))
        }
        return newNodes
    }

    private func buildEdges(
        from response: Components.Schemas.NeighborhoodResponse,
        allowedNodeIds: Set<String>
    ) -> [GraphEdge] {
        let reduced = EpistemologyGraphReducer.reduce(
            edges: response.edges.map { edge in
                EpistemologyGraphEdgeInput(
                    sourceId: edge.sourceId,
                    targetId: edge.targetId,
                    predicate: edge.predicate,
                    claimId: edge.claimId,
                    sourceDocumentId: edge.sourceDocumentId,
                    sourcePageLabel: edge.sourcePageLabel
                )
            },
            allowedNodeIds: allowedNodeIds,
            maxEdges: maxEdges
        )
        return reduced.map { edge in
            GraphEdge(
                source: edge.source,
                target: edge.target,
                predicate: edge.predicate,
                claimId: edge.claimId,
                sourceDocumentId: edge.sourceDocumentId,
                pageLabel: edge.pageLabel,
                weight: edge.weight
            )
        }
    }

    func step(in size: CGSize, now: Date) {
        guard !nodes.isEmpty, size.width > 0, size.height > 0 else { return }
        let elapsed = now.timeIntervalSince(startTime)
        guard elapsed < 4.0 else { return }
        let dt = max(min(now.timeIntervalSince(lastTick), 1.0 / 30.0), 0.001)
        lastTick = now

        let positions = nodes.map(\.position)
        var forces: [CGVector] = Array(repeating: .zero, count: nodes.count)
        applyRepulsion(positions: positions, forces: &forces)
        applySprings(positions: positions, forces: &forces)
        integrate(forces: forces, dt: dt, size: size)
    }

    private func applyRepulsion(positions: [CGPoint], forces: inout [CGVector]) {
        let repulsion: CGFloat = 6000
        for i in 0..<nodes.count {
            for j in (i + 1)..<nodes.count {
                let dx = positions[i].x - positions[j].x
                let dy = positions[i].y - positions[j].y
                let distSq = max(dx * dx + dy * dy, 25)
                let dist = sqrt(distSq)
                let force = repulsion / distSq
                let fx = (dx / dist) * force
                let fy = (dy / dist) * force
                forces[i].dx += fx; forces[i].dy += fy
                forces[j].dx -= fx; forces[j].dy -= fy
            }
        }
    }

    private func applySprings(positions: [CGPoint], forces: inout [CGVector]) {
        let springLength: CGFloat = 110
        let springStiffness: CGFloat = 0.04
        let idIndex: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.enumerated().map { ($1.id, $0) }
        )
        for edge in edges {
            guard let aIdx = idIndex[edge.source],
                  let bIdx = idIndex[edge.target] else { continue }
            let dx = positions[bIdx].x - positions[aIdx].x
            let dy = positions[bIdx].y - positions[aIdx].y
            let dist = max(sqrt(dx * dx + dy * dy), 0.001)
            let force = springStiffness * (dist - springLength)
            let fx = (dx / dist) * force
            let fy = (dy / dist) * force
            forces[aIdx].dx += fx; forces[aIdx].dy += fy
            forces[bIdx].dx -= fx; forces[bIdx].dy -= fy
        }
    }

    private func integrate(forces: [CGVector], dt: TimeInterval, size: CGSize) {
        let damping: CGFloat = 0.82
        let centerPull: CGFloat = 0.012
        let maxSpeed: CGFloat = 240
        let halfW = size.width / 2 - 20
        let halfH = size.height / 2 - 20
        for i in 0..<nodes.count {
            var node = nodes[i]
            var force = forces[i]
            force.dx += -(node.position.x) * centerPull
            force.dy += -(node.position.y) * centerPull
            node.velocity.dx = (node.velocity.dx + force.dx * CGFloat(dt)) * damping
            node.velocity.dy = (node.velocity.dy + force.dy * CGFloat(dt)) * damping
            let speed = sqrt(node.velocity.dx * node.velocity.dx + node.velocity.dy * node.velocity.dy)
            if speed > maxSpeed {
                node.velocity.dx = node.velocity.dx / speed * maxSpeed
                node.velocity.dy = node.velocity.dy / speed * maxSpeed
            }
            guard node.velocity.dx.isFinite, node.velocity.dy.isFinite else {
                node.velocity = .zero
                nodes[i] = node
                continue
            }
            node.position.x += node.velocity.dx * CGFloat(dt)
            node.position.y += node.velocity.dy * CGFloat(dt)
            guard node.position.x.isFinite, node.position.y.isFinite else {
                node.position = .zero
                node.velocity = .zero
                nodes[i] = node
                continue
            }
            node.position.x = min(max(node.position.x, -halfW), halfW)
            node.position.y = min(max(node.position.y, -halfH), halfH)
            nodes[i] = node
        }
    }
}

// swiftlint:enable identifier_name
