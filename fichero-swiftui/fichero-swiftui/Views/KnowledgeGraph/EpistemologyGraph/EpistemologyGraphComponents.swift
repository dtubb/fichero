import FicheroAPIClient
import SwiftUI

// MARK: - Link Type Filter

enum LinkTypeFilter: String, CaseIterable {
    case all = "All"
    case supports = "Supports"
    case contradicts = "Contradicts"
    case refines = "Refines"
    case supersedes = "Supersedes"

    var color: Color {
        switch self {
        case .all: return .accentColor
        case .supports: return .blue
        case .contradicts: return .red
        case .refines: return .purple
        case .supersedes: return .orange
        }
    }
}

// MARK: - Graph Grid Layer

struct GraphGridLayer: View {
    let zoom: CGFloat
    let offset: CGSize

    var body: some View {
        Canvas { context, canvasSize in
            let gridSpacing: CGFloat = 40 * zoom
            let offsetX = offset.width.truncatingRemainder(dividingBy: gridSpacing)
            let offsetY = offset.height.truncatingRemainder(dividingBy: gridSpacing)

            var path = Path()
            var gridX = offsetX
            while gridX < canvasSize.width {
                path.move(to: CGPoint(x: gridX, y: 0))
                path.addLine(to: CGPoint(x: gridX, y: canvasSize.height))
                gridX += gridSpacing
            }
            var gridY = offsetY
            while gridY < canvasSize.height {
                path.move(to: CGPoint(x: 0, y: gridY))
                path.addLine(to: CGPoint(x: canvasSize.width, y: gridY))
                gridY += gridSpacing
            }
            context.stroke(path, with: .color(.gray.opacity(0.15)), lineWidth: 0.5)
        }
    }
}

// MARK: - Graph Links Layer

struct GraphLinksLayer: View {
    let claims: [Components.Schemas.KnowledgeClaim]
    let links: [Components.Schemas.KnowledgeClaimLink]
    let zoom: CGFloat
    let offset: CGSize
    let size: CGSize

    var body: some View {
        Canvas { context, _ in
            for link in links {
                guard let sourceId = link.sourceClaimId,
                      let targetId = link.targetClaimId,
                      let sourceClaim = claims.first(where: { $0.id == sourceId }),
                      let targetClaim = claims.first(where: { $0.id == targetId }) else { continue }

                let sourcePos = nodePosition(for: sourceClaim)
                let targetPos = nodePosition(for: targetClaim)

                var path = Path()
                path.move(to: sourcePos)
                path.addLine(to: targetPos)
                let color = linkColor(for: link.linkType)
                context.stroke(path, with: .color(color.opacity(0.6)), lineWidth: 2)

                let angle = atan2(targetPos.y - sourcePos.y, targetPos.x - sourcePos.x)
                let arrowLength: CGFloat = 10
                let arrowAngle: CGFloat = .pi / 6
                let arrowPoint = CGPoint(
                    x: targetPos.x - cos(angle) * 20,
                    y: targetPos.y - sin(angle) * 20
                )
                var arrowPath = Path()
                arrowPath.move(to: arrowPoint)
                arrowPath.addLine(to: CGPoint(
                    x: arrowPoint.x - arrowLength * cos(angle - arrowAngle),
                    y: arrowPoint.y - arrowLength * sin(angle - arrowAngle)
                ))
                arrowPath.move(to: arrowPoint)
                arrowPath.addLine(to: CGPoint(
                    x: arrowPoint.x - arrowLength * cos(angle + arrowAngle),
                    y: arrowPoint.y - arrowLength * sin(angle + arrowAngle)
                ))
                context.stroke(arrowPath, with: .color(color.opacity(0.8)), lineWidth: 1.5)
            }
        }
    }

    private func nodePosition(for claim: Components.Schemas.KnowledgeClaim) -> CGPoint {
        let hash = abs((claim.id ?? "").hashValue)
        let posX = CGFloat(hash % 10000) / 10000.0 * (size.width - 80) + 40
        let posY = CGFloat((hash / 10000) % 10000) / 10000.0 * (size.height - 80) + 40
        return CGPoint(x: posX, y: posY)
    }

    private func linkColor(for type: String) -> Color {
        switch type.lowercased() {
        case "supports": return .blue
        case "contradicts": return .red
        case "refines": return .purple
        case "supersedes": return .orange
        default: return .gray
        }
    }
}

// MARK: - Graph Nodes Layer

struct GraphNodesLayer: View {
    let claims: [Components.Schemas.KnowledgeClaim]
    let selectedClaimId: String?
    let focusClaimId: String?
    let zoom: CGFloat
    let offset: CGSize
    let size: CGSize
    let onNodeTap: (Components.Schemas.KnowledgeClaim) -> Void

    var body: some View {
        ForEach(claims, id: \.id) { claim in
            ClaimNode(
                claim: claim,
                isSelected: selectedClaimId == claim.id,
                isFocused: focusClaimId == claim.id
            )
            .position(nodePosition(for: claim))
            .onTapGesture { onNodeTap(claim) }
        }
    }

    private func nodePosition(for claim: Components.Schemas.KnowledgeClaim) -> CGPoint {
        let hash = abs((claim.id ?? "").hashValue)
        let posX = CGFloat(hash % 10000) / 10000.0 * (size.width - 80) + 40
        let posY = CGFloat((hash / 10000) % 10000) / 10000.0 * (size.height - 80) + 40
        return CGPoint(x: posX, y: posY)
    }
}

// MARK: - Graph Loading State

struct GraphLoadingStateView: View {
    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading knowledge graph...")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Graph Error State

struct GraphErrorStateView: View {
    let error: String
    let onRetry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 36))
                .foregroundStyle(.orange)

            Text("Failed to Load Graph")
                .font(.headline)

            Text(error)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button("Retry", action: onRetry)
                .buttonStyle(.bordered)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Graph Empty State

struct GraphEmptyStateView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "chart.dots.scatter")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Claims Yet")
                .font(.headline)

            Text("Create claims and link them to see the epistemology graph")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Graph Toolbar View

struct GraphToolbarView: View {
    @Binding var linkTypeFilter: LinkTypeFilter
    let onFocusSelected: () -> Void
    let onClearFocus: () -> Void
    let graphZoom: CGFloat
    let onZoomIn: () -> Void
    let onZoomOut: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            linkTypePicker
            filterMenu
            zoomControls
        }
    }

    private var linkTypePicker: some View {
        Picker("Link Type", selection: $linkTypeFilter) {
            ForEach(LinkTypeFilter.allCases, id: \.self) { filter in
                HStack {
                    Circle()
                        .fill(filter.color)
                        .frame(width: 8, height: 8)
                    Text(filter.rawValue)
                }
                .tag(filter)
            }
        }
        .pickerStyle(.menu)
    }

    private var filterMenu: some View {
        Menu {
            Button("Show All Links") { linkTypeFilter = .all }
            Divider()
            Button("Focus on Selected", action: onFocusSelected)
            Button("Clear Focus", action: onClearFocus)
        } label: {
            Image(systemName: "line.3.horizontal.decrease.circle")
        }
    }

    private var zoomControls: some View {
        HStack(spacing: 4) {
            Button(action: onZoomOut) {
                Image(systemName: "minus.magnifyingglass")
            }
            .buttonStyle(.plain)

            Text("\(Int(graphZoom * 100))%")
                .font(.caption)
                .frame(width: 40)

            Button(action: onZoomIn) {
                Image(systemName: "plus.magnifyingglass")
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - Claim Inspector Panel View

struct ClaimInspectorPanelView: View {
    let claim: Components.Schemas.KnowledgeClaim?
    let onDismiss: () -> Void

    var body: some View {
        Group {
            if let claim = claim {
                VStack(spacing: 0) {
                    inspectorHeader
                    Divider()
                    ClaimInspector(claim: claim)
                }
                .frame(minWidth: 280, maxWidth: 400)
            } else {
                emptyInspectorState
            }
        }
    }

    private var inspectorHeader: some View {
        HStack {
            Text("Claim Inspector")
                .font(.headline)
            Spacer()
            Button(action: onDismiss) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
    }

    private var emptyInspectorState: some View {
        VStack(spacing: 12) {
            Image(systemName: "hand.tap")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Claim Selected")
                .font(.headline)

            Text("Click a node in the graph to inspect it")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}
