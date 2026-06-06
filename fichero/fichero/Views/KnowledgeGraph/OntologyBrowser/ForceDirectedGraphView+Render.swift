import FicheroAPIClient
import SwiftUI

// Canvas drawing, hit-testing, and color mapping for ForceDirectedGraphView
// (#1703). Split from the view body so each file stays under the SwiftLint
// type/file limits. Behavior is identical.
// swiftlint:disable identifier_name
// Force-directed physics uses standard short names (i, j, dx, dy, fx, fy)
// for clarity in the math.
extension ForceDirectedGraphView {
    // MARK: - Drawing

    func drawEdges(ctx: GraphicsContext) {
        for edge in sim.edges {
            guard let source = sim.nodes.first(where: { $0.id == edge.source }),
                  let target = sim.nodes.first(where: { $0.id == edge.target }) else { continue }
            let from = centered(source.position, in: ctx)
            let dest = centered(target.position, in: ctx)
            guard from.x.isFinite && from.y.isFinite && dest.x.isFinite && dest.y.isFinite else { continue }
            var path = Path()
            path.move(to: from)
            path.addLine(to: dest)
            let alpha = min(0.2 + Double(edge.weight) * 0.08, 0.65)
            let width = min(1.0 + CGFloat(edge.weight - 1) * 0.35, 2.6)
            ctx.stroke(path, with: .color(.secondary.opacity(alpha)), lineWidth: width)
            // Predicate label at the midpoint. Skip when the edge is so
            // short that the label would overlap a node. Background-
            // ribbon the label so it's readable across the line.
            let dx = dest.x - from.x
            let dy = dest.y - from.y
            let lineLen = sqrt(dx * dx + dy * dy)
            if lineLen > 72, edge.weight >= 2, !edge.predicate.isEmpty {
                let midX = (from.x + dest.x) / 2
                let midY = (from.y + dest.y) / 2
                let label = Text(edge.predicate)
                    .font(.caption2)
                    .italic()
                    .foregroundColor(.accentColor)
                ctx.draw(label, at: CGPoint(x: midX, y: midY), anchor: .center)
            }
        }
    }

    func drawNodes(ctx: GraphicsContext) {
        for node in sim.nodes {
            let pos = centered(node.position, in: ctx)
            guard pos.x.isFinite && pos.y.isFinite else { continue }
            let isFocus = node.id == selectedEntityId
            // Scale radius by degree so high-connectivity nodes are visually larger.
            let degree = sim.nodeDegrees[node.id] ?? 0
            let baseRadius: CGFloat = isFocus ? 9 : 5
            let radius = baseRadius + CGFloat(min(degree, 10)) * 0.45
            let circle = Path(ellipseIn: CGRect(
                x: pos.x - radius,
                y: pos.y - radius,
                width: radius * 2,
                height: radius * 2
            ))
            ctx.fill(circle, with: .color(color(for: node.kind)))
            if isFocus {
                ctx.stroke(circle, with: .color(.accentColor), lineWidth: 2)
            } else {
                ctx.stroke(circle, with: .color(.primary.opacity(0.3)), lineWidth: 0.5)
            }
            let label = Text(node.name).font(.caption2).foregroundColor(.primary)
            ctx.draw(label, at: CGPoint(x: pos.x, y: pos.y + radius + 7), anchor: .top)
        }
    }

    func centered(_ point: CGPoint, in ctx: GraphicsContext) -> CGPoint {
        // Apply viewport scale + pan around the canvas center, so pinch
        // zooms toward the center and drag moves the whole graph
        // together. Edge widths and node radii intentionally don't scale
        // — keeps the graph readable at any zoom level.
        let bounds = ctx.clipBoundingRect
        return CGPoint(
            x: bounds.midX + point.x * scale + panOffset.width,
            y: bounds.midY + point.y * scale + panOffset.height
        )
    }

    // MARK: - Interaction

    func handleTap(at location: CGPoint, in size: CGSize) {
        // Inverse of `centered`: back out scale + panOffset to get
        // simulation-space coordinates for hit-testing.
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let local = CGPoint(
            x: (location.x - center.x - panOffset.width) / scale,
            y: (location.y - center.y - panOffset.height) / scale
        )
        // Hit radius is in simulation space — divide by scale so the tap
        // target stays a constant ~18pt of screen space.
        let hitRadius: CGFloat = 18 / scale
        // Node hit-test first — clicking a node refocuses.
        var bestNode: (id: String, dist: CGFloat)?
        for node in sim.nodes {
            let dx = node.position.x - local.x
            let dy = node.position.y - local.y
            let dist = sqrt(dx * dx + dy * dy)
            if dist < hitRadius, dist < (bestNode?.dist ?? .greatestFiniteMagnitude) {
                bestNode = (node.id, dist)
            }
        }
        if let hit = bestNode {
            selectedEntityId = hit.id
            kgFocusState.focusEntity(entityId: hit.id)
            return
        }
        // No node hit — check whether the tap landed near an edge's
        // midpoint (where the predicate label sits). Clicking an edge
        // opens the source claim. (#982 — wireframe Path B)
        let edgeHitRadius: CGFloat = 22 / scale
        var bestEdge: (edge: GraphEdge, dist: CGFloat)?
        for edge in sim.edges {
            guard let source = sim.nodes.first(where: { $0.id == edge.source }),
                  let target = sim.nodes.first(where: { $0.id == edge.target }) else { continue }
            let midX = (source.position.x + target.position.x) / 2
            let midY = (source.position.y + target.position.y) / 2
            let dx = midX - local.x
            let dy = midY - local.y
            let dist = sqrt(dx * dx + dy * dy)
            if dist < edgeHitRadius, dist < (bestEdge?.dist ?? .greatestFiniteMagnitude) {
                bestEdge = (edge, dist)
            }
        }
        if let hit = bestEdge {
            kgFocusState.focusClaim(
                claimId: hit.edge.claimId,
                sourceDocumentId: hit.edge.sourceDocumentId,
                sourcePageLabel: hit.edge.pageLabel
            )
        }
    }

    // MARK: - Colors

    func color(
        for kind: Components.Schemas.EntityTypeOutput?
    ) -> Color {
        guard let kind else { return .gray }
        switch kind {
        case .person: return .blue
        case .organization: return .purple
        case .location: return .green
        case .event: return .orange
        case .concept: return .yellow
        case .citation: return .brown
        case .other: return .gray
        }
    }
}

// swiftlint:enable identifier_name
