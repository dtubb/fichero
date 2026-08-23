import SwiftUI

// The Knowledge tab — the KG exploration sub-mode switcher plus the set-apart
// Digest section, and the helpers that clamp `activeTab` to a valid selection.
// Split out of ReadingPaneView to keep the type body under the SwiftLint threshold.
extension ReadingPaneView {
    /// Knowledge tab — explore what we know. A native sub-mode switcher for the
    /// exploration views (Graph, Claims, Timeline, Map — Timeline/Map are
    /// sub-modes, not top tabs, #3504) sits alongside a set-apart **Digest**
    /// section, so the digest reads as a distinct section rather than a co-equal
    /// sub-mode or its own tab (#3505/#3512, design Q1). Digest is NOT an AI
    /// summary — it renders every claim grouped by entity (see below).
    /// Transcript is excluded — it lives in the Page tab. The surface is the
    /// shared `DocumentKGSurface` WebKit view, driven by `activeTab`.
    /// NO inner sub-mode bar (Daniel, 2026-08-23 / S2): the PaneHead's lens
    /// selector is the ONE switch — Entities/Claims/Graph/Timeline/Map and
    /// Statements (the digest) are all lenses there. The old segmented picker
    /// + Digest button rendered a second tab bar and listed Statements twice.
    @ViewBuilder
    var knowledgeTabContent: some View {
        surfaceView(tab: effectiveKnowledgeTab)
    }

    /// The KG exploration sub-modes in the Knowledge tab. Transcript is a Page
    /// concern; Digest is a separate section (below). Entities/Claims are native
    /// lists; Graph/Timeline/Map are the WebKit visualization views (#3503).
    static let knowledgeVizModes: [KGSurfaceTab] = [.entities, .claims, .graph, .timeline, .map]

    /// The KG tab actually shown: a valid viz sub-mode or the digest section;
    /// anything else (e.g. a stale `.transcript`) falls back to Entities.
    private var effectiveKnowledgeTab: KGSurfaceTab {
        (Self.knowledgeVizModes.contains(activeTab) || activeTab == .digest) ? activeTab : .entities
    }
}
