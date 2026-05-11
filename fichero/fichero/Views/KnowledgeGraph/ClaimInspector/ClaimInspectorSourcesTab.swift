import FicheroAPIClient
import SwiftUI

/// Sources tab showing document references for a claim
struct ClaimInspectorSourcesTab: View {
    let claim: Components.Schemas.KnowledgeClaim

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                primarySourceSection
                if !sourceIds.isEmpty {
                    Divider()
                    sourceList
                } else if (claim.sourceExcerpt?.isEmpty ?? true) && claim.sourceDocumentId.isEmpty {
                    emptySourcesState
                }
            }
            .padding()
        }
    }

    // Primary source: the document the claim was extracted from plus
    // the verbatim excerpt the LLM lifted it from (#892/#893). Shown
    // even when sourceIds is empty — every claim has a primary
    // source_document_id, while sourceIds is the *additional* multi-
    // source list. The excerpt is the citation Daniel asked for.
    @ViewBuilder
    private var primarySourceSection: some View {
        if !claim.sourceDocumentId.isEmpty || !(claim.sourceExcerpt?.isEmpty ?? true) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Primary Source")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                if let excerpt = claim.sourceExcerpt?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !excerpt.isEmpty {
                    Text("“\(excerpt)”")
                        .font(.callout)
                        .italic()
                        .foregroundStyle(.primary)
                        .textSelection(.enabled)
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.controlBackgroundColor))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                }

                Form {
                    if !claim.sourceDocumentId.isEmpty {
                        LabeledContent("Document") {
                            Text(claim.sourceDocumentId)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                    }
                    if let page = claim.sourcePageLabel, !page.isEmpty {
                        LabeledContent("Page") {
                            Text(page)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .formStyle(.grouped)
            }
        }
    }

    private var sourceIds: [String] {
        claim.sourceIds ?? []
    }

    private var emptySourcesState: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.on.doc")
                .font(.system(size: 28))
                .foregroundColor(.secondary)

            Text("No Sources")
                .font(.subheadline)
                .fontWeight(.medium)

            Text("This claim has no linked sources")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }

    private var sourceList: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Sources")
                .font(.subheadline)
                .fontWeight(.semibold)

            if let sourceType = claim.sourceType {
                LabeledContent("Source Type") {
                    Text(sourceType.rawValue.capitalized)
                        .foregroundStyle(.secondary)
                }
            }

            if let languages = claim.sourceLanguages, !languages.isEmpty {
                LabeledContent("Languages") {
                    Text(languages.map { $0.uppercased() }.joined(separator: ", "))
                        .foregroundStyle(.secondary)
                }
            }

            Divider()

            ForEach(Array(sourceIds.enumerated()), id: \.offset) { index, sourceId in
                sourceItem(index: index, sourceId: sourceId)
            }
        }
    }

    private func sourceItem(index: Int, sourceId: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: "doc.fill")
                    .foregroundStyle(.secondary)

                Text("Source \(index + 1)")
                    .font(.subheadline)
                    .fontWeight(.medium)

                Spacer()
            }

            LabeledContent("ID") {
                Text(sourceId)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            if let pageLabel = claim.sourcePageLabels?[safe: index] {
                LabeledContent("Page") {
                    Text(pageLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Array Safe Subscript

extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
