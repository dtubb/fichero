import FicheroAPIClient
import SwiftUI

/// The views the knowledge surface can show. The first three raw values match
/// the tab ids the in-page JS (`document_view.html`) expects.
enum KGSurfaceTab: String, CaseIterable, Identifiable {
    case transcript
    case digest
    case graph
    case claims
    case timeline
    case map
    case realitykit

    var id: String { rawValue }

    /// Human-readable label shown on the native toolbar button.
    var title: String {
        switch self {
        case .transcript: return "Transcript"
        case .digest: return "Digest"
        case .graph: return "Graph"
        case .claims: return "Claims"
        case .timeline: return "Timeline"
        case .map: return "Map"
        case .realitykit: return "RealityKit"
        }
    }

    /// SF Symbol mirroring the inspector tab-bar visual language.
    var icon: String {
        switch self {
        case .transcript: return "doc.text"
        case .digest: return "list.bullet.rectangle"
        case .graph: return "point.3.connected.trianglepath.dotted"
        case .claims: return "quote.bubble"
        case .timeline: return "calendar.badge.clock"
        case .map: return "map"
        case .realitykit: return "cube.transparent"
        }
    }
}

/// Hosts the WebKit document KG plus native document-scoped claims, timeline,
/// and map visualizations under one fixed toolbar.
struct DocumentKGSurface: View {
    let documentId: String
    let libraryPath: String
    var selectedEntityId: String?
    var selectedClaimId: String?
    var activePageNumber: Int?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }

    @State private var activeTab: KGSurfaceTab = .transcript
    @State private var selectedEntityId: String?
    @State private var selectedSpatialNodeId: String?
    @Environment(KGFocusState.self) private var kgFocusState
    @EnvironmentObject private var entityService: EntityServiceGenerated
    @EnvironmentObject private var artifactService: ArtifactServiceGenerated

    var body: some View {
        VStack(spacing: 0) {
            MiniToolbar {
                Spacer(minLength: 0)
                ForEach(KGSurfaceTab.allCases) { tab in
                    tabButton(tab)
                }
                Spacer(minLength: 0)
            }
            .accessibilityIdentifier("knowledgeSurfaceTabs")

            Divider()

            content
        }
    }

    @ViewBuilder
    private var content: some View {
        switch activeTab {
        case .transcript, .digest, .graph:
            DocumentKGWebPane(
                documentId: documentId,
                libraryPath: libraryPath,
                selectedEntityId: selectedEntityId,
                selectedClaimId: selectedClaimId,
                activeTab: activeTab.rawValue,
                activePageNumber: activePageNumber,
                pageCount: pageCount,
                onPageSelected: onPageSelected
            )
        case .claims:
            ScrollView {
                KnowledgeGraphInspectorSection(
                    documentId: documentId,
                    entityService: entityService,
                    artifactService: artifactService,
                    onClaimSelect: { claimId, _, sourceDocId, pageLabel, _, _ in
                        kgFocusState.focusClaim(
                            claimId: claimId,
                            sourceDocumentId: sourceDocId,
                            sourcePageLabel: pageLabel
                        )
                    }
                )
                .padding()
            }
        case .timeline:
            KGTimelineView(
                entities: [],
                selectedEntityId: $selectedEntityId,
                sourceDocumentId: documentId
            )
        case .map:
            KGMapView(
                entities: [],
                selectedEntityId: $selectedEntityId,
                sourceDocumentId: documentId
            )
        case .realitykit:
            FolderRealityKitSurface(
                documentId: documentId,
                selectedNodeId: $selectedSpatialNodeId
            )
        }
    }

    @ViewBuilder
    private func tabButton(_ tab: KGSurfaceTab) -> some View {
        let isSelected = activeTab == tab
        Button {
            activeTab = tab
        } label: {
            Image(systemName: tab.icon)
                .font(.system(size: 16, weight: .regular))
                .frame(width: 40)
                .frame(maxHeight: .infinity)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isSelected ? Color.accentColor.opacity(0.15) : Color.clear)
        )
        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
        .help(tab.title)
        .accessibilityIdentifier("kgSurfaceTab-\(tab.rawValue)")
    }
}

private struct FolderRealityKitSurface: View {
    let documentId: String
    @Binding var selectedNodeId: String?

    private var nodes: [MindPalaceNode] {
        [
            MindPalaceNode(
                id: "folder-\(documentId)",
                roomId: documentId,
                nodeType: .source,
                sourceId: documentId,
                label: "Folder",
                positionX: 0,
                positionY: 0,
                positionZ: 0,
                scale: 2
            )
        ]
    }

    var body: some View {
        SpatialScene3D(
            nodes: nodes,
            connections: [],
            selectedNodeId: $selectedNodeId
        )
    }
}
