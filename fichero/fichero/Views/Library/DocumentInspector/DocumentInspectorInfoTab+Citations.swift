import FicheroAPIClient
import OSLog
import SwiftUI

private let citationGraphLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "CitationGraphPanel"
)

// MARK: - CitationGraphPanel (#974 prep)

/// Inspector panel that surfaces citations to/from this document, backed
/// by `/api/citations/graph/document/{id}/{inbound,outbound}`.
/// "Inbound" = docs that cite this one; "Outbound" = docs this one cites.
/// Rows render the citation text + page label (when present) + a small
/// italic resolved doc name for outbound, source-doc name for inbound.
struct CitationGraphPanel: View {
    let documentId: String

    @State private var inbound: [Components.Schemas.DocumentCitation] = []
    @State private var outbound: [Components.Schemas.DocumentCitation] = []
    @State private var citationUsages: [EntityCitationUsage] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

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
        .task(id: documentId) { await load() }
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
                    Text(String(format: "%.2f", confidence))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
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

    @MainActor
    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let inboundTask = library.entityService.inboundCitations(forDocumentId: documentId)
            async let outboundTask = library.entityService.outboundCitations(forDocumentId: documentId)
            async let usageTask = library.entityService.citationUsages(
                sourceDocumentId: documentId
            )
            let (inb, out, usages) = try await (inboundTask, outboundTask, usageTask)
            inbound = inb
            outbound = out
            citationUsages = usages
        } catch {
            citationGraphLogger.error("Citations fetch failed: \(error.localizedDescription)")
            errorMessage = "Couldn't load citations."
            inbound = []
            outbound = []
            citationUsages = []
        }
    }
}
