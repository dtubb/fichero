import SwiftUI
import FicheroAPIClient

/// Tab selection for ClaimInspector
enum ClaimInspectorTab: String, CaseIterable, Identifiable {
    case details = "Details"
    case sources = "Sources"
    case links = "Links"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .details: return "text.alignleft"
        case .sources: return "doc.on.doc"
        case .links: return "link"
        }
    }
}

/// Inspector panel for displaying and editing a knowledge claim
struct ClaimInspector: View {
    let claim: Components.Schemas.KnowledgeClaim?

    @SceneStorage("ClaimInspector.selectedTab") private var selectedTab: ClaimInspectorTab = .details

    var body: some View {
        Group {
            if let c = claim {
                claimDetail(c)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 280, maxWidth: .infinity)
    }

    // MARK: - Claim Detail

    private func claimDetail(_ c: Components.Schemas.KnowledgeClaim) -> some View {
        VStack(spacing: 0) {
            tabBar

            Divider()

            switch selectedTab {
            case .details:
                ClaimInspectorDetailsTab(claim: c)
            case .sources:
                ClaimInspectorSourcesTab(claim: c)
            case .links:
                ClaimInspectorLinksTab(claim: c)
            }
        }
    }

    private var tabBar: some View {
        HStack(spacing: 2) {
            ForEach(ClaimInspectorTab.allCases) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    Image(systemName: tab.icon)
                        .font(Font.system(size: 14, weight: .regular))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(selectedTab == tab
                              ? Color.accentColor.opacity(0.15)
                              : Color.clear)
                )
                .foregroundStyle(selectedTab == tab ? Color.accentColor : Color.secondary)
                .help(tab.rawValue)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "text.badge.checkmark")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Claim Selected")
                .font(.headline)

            Text("Select a claim to view details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

// MARK: - Preview

#Preview("Empty") {
    ClaimInspector(claim: nil)
        .frame(width: 300, height: 400)
}

#Preview("With Claim") {
    let claim = Components.Schemas.KnowledgeClaim(
        id: "claim-1",
        text: "The Treaty of Westphalia established the principle of state sovereignty in European affairs.",
        sourceDocumentId: "doc-1",
        sourceSegmentId: nil,
        sourcePageLabel: "42",
        sourceExcerpt: "The treaty was signed in 1648...",
        sourceRef: nil,
        sourceType: .document,
        sourceIds: ["doc-1"],
        sourcePageLabels: ["42"],
        sourceLanguages: ["en"],
        claimType: .fact,
        epistemicStatus: .confirmed,
        entityIds: ["entity-1", "entity-2"],
        curationState: .approved,
        confidence: 0.95,
        predictedConfidence: nil,
        predictedBy: nil,
        prediction: nil,
        language: "en",
        metadata: nil,
        createdBy: "human",
        createdAt: ISO8601DateFormatter().date(from: "2026-01-15T10:30:00Z")!,
        updatedAt: ISO8601DateFormatter().date(from: "2026-01-15T10:30:00Z")!
    )

    ClaimInspector(claim: claim)
        .frame(width: 300, height: 500)
}
