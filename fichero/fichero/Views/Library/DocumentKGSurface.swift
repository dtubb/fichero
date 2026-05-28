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
}

/// Hosts the WebKit document KG plus native document-scoped claims, timeline,
/// and map visualizations under one fixed toolbar.
struct DocumentKGSurface: View {
    let documentId: String
    let libraryPath: String
    var selectedClaimId: String?
    var activePageNumber: Int?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }

    @State private var activeTab: KGSurfaceTab = .transcript
    @State private var selectedEntityId: String?
    @EnvironmentObject private var entityService: EntityServiceGenerated

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
                    onClaimSelect: { claimId, claimText, sourceDocId, pageLabel, charStart, charEnd in
                        postClaimSource(ClaimSourceSelection(
                            claimId: claimId,
                            claimText: claimText,
                            sourceDocId: sourceDocId,
                            pageLabel: pageLabel,
                            charStart: charStart,
                            charEnd: charEnd
                        ))
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
        }
    }

    private func postClaimSource(_ selection: ClaimSourceSelection) {
        NotificationCenter.default.post(
            name: .ficheroOpenClaimSource,
            object: nil,
            userInfo: [
                "documentId": selection.sourceDocId ?? documentId,
                "claimId": selection.claimId,
                "claimText": selection.claimText as Any,
                "pageLabel": selection.pageLabel as Any,
                "charStart": selection.charStart as Any,
                "charEnd": selection.charEnd as Any
            ]
        )
    }

    private struct ClaimSourceSelection {
        let claimId: String
        let claimText: String?
        let sourceDocId: String?
        let pageLabel: String?
        let charStart: Int?
        let charEnd: Int?
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
