import FicheroAPIClient
import SwiftUI

enum KGGraphRendererFramework: String {
    case cytoscapeWebKit = "cytoscape-webkit"

    static let selected: KGGraphRendererFramework = .cytoscapeWebKit

    var displayName: String {
        switch self {
        case .cytoscapeWebKit:
            return "Cytoscape.js (WebKit)"
        }
    }
}

@MainActor
final class DocumentScrollSyncState: ObservableObject {
    enum Pane {
        case pdf
        case web
    }

    private var drivingPane: Pane?
    private var releaseTask: Task<Void, Never>?

    func beginDriving(_ pane: Pane) -> Bool {
        guard drivingPane == nil || drivingPane == pane else { return false }
        drivingPane = pane
        releaseTask?.cancel()
        releaseTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(50))
            if self?.drivingPane == pane {
                self?.drivingPane = nil
            }
        }
        return true
    }

    func isDriving(_ pane: Pane) -> Bool {
        drivingPane == pane
    }
}

/// The views the knowledge surface can show. The first three raw values match
/// the tab ids the in-page JS (`document_view.html`) expects.
enum KGSurfaceTab: String, CaseIterable, Identifiable {
    case transcript
    case digest
    case graph
    case claims
    case timeline
    case map

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
        }
    }

    /// Tooltip copy: what the view shows and how to use it. (#1371)
    var helpText: String {
        switch self {
        case .transcript: return "Transcript — read the document's full text"
        case .digest: return "Digest — a condensed summary of the document"
        case .graph: return "Graph — entities and their connections as a network (\(KGGraphRendererFramework.selected.displayName))"
        case .claims: return "Claims — statements extracted from the document, grouped by source"
        case .timeline: return "Timeline — dated entities and events in chronological order"
        case .map: return "Map — entities laid out on a visual canvas"
        }
    }

    /// True for tabs rendered inside the shared WKWebView (#1346).
    var usesWebKit: Bool {
        switch self {
        case .transcript, .digest, .graph, .timeline: return true
        case .claims, .map: return false
        }
    }
}

/// Hosts the WebKit document KG plus the native document-scoped claims and map
/// views under one fixed toolbar.
struct DocumentKGSurface: View {
    let documentId: String
    let documentScope: InspectorClaimDocumentScope
    let libraryPath: String
    var selectedEntityId: String?
    var selectedClaimId: String?
    var activePageNumber: Int?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }
    @ObservedObject var scrollSync: DocumentScrollSyncState

    @State private var activeTab: KGSurfaceTab = .transcript
    @State private var internalSelectedEntityId: String?
    @State private var documentEntities: [Components.Schemas.KnowledgeEntity] = []
    @Environment(KGFocusState.self) private var kgFocusState
    @EnvironmentObject private var entityService: EntityServiceGenerated
    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @EnvironmentObject private var kgCurationService: KGCurationServiceGenerated

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
        .task(id: documentId) {
            documentEntities = (try? await entityService.listEntitiesForDocument(
                documentId: documentId)) ?? []
        }
    }

    @ViewBuilder
    private var content: some View {
        // Keep the WKWebView alive across tab switches via ZStack + opacity
        // so scroll position survives when the user moves between transcript/
        // digest/graph/timeline and the native claims/map tabs. (#1346)
        ZStack {
            DocumentKGWebPane(
                documentId: documentId,
                libraryPath: libraryPath,
                selectedEntityId: selectedEntityId,
                selectedClaimId: selectedClaimId,
                activeTab: activeTab.rawValue,
                activePageNumber: activePageNumber,
                pageCount: pageCount,
                onPageSelected: onPageSelected,
                scrollSync: scrollSync
            )
            .opacity(activeTab.usesWebKit ? 1 : 0)
            .allowsHitTesting(activeTab.usesWebKit)

            if !activeTab.usesWebKit {
                nativeTabContent
            }
        }
    }

    @ViewBuilder
    private var nativeTabContent: some View {
        switch activeTab {
        case .transcript, .digest, .graph, .timeline:
            EmptyView()
        case .claims:
            ScrollView {
                KnowledgeGraphInspectorSection(
                    documentId: documentId,
                    documentScope: documentScope,
                    entityService: entityService,
                    artifactService: artifactService,
                    kgCurationService: kgCurationService,
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
        case .map:
            KGMapView(
                entities: documentEntities,
                selectedEntityId: $internalSelectedEntityId,
                sourceDocumentId: documentId
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
        .help(tab.helpText)
        .accessibilityIdentifier("kgSurfaceTab-\(tab.rawValue)")
    }
}

struct FolderRealityKitSurface: View {
    let documentId: String
    @Binding var selectedNodeId: String?

    @EnvironmentObject private var documentStore: DocumentStore
    @State private var scopedDocuments: [Document] = []
    @State private var isLoading = false

    private var nodes: [MindPalaceNode] {
        scopedDocuments
            .sorted { lhs, rhs in
                (lhs.sequence ?? lhs.sortOrder, lhs.name) < (rhs.sequence ?? rhs.sortOrder, rhs.name)
            }
            .enumerated()
            .map { index, document in
                node(for: document, at: index, count: scopedDocuments.count)
            }
    }

    var body: some View {
        ZStack {
            SpatialScene3D(
                nodes: nodes,
                connections: [],
                selectedNodeId: $selectedNodeId
            )

            if isLoading {
                ProgressView()
                    .padding(12)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .task(id: documentId) {
            await loadScope()
        }
    }

    private func loadScope() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let response: DocumentListResponse = try await documentStore.api.get("/documents/\(documentId)/children")
            if !response.items.isEmpty {
                scopedDocuments = response.items
                return
            }

            if let document = try? await currentDocument(), document.docType != .folder && !document.isWorkspace {
                scopedDocuments = [document]
            } else {
                scopedDocuments = []
            }
        } catch {
            scopedDocuments = cachedScope()
        }
    }

    private func currentDocument() async throws -> Document {
        if let cached = cachedDocument() {
            return cached
        }
        return try await documentStore.api.get("/documents/\(documentId)")
    }

    private func cachedDocument() -> Document? {
        if let document = documentStore.collections.first(where: { $0.id == documentId }) {
            return document
        }
        return documentStore.currentDocuments.first { $0.id == documentId }
    }

    private func cachedScope() -> [Document] {
        let children = documentStore.currentDocuments.filter { $0.parentId == documentId }
        if !children.isEmpty {
            return children
        }
        guard let document = cachedDocument(), document.docType != .folder && !document.isWorkspace else {
            return []
        }
        return [document]
    }

    private func node(for document: Document, at index: Int, count: Int) -> MindPalaceNode {
        let point = position(for: index, count: count)
        let scale = document.docType == .page ? 1.15 : 1.35
        return MindPalaceNode(
            id: "doc-\(document.id)",
            roomId: documentId,
            nodeType: .source,
            sourceId: document.id,
            label: document.name,
            positionX: point.x,
            positionY: point.y,
            positionZ: point.z,
            scale: scale
        )
    }

    private func position(for index: Int, count: Int) -> SIMD3<Double> {
        guard count > 1 else { return .zero }
        let angle = (Double(index) / Double(count)) * Double.pi * 2
        let radius = max(1.2, sqrt(Double(count)) * 0.45)
        let layer = Double(index % 3 - 1) * 0.18
        return SIMD3<Double>(cos(angle) * radius, sin(angle) * radius, layer)
    }
}
