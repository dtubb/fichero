import FicheroAPIClient
import SwiftUI

/// Graph view showing claim-to-claim epistemology relationships
/// Visualizes supports/contradicts/refines/supersedes links between claims
struct EpistemologyGraphView: View {
    @State private var selectedClaim: Components.Schemas.KnowledgeClaim?
    @State private var focusClaimId: String?
    @State private var linkTypeFilter: LinkTypeFilter = .all
    @State private var graphZoom: CGFloat = 1.0
    @State private var graphOffset: CGSize = .zero

    var body: some View {
        HSplitView {
            graphCanvas
            claimInspectorPanel
        }
        .frame(minWidth: 400, minHeight: 300)
        .toolbar { ToolbarItemGroup { graphToolbar } }
    }

    // MARK: - Graph Canvas

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
    @State private var allLinks: [Components.Schemas.KnowledgeClaimLink] = []
    @State private var isLoading = false
    @State private var loadError: String?

    private var graphCanvas: some View {
        VStack(spacing: 0) {
            if isLoading {
                GraphLoadingStateView()
            } else if let error = loadError {
                GraphErrorStateView(error: error, onRetry: { Task { await loadGraphData() } })
            } else if claims.isEmpty {
                GraphEmptyStateView()
            } else {
                graphView
            }
        }
        .frame(minWidth: 250)
        .background(Color(.windowBackgroundColor))
        .task { await loadGraphData() }
    }

    private var graphView: some View {
        GeometryReader { geometry in
            ZStack {
                GraphGridLayer(
                    zoom: graphZoom,
                    offset: graphOffset
                )
                GraphLinksLayer(
                    claims: claims,
                    links: filteredLinks,
                    zoom: graphZoom,
                    offset: graphOffset,
                    size: geometry.size
                )
                GraphNodesLayer(
                    claims: claims,
                    selectedClaimId: selectedClaim?.id,
                    focusClaimId: focusClaimId,
                    zoom: graphZoom,
                    offset: graphOffset,
                    size: geometry.size,
                    onNodeTap: { claim in selectedClaim = claim }
                )
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

    private var filteredLinks: [Components.Schemas.KnowledgeClaimLink] {
        if linkTypeFilter == .all { return allLinks }
        return allLinks.filter { $0.linkType.lowercased() == linkTypeFilter.rawValue.lowercased() }
    }

    // MARK: - Toolbar

    private var graphToolbar: some View {
        GraphToolbarView(
            linkTypeFilter: $linkTypeFilter,
            onFocusSelected: {
                if let claim = selectedClaim { focusClaimId = claim.id }
            },
            onClearFocus: { focusClaimId = nil },
            graphZoom: graphZoom,
            onZoomIn: { graphZoom = min(graphZoom + 0.25, 3.0) },
            onZoomOut: { graphZoom = max(graphZoom - 0.25, 0.25) }
        )
    }

    // MARK: - Claim Inspector Panel

    private var claimInspectorPanel: some View {
        ClaimInspectorPanelView(
            claim: selectedClaim,
            onDismiss: { selectedClaim = nil }
        )
    }

    // MARK: - Data Loading

    private func loadGraphData() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)

            claims = try await service.listClaims(limit: 100)

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

// MARK: - Previews

#Preview("Graph") {
    EpistemologyGraphView()
        .frame(width: 700, height: 500)
}
