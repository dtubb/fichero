import FicheroAPIClient
import OSLog
import SwiftUI

private let relatedClaimsLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "RelatedClaimsPanel"
)

// MARK: - RelatedClaimsPanel (#959 KG-RAG)

/// Inspector panel that surfaces claims from across the library
/// semantically similar to claims extracted from the current document.
/// Uses `EntityService.findSimilarClaims` per doc-claim, dedups
/// by claim id, ranks by similarity, caps at 10.
///
/// Empty state means either (a) the doc has no extracted claims yet, or
/// (b) claims haven't been embedded — run "Embed claims" from the
/// Ontology Browser Tools menu.
struct RelatedClaimsPanel: View {
    let documentId: String
    /// The library that OWNS `documentId`, handed down by the inspector rather
    /// than looked up here (#4461).
    ///
    /// Both the claim fetch and the source-name resolution reached for
    /// `LibraryManager.shared.globalLibrary` — the #4306 shape, and a sibling
    /// of it in the very same Info tab. In a non-global library the panel
    /// listed claims from a database this document is not in, so it showed
    /// either nothing or another library's claims as this document's.
    let library: LibraryManager.LibraryReference?

    @State private var related: [EntityService.SimilarClaim] = []
    @State private var sourceDocNames: [String: String] = [:]
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if isLoading && related.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Searching…").font(.caption).foregroundStyle(.secondary)
                }
            } else if related.isEmpty {
                Text("No related claims")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(related) { row(for: $0) }
                }
            }
        }
        .task(id: documentId) { await load() }
    }

    @ViewBuilder
    private func row(for claim: EntityService.SimilarClaim) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(claim.text)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                if let docId = claim.sourceDocumentId,
                   let name = sourceDocNames[docId], !name.isEmpty {
                    Text(name)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                Spacer(minLength: 4)
                Text(String(format: "%.2f", max(0, min(1, claim.similarityScore))))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }

    @MainActor
    private func load() async {
        guard let library else {
            related = []
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            // 1) Fetch this doc's own claims.
            let myClaims = try await library.entityService.listClaims(
                sourceDocumentId: documentId,
                limit: 100
            )
            guard !myClaims.isEmpty else {
                related = []
                return
            }

            // 2) For each (up to 20), fetch top-3 similar; dedup by claim id;
            // keep the highest similarity per id; exclude self-doc; top 10.
            var aggregated: [String: EntityService.SimilarClaim] = [:]
            for claim in myClaims.prefix(20) {
                guard let cid = claim.id else { continue }
                let similar = try await library.entityService.findSimilarClaims(
                    claimId: cid,
                    limit: 3
                )
                for sim in similar where sim.sourceDocumentId != documentId {
                    if let existing = aggregated[sim.id] {
                        if sim.similarityScore > existing.similarityScore {
                            aggregated[sim.id] = sim
                        }
                    } else {
                        aggregated[sim.id] = sim
                    }
                }
            }
            let top = aggregated.values
                .sorted { $0.similarityScore > $1.similarityScore }
                .prefix(10)
            let result = Array(top)
            resolveSourceDocNames(for: Set(result.compactMap { $0.sourceDocumentId }))
            related = result
        } catch {
            relatedClaimsLogger.error("Related claims fetch failed: \(error.localizedDescription)")
            errorMessage = "Couldn't load related claims."
            related = []
        }
    }

    private func resolveSourceDocNames(for ids: Set<String>) {
        guard let library, !ids.isEmpty else { return }
        var resolved: [String: String] = [:]
        for id in ids {
            if let doc = library.documentStore.currentDocuments.first(where: { $0.id == id }) {
                resolved[id] = doc.name
            }
        }
        sourceDocNames = resolved
    }
}
