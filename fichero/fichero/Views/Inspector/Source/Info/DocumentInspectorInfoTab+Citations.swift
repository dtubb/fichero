import FicheroAPIClient
import SwiftUI

// MARK: - CitationGraphPanel (#974 prep)

/// Inspector panel that surfaces citations to/from this document, backed
/// by `/api/citations/graph/document/{id}/{inbound,outbound}`.
/// "Inbound" = docs that cite this one; "Outbound" = docs this one cites.
/// Rows render the citation text + page label (when present) + a small
/// italic resolved doc name for outbound, source-doc name for inbound.
struct CitationGraphPanel: View {
    let documentId: String
    @Environment(CitationStore.self) private var store

    // Live-refresh via the per-document CitationStore (#1998): the store owns
    // the fetch + the `citation.*` change-stream reactions, so an edit in any
    // window updates this panel in place. Reading the store's properties in
    // `body` registers the @Observable dependency.
    private var inbound: [Components.Schemas.DocumentCitation] { store.inbound }
    private var outbound: [Components.Schemas.DocumentCitation] { store.outbound }
    private var citationUsages: [EntityCitationUsage] { store.usages }
    private var isLoading: Bool { store.isLoading }
    private var errorMessage: String? { store.loadError }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if isLoading && inbound.isEmpty && outbound.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Loading…").font(.caption).foregroundStyle(.secondary)
                }
            } else if inbound.isEmpty && outbound.isEmpty {
                Text("No citations recorded")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                if !outbound.isEmpty {
                    citationGroup(
                        title: "Cites \(outbound.count)",
                        items: outbound,
                        nameFor: { $0.targetDocumentId }
                    )
                }
                if !inbound.isEmpty {
                    citationGroup(
                        title: "Cited by \(inbound.count)",
                        items: inbound,
                        nameFor: { _ in nil }
                    )
                }
            }
        }
        .task(id: documentId) { await store.setScope(documentId: documentId) }
    }

    @ViewBuilder
    private func citationGroup(
        title: String,
        items: [Components.Schemas.DocumentCitation],
        nameFor: (Components.Schemas.DocumentCitation) -> String?
    ) -> some View {
        Text(title)
            .font(.caption.bold())
            .foregroundStyle(.secondary)
        LazyVStack(alignment: .leading, spacing: 4) {
            ForEach(items, id: \.id) { item in
                citationRow(item)
            }
        }
    }

    @ViewBuilder
    private func citationRow(_ item: Components.Schemas.DocumentCitation) -> some View {
        let usages = usageItems(for: item)
        VStack(alignment: .leading, spacing: 2) {
            Text(item.targetCitationText)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                if let page = item.pageLabel, !page.isEmpty {
                    Text("p. \(page)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                if let detector = item.detector, !detector.isEmpty {
                    Text(detector)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.tertiary)
                }
                Spacer(minLength: 4)
                if let confidence = item.confidence {
                    // Same self-reported signal as the claim badge (#4394).
                    let band = ConfidenceBand.band(for: confidence)
                    Text(band.badgeText)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .help(band.help)
                        .accessibilityLabel(band.help)
                }
            }
            if !usages.isEmpty {
                Text("\(usages.count) supported claim\(usages.count == 1 ? "" : "s")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let claimText = usages.first?.claim?.text, !claimText.isEmpty {
                    Text(claimText)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func usageItems(
        for citation: Components.Schemas.DocumentCitation
    ) -> [EntityCitationUsage] {
        guard let citationId = citation.id else { return [] }
        return citationUsages.filter { $0.citation.id == citationId }
    }
}
