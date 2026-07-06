import FicheroAPIClient
import SwiftUI

/// The shared renderer for ONE citation (#2004, EPIC #2002).
///
/// Shown both **inline** in the inspector (below `CitationListView`) and in the
/// **detached window** torn off from it. Read-only: citations are extracted
/// data, so there is no edit/delete path (unlike `ArtifactDetailView`). The
/// inline pane passes the `usages` it has from the store so the detail can list
/// supported claims; the detached window passes none (it has no store).
struct CitationDetailView: View {
    /// The citation to render. `nil` shows the empty state.
    let item: CitationItem?

    /// Citation→claim usage rows for the supported-claims section. Empty in the
    /// detached window, which has no store.
    var usages: [EntityCitationUsage] = []

    var body: some View {
        Group {
            if let item {
                ScrollView {
                    content(for: item)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                emptyState
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder
    private func content(for item: CitationItem) -> some View {
        let citation = item.citation
        VStack(alignment: .leading, spacing: 12) {
            Label(item.direction.label, systemImage: item.direction.icon)
                .font(.caption.bold())
                .foregroundStyle(.secondary)

            Text(citation.targetCitationText)
                .font(.body)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)

            metadataGrid(for: citation)

            let claims = relatedUsages(for: citation)
            if !claims.isEmpty {
                Divider()
                Text("Supported Claims (\(claims.count))")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                ForEach(claims) { usage in
                    if let text = usage.claim?.text, !text.isEmpty {
                        Text(text)
                            .font(.callout)
                            .foregroundStyle(.primary)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.vertical, 1)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func metadataGrid(for citation: Components.Schemas.DocumentCitation) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let page = citation.pageLabel, !page.isEmpty {
                LabeledContent("Page", value: page)
            }
            if let detector = citation.detector, !detector.isEmpty {
                LabeledContent("Detector", value: detector)
            }
            if let confidence = citation.confidence {
                LabeledContent("Confidence", value: String(format: "%.2f", confidence))
            }
            if let target = citation.targetDocumentId, !target.isEmpty {
                LabeledContent("Target", value: target)
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    private func relatedUsages(
        for citation: Components.Schemas.DocumentCitation
    ) -> [EntityCitationUsage] {
        guard let citationId = citation.id else { return [] }
        return usages.filter { $0.citation.id == citationId }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "text.quote")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No citation selected")
                .font(.callout)
            Text("Pick a citation from the list to see its details.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.vertical, 32)
    }
}
