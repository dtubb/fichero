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
    @ViewBuilder
    var knowledgeTabContent: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Picker("Knowledge view", selection: knowledgeVizBinding) {
                    ForEach(Self.knowledgeVizModes) { mode in
                        Label(mode.title, systemImage: mode.icon)
                            .help(mode.helpText)
                            .tag(mode as KGSurfaceTab?)
                    }
                }
                .pickerStyle(.segmented)
                .labelStyle(.iconOnly)
                .fixedSize()
                .accessibilityIdentifier("readerKnowledgeSubMode")

                Spacer(minLength: 8)

                // Digest: claims grouped by the entity they are about, with page
                // labels + source excerpts (document_view.html renderDigest). It is
                // NOT an AI summary and involves no LLM call — the old comment and
                // help text said otherwise, which is why nobody could say what it
                // was (the user: "Digest — not sure what that is", #3765 Q2). Set
                // apart from the exploration sub-modes (design Q1 / #3512).
                Divider().frame(height: 16)
                Button {
                    activeTab = .digest
                } label: {
                    Label(KGSurfaceTab.digest.title, systemImage: KGSurfaceTab.digest.icon)
                }
                .buttonStyle(.borderless)
                .labelStyle(.titleAndIcon)
                .font(.caption)
                .foregroundStyle(activeTab == .digest ? Color.accentColor : .secondary)
                .help(KGSurfaceTab.digest.helpText)
                .accessibilityIdentifier("readerKnowledgeDigest")
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)

            Divider()

            surfaceView(tab: effectiveKnowledgeTab)
        }
    }

    /// The KG exploration sub-modes in the Knowledge tab. Transcript is a Page
    /// concern; Digest is a separate section (below). Entities/Claims are native
    /// lists; Graph/Timeline/Map are the WebKit visualization views (#3503).
    static let knowledgeVizModes: [KGSurfaceTab] = [.entities, .claims, .graph, .timeline, .map]

    /// Binds the exploration sub-mode picker to `activeTab`. When the Digest
    /// section is active (`activeTab == .digest`) the selection is nil so no viz
    /// segment is highlighted; any stale non-knowledge value clamps to Entities.
    private var knowledgeVizBinding: Binding<KGSurfaceTab?> {
        Binding(
            get: {
                if Self.knowledgeVizModes.contains(activeTab) { return activeTab }
                return activeTab == .digest ? nil : .entities
            },
            set: { if let mode = $0 { activeTab = mode } }
        )
    }

    /// The KG tab actually shown: a valid viz sub-mode or the digest section;
    /// anything else (e.g. a stale `.transcript`) falls back to Entities.
    private var effectiveKnowledgeTab: KGSurfaceTab {
        (Self.knowledgeVizModes.contains(activeTab) || activeTab == .digest) ? activeTab : .entities
    }
}
