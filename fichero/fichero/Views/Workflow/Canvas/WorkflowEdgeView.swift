import SwiftUI

/// Visual representation of an edge (connection between ports)
struct WorkflowEdgeView: View {
    let edge: WorkflowEdge
    let sourcePoint: CGPoint
    let targetPoint: CGPoint
    let isSelected: Bool
    let isConditional: Bool
    /// Optional classification — when .fanOut or .fanIn, a labelled
    /// badge is rendered on the edge so the user can see the topology
    /// change visually. Defaults to .none so existing call sites don't
    /// need to pass a value.
    var fanRole: EdgeFanRole = .none
    /// Live file count during an active run. `nil` when idle — badge
    /// falls back to a static label.
    var fanCount: Int?

    var body: some View {
        ZStack {
            // Invisible wider stroke for easier click targeting
            edgePath
                .stroke(Color.clear, lineWidth: 20)
                .contentShape(edgePath.strokedPath(StrokeStyle(lineWidth: 20)))

            // Shadow for depth
            edgePath
                .stroke(
                    Color.black.opacity(0.2),
                    style: StrokeStyle(lineWidth: isSelected ? 5 : 4, lineCap: .round)
                )
                .offset(x: 1, y: 1)

            // Main edge stroke
            edgePath
                .stroke(
                    edgeColor,
                    style: StrokeStyle(
                        lineWidth: isSelected ? 4 : 2,
                        lineCap: .round,
                        dash: isConditional ? [8, 4] : []
                    )
                )

            // Direction arrow in the middle
            directionArrow

            // Arrow head at target
            arrowHead
                .fill(edgeColor)
                .position(targetPoint)

            // Label if present
            if let label = edge.label, !label.isEmpty {
                edgeLabel(label)
            }

            // Fan-in / fan-out badge — shown even at idle so users see
            // the topology before running. A live count overrides the
            // static label when available.
            if fanRole != .none {
                fanBadge
            }
        }
    }

    /// Pill-shaped badge near the target end of the edge. Colored by
    /// role so fan-out (branching) and fan-in (merging) read at a
    /// glance.
    @ViewBuilder
    private var fanBadge: some View {
        let text = fanRole.label(count: fanCount)
        if !text.isEmpty {
            let position: CGPoint = {
                // Place fan-in badges near the target (where merging
                // happens), fan-out near the source (where branching
                // happens). Makes the direction of the topology bend
                // obvious.
                switch fanRole {
                case .fanIn:
                    return CGPoint(
                        x: sourcePoint.x * 0.3 + targetPoint.x * 0.7,
                        y: sourcePoint.y * 0.3 + targetPoint.y * 0.7 - 14
                    )
                case .fanOut:
                    return CGPoint(
                        x: sourcePoint.x * 0.7 + targetPoint.x * 0.3,
                        y: sourcePoint.y * 0.7 + targetPoint.y * 0.3 - 14
                    )
                case .none:
                    return .zero
                }
            }()
            let tint: Color = fanRole == .fanIn ? .teal : .blue
            Text(text)
                .font(.caption2.weight(.semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(
                    Capsule()
                        .fill(tint)
                        .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
                )
                .position(position)
        }
    }

    private var edgePath: Path {
        Path { path in
            let controlDistance = abs(targetPoint.x - sourcePoint.x) * 0.5
            let control1 = CGPoint(x: sourcePoint.x + controlDistance, y: sourcePoint.y)
            let control2 = CGPoint(x: targetPoint.x - controlDistance, y: targetPoint.y)

            path.move(to: sourcePoint)
            path.addCurve(to: targetPoint, control1: control1, control2: control2)
        }
    }

    /// Static direction arrow in the middle of the edge
    @ViewBuilder
    private var directionArrow: some View {
        let midX = (sourcePoint.x + targetPoint.x) / 2
        let midY = (sourcePoint.y + targetPoint.y) / 2
        let angle = atan2(targetPoint.y - sourcePoint.y, targetPoint.x - sourcePoint.x)

        // Single chevron arrow in middle
        Path { path in
            path.move(to: CGPoint(x: -5, y: -6))
            path.addLine(to: CGPoint(x: 5, y: 0))
            path.addLine(to: CGPoint(x: -5, y: 6))
        }
        .stroke(edgeColor, style: StrokeStyle(lineWidth: isSelected ? 2.5 : 1.5, lineCap: .round, lineJoin: .round))
        .rotationEffect(.radians(angle))
        .position(x: midX, y: midY)
        .opacity(isSelected ? 1.0 : 0.5)
    }

    private var arrowHead: Path {
        Path { path in
            let angle = atan2(targetPoint.y - sourcePoint.y, targetPoint.x - sourcePoint.x)
            let arrowLength: CGFloat = 10
            let arrowAngle: CGFloat = .pi / 6

            let point1 = CGPoint(
                x: -arrowLength * cos(angle - arrowAngle),
                y: -arrowLength * sin(angle - arrowAngle)
            )
            let point2 = CGPoint(
                x: -arrowLength * cos(angle + arrowAngle),
                y: -arrowLength * sin(angle + arrowAngle)
            )

            path.move(to: .zero)
            path.addLine(to: point1)
            path.addLine(to: point2)
            path.closeSubpath()
        }
    }

    private var edgeColor: Color {
        if isSelected {
            return .accentColor
        } else if isConditional {
            return .orange
        } else if edge.animated {
            return .blue
        } else {
            return Color.secondary.opacity(0.7)
        }
    }

    @ViewBuilder
    private func edgeLabel(_ text: String) -> some View {
        let midPoint = CGPoint(
            x: (sourcePoint.x + targetPoint.x) / 2,
            y: (sourcePoint.y + targetPoint.y) / 2
        )

        Text(text)
            .font(.caption2)
            .foregroundColor(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.windowBackgroundColor))
                    .shadow(radius: 1)
            )
            .position(midPoint)
    }
}
