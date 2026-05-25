import FicheroAPIClient
import SwiftUI

// MARK: - Biography

extension EntityDetailView {
    var biographySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Biography")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Text("Reconstructed from claims")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            biographyComposedText
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    /// Build the prose paragraph. Iterates filteredClaims that have an
    /// SVO triple in metadata, substitutes a pronoun after the first
    /// subject mention, appends an italic doc-name citation per
    /// sentence. Returns Text(verbatim) so we keep AttributedString
    /// styling for the verb (italic) + citation (italic secondary).
    var biographyComposedText: Text {
        let pronoun = entityPronoun
        var first = true
        var composed = Text("")
        for claim in filteredClaims {
            guard let svo = svoOf(claim) else { continue }
            let subject = first ? svo.subject : pronoun
            first = false
            let docName = LibraryManager.shared.globalLibrary?
                .documentStore
                .currentDocuments
                .first(where: { $0.id == claim.sourceDocumentId })?
                .name
            let citation: String = {
                let parts = [docName, claim.sourcePageLabel.flatMap { "p. \($0)" }]
                    .compactMap { $0 }
                return parts.isEmpty ? "" : " [\(parts.joined(separator: ", "))]"
            }()
            composed = composed
                + Text(subject)
                + Text(" \(svo.verb) ").italic().foregroundColor(.accentColor)
                + Text(svo.object)
                + Text(citation)
                    .font(.caption2)
                    .italic()
                    .foregroundColor(.secondary)
                + Text(". ")
        }
        if first {
            return Text("No subject-verb-object claims to compose a biography from.")
                .foregroundColor(.secondary)
                .italic()
        }
        return composed
    }

    struct SVOTriple {
        let subject: String
        let verb: String
        let object: String
    }

    /// Returns the SVO triple from claim metadata, or nil if the claim
    /// has no SVO (legacy or empty-content). Mirrors the helper on
    /// ClaimSummaryCard.
    func svoOf(
        _ claim: Components.Schemas.KnowledgeClaim
    ) -> SVOTriple? {
        let subject = (claim.subjectCanonical ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let verb = (claim.predicateVerb ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let object = (claim.objectPhrase ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !subject.isEmpty, !verb.isEmpty, !object.isEmpty {
            return SVOTriple(subject: subject, verb: verb, object: object)
        }
        guard let dict = claim.metadata?.additionalProperties.value else { return nil }
        let metadataSubject = (dict["subject"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metadataVerb = (dict["verb"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metadataObject = (dict["object"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !metadataSubject.isEmpty, !metadataVerb.isEmpty, !metadataObject.isEmpty else { return nil }
        return SVOTriple(subject: metadataSubject, verb: metadataVerb, object: metadataObject)
    }

    /// Pronoun to use after the first mention. Defaults to "they" for
    /// neutrality on Person; "it" for non-persons.
    var entityPronoun: String {
        guard let type = entity.entityType else { return "it" }
        switch type {
        case .person: return "they"
        default: return "it"
        }
    }
}
