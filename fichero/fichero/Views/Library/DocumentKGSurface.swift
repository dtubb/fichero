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
@Observable
final class DocumentScrollSyncState {
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

    /// Number key for the View-menu "Add View" shortcut (⌃⌥⌘N). Mirrors the
    /// menu order; chosen to avoid the ⌘N library-layout and ⌃⌘N sidebar-mode
    /// shortcuts. (#2032)
    var representationShortcut: Character {
        switch self {
        case .transcript: return "1"
        case .digest: return "2"
        case .graph: return "3"
        case .claims: return "4"
        case .timeline: return "5"
        case .map: return "6"
        }
    }

    /// True for tabs rendered inside the shared WKWebView (#1346).
    var usesWebKit: Bool {
        switch self {
        case .transcript, .digest, .graph, .timeline, .map: return true
        case .claims: return false
        }
    }
}

/// Equatable focused-value wrapper for the active document representation.
///
/// Publishing a raw `Binding<KGSurfaceTab>` via `focusedSceneValue` is a perf
/// footgun: a `Binding` is non-Equatable, so SwiftUI cannot dedupe it and every
/// `body` pass republishes a "new" focused value, causing per-frame
/// invalidation churn ("FocusedValue update tried to update multiple times per
/// frame"). This wrapper keys equality on the *value* (`current`) so the
/// focused value only changes when the active representation actually changes;
/// the `select` closure is excluded from equality (closures are non-Equatable).
/// (#2032)
struct DocumentRepresentationFocus: Equatable {
    let current: KGSurfaceTab
    let select: (KGSurfaceTab) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.current == rhs.current
    }
}

/// Hosts the WebKit document KG plus the native document-scoped claims view.
/// The representation switcher (Transcript/Digest/Graph/Claims/Timeline/Map)
/// lives in the View menu ("Add View"), driven via FocusedValues — not a
/// floating icon bar over the content (#2032 / reform §G).
struct DocumentKGSurface: View {
    let documentId: String
    let documentScope: InspectorClaimDocumentScope
    let libraryPath: String
    var selectedEntityId: String?
    var selectedClaimId: String?
    var activePageNumber: Int?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }
    var scrollSync: DocumentScrollSyncState
    /// Zoom level forwarded to the WebKit pane. 1.0 = 100%. (#2316)
    var zoom: Double = 1.0
    /// Active tab driven by the parent pane. When omitted the surface manages
    /// tab state internally (backward-compat for non-split usages).
    /// `= nil` is load-bearing: KnowledgeSurface call site omits these args.
    var externalActiveTab: KGSurfaceTab? = nil // swiftlint:disable:this implicit_optional_initialization
    var onTabSelected: ((KGSurfaceTab) -> Void)? = nil // swiftlint:disable:this implicit_optional_initialization

    @State private var internalActiveTab: KGSurfaceTab = .transcript
    private var activeTab: KGSurfaceTab { externalActiveTab ?? internalActiveTab }
    @Environment(KGFocusState.self) private var kgFocusState
    @EnvironmentObject private var entityService: EntityServiceGenerated
    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @EnvironmentObject private var kgCurationService: KGCurationServiceGenerated

    var body: some View {
        // The representation switcher (Transcript/Digest/Graph/Claims/Timeline/
        // Map) lives in the View menu as "Add View" items, not as a floating
        // icon bar over the content (#2032 / reform §G). Publishing `activeTab`
        // as a focused scene value lets the menu drive the selection for the
        // focused document surface.
        content
            .accessibilityIdentifier("knowledgeSurfaceContent")
            .focusedSceneValue(
                \.documentRepresentation,
                DocumentRepresentationFocus(
                    current: activeTab,
                    select: { selectTab($0) }
                )
            )
    }

    private func selectTab(_ tab: KGSurfaceTab) {
        if onTabSelected != nil {
            onTabSelected?(tab)
        } else {
            internalActiveTab = tab
        }
    }

    @ViewBuilder
    private var content: some View {
        // Keep the WKWebView alive across tab switches via ZStack + opacity
        // so scroll position survives when the user moves between transcript/
        // digest/graph/timeline/map and the native claims tab. (#1346)
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
                scrollSync: scrollSync,
                zoom: zoom
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
        case .transcript, .digest, .graph, .timeline, .map:
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
        }
    }

}
