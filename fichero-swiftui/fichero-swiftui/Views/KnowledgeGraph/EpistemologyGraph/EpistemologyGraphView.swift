import SwiftUI
import FicheroAPIClient

/// Graph view showing claim-to-claim epistemology relationships
/// Visualizes supports/contradicts/refines/supersedes links between claims
struct EpistemologyGraphView: View {
    @State private var selectedClaim: Components.Schemas.KnowledgeClaim?
    @State private var focusClaimId: String?
    @State private var linkTypeFilter: LinkTypeFilter = .all
    @State private var graphZoom: CGFloat = 1.0
    @State private var graphOffset: CGSize = .zero

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

    var body: some View {
        HSplitView {
            graphCanvas
            claimInspectorPanel
        }
        .frame(minWidth: 400, minHeight: 300)
        .toolbar {
            ToolbarItemGroup {
                linkTypePicker
                filterMenu
                zoomControls
            }
        }
    }

    // MARK: - Graph Canvas

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
    @State private var allLinks: [Components.Schemas.KnowledgeClaimLink] = []
    @State private var isLoading = false
    @State private var loadError: String?

    private var graphCanvas: some View {
        VStack(spacing: 0) {
            if isLoading {
                loadingState
            } else if let error = loadError {
                errorState(error)
            } else if claims.isEmpty {
                emptyState
            } else {
                graphView
            }
        }
        .frame(minWidth: 250)
        .background(Color(.windowBackgroundColor))
        .task {
            await loadGraphData()
        }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading knowledge graph...")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ error: String) -> some View {
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

            Button("Retry") {
                Task { await loadGraphData() }
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
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

    private var graphView: some View {
        GeometryReader { geometry in
            ZStack {
                // Grid background
                gridPattern(in: geometry.size)

                // Links layer
                linksLayer(in: geometry.size)

                // Nodes layer
                nodesLayer(in: geometry.size)
            }
            .scaleEffect(graphZoom)
            .offset(graphOffset)
            .gesture(
                DragGesture()
                    .onChanged { value in
                        graphOffset = CGSize(
                            width: graphOffset.width + value.translation.width,
                            height: graphOffset.height + value.translation.height
                        )
                    }
            )
            .gesture(
                MagnificationGesture()
                    .onChanged { value in
                        graphZoom = min(max(value, 0.25), 3.0)
                    }
            )
            .onTapGesture {
                selectedClaim = nil
                focusClaimId = nil
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .padding(8)
    }

    private func gridPattern(in size: CGSize) -> some View {
        Canvas { context, canvasSize in
            let gridSpacing: CGFloat = 40 * graphZoom
            let offsetX = graphOffset.width.truncatingRemainder(dividingBy: gridSpacing)
            let offsetY = graphOffset.height.truncatingRemainder(dividingBy: gridSpacing)

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

    private var filteredLinks: [Components.Schemas.KnowledgeClaimLink] {
        if linkTypeFilter == .all {
            return allLinks
        }
        return allLinks.filter { $0.linkType.lowercased() == linkTypeFilter.rawValue.lowercased() }
    }

    private func linksLayer(in size: CGSize) -> some View {
        Canvas { context, _ in
            for link in filteredLinks {
                guard let sourceId = link.sourceClaimId,
                      let targetId = link.targetClaimId,
                      let sourceClaim = claims.first(where: { $0.id == sourceId }),
                      let targetClaim = claims.first(where: { $0.id == targetId }) else { continue }

                let sourcePos = nodePosition(for: sourceClaim, in: size)
                let targetPos = nodePosition(for: targetClaim, in: size)

                var path = Path()
                path.move(to: sourcePos)
                path.addLine(to: targetPos)

                let color = linkColor(for: link.linkType)
                context.stroke(path, with: .color(color.opacity(0.6)), lineWidth: 2)

                // Arrow head
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

    private func nodesLayer(in size: CGSize) -> some View {
        ForEach(claims, id: \.id) { claim in
            ClaimNode(
                claim: claim,
                isSelected: selectedClaim?.id == claim.id,
                isFocused: focusClaimId == claim.id
            )
            .position(nodePosition(for: claim, in: size))
            .onTapGesture {
                selectedClaim = claim
            }
        }
    }

    private func nodePosition(for claim: Components.Schemas.KnowledgeClaim, in size: CGSize) -> CGPoint {
        // Use claim ID hash for deterministic positioning
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

    // MARK: - Toolbar Controls

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
            Button("Show All Links") {
                linkTypeFilter = .all
            }
            Divider()
            Button("Focus on Selected") {
                if let claim = selectedClaim {
                    focusClaimId = claim.id
                }
            }
            Button("Clear Focus") {
                focusClaimId = nil
            }
        } label: {
            Image(systemName: "line.3.horizontal.decrease.circle")
        }
    }

    private var zoomControls: some View {
        HStack(spacing: 4) {
            Button {
                graphZoom = max(graphZoom - 0.25, 0.25)
            } label: {
                Image(systemName: "minus.magnifyingglass")
            }
            .buttonStyle(.plain)

            Text("\(Int(graphZoom * 100))%")
                .font(.caption)
                .frame(width: 40)

            Button {
                graphZoom = min(graphZoom + 0.25, 3.0)
            } label: {
                Image(systemName: "plus.magnifyingglass")
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Claim Inspector Panel

    private var claimInspectorPanel: some View {
        Group {
            if let claim = selectedClaim {
                VStack(spacing: 0) {
                    inspectorHeader(for: claim)
                    Divider()
                    ClaimInspector(claim: claim)
                }
                .frame(minWidth: 280, maxWidth: 400)
            } else {
                emptyInspectorState
            }
        }
    }

    private func inspectorHeader(for claim: Components.Schemas.KnowledgeClaim) -> some View {
        HStack {
            Text("Claim Inspector")
                .font(.headline)
            Spacer()
            Button {
                selectedClaim = nil
            } label: {
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

    // MARK: - Data Loading

    private func loadGraphData() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)

            claims = try await service.listClaims(limit: 100)

            // Collect all links from all claims
            var collectedLinks: [Components.Schemas.KnowledgeClaimLink] = []
            for claim in claims {
                if let claimId = claim.id {
                    let links = try await service.listClaimLinks(claimId: claimId)
                    collectedLinks.append(contentsOf: links)
                }
            }
            allLinks = collectedLinks
        } catch {
            loadError = error.localizedDescription
        }

        isLoading = false
    }
}

// MARK: - Claim Node

private struct ClaimNode: View {
    let claim: Components.Schemas.KnowledgeClaim
    let isSelected: Bool
    let isFocused: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(backgroundColor)
                    .frame(width: nodeSize, height: nodeSize)

                Circle()
                    .stroke(borderColor, lineWidth: isSelected ? 3 : (isFocused ? 2 : 1))
                    .frame(width: nodeSize, height: nodeSize)

                Image(systemName: iconForClaimType)
                    .font(.system(size: nodeSize * 0.4))
                    .foregroundStyle(iconColor)
            }

            Text(claim.text)
                .font(.caption2)
                .lineLimit(2)
                .frame(width: 80)
                .multilineTextAlignment(.center)
        }
    }

    private var nodeSize: CGFloat { isSelected ? 36 : 28 }

    private var backgroundColor: Color {
        if isSelected {
            return Color.accentColor.opacity(0.2)
        } else if isFocused {
            return Color.accentColor.opacity(0.1)
        }
        return Color(.controlBackgroundColor)
    }

    private var borderColor: Color {
        if isSelected {
            return .accentColor
        } else if isFocused {
            return .accentColor.opacity(0.6)
        }
        return .gray.opacity(0.4)
    }

    private var iconForClaimType: String {
        guard let type = claim.claimType else { return "text.alignleft" }
        switch type {
        case .fact: return "checkmark.circle"
        case .analysis: return "chart.bar"
        case .interpretation: return "text.quote"
        case .argument: return "text.badge.checkmark"
        case .historiography: return "clock"
        case .theory: return "lightbulb"
        }
    }

    private var iconColor: Color {
        guard let status = claim.epistemicStatus else { return .secondary }
        switch status {
        case .confirmed: return .green
        case .rejected: return .red
        case .tentative: return .orange
        }
    }
}

// MARK: - Previews

#Preview("Graph") {
    EpistemologyGraphView()
        .frame(width: 700, height: 500)
}
