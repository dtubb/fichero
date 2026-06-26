import FicheroAPIClient
import Foundation
import SwiftUI

// MARK: - Mentions

extension EntityDetailView {
    struct MentionSummary: Identifiable, Equatable {
        let id: String
        let claim: Components.Schemas.KnowledgeClaim
        let dateLabel: String?
        let pageLabel: String?

        var lineLabel: String {
            let parts = [dateLabel, pageLabel]
                .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            return parts.isEmpty ? "Mentioned in source" : parts.joined(separator: " · ")
        }
    }

    var mentionsSection: some View {
        let mentions = Self.mentionSummaries(from: filteredClaims, documents: sourceDocumentsById)
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Mentions")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Text("\(mentions.count)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            if mentions.isEmpty {
                Text("No source mentions available")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(mentions) { mention in
                        Button {
                            onNavigateToSource?(mention.claim)
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "arrow.right.to.line")
                                    .font(.caption)
                                    .foregroundStyle(Color.accentColor)
                                Text(mention.lineLabel)
                                    .font(.callout)
                                    .foregroundStyle(.primary)
                                Spacer()
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .help("Jump the reading view to this source page")
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    var sourceDocumentsById: [String: Document] {
        Dictionary(
            uniqueKeysWithValues: (
                LibraryManager.shared.globalLibrary?
                    .documentStore
                    .currentDocuments
                    .map { ($0.id, $0) }
            ) ?? []
        )
    }

    static func mentionSummaries(
        from claims: [Components.Schemas.KnowledgeClaim],
        documents: [String: Document]
    ) -> [MentionSummary] {
        var mentions: [MentionSummary] = []
        var seenIds: Set<String> = []

        for claim in claims {
            let documentId = (claim.sourceDocumentId ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !documentId.isEmpty else { continue }
            let pageLabel = normalizedPageLabel(for: claim, document: documents[documentId])
            let key = [documentId, pageLabel ?? ""].joined(separator: "::")
            guard seenIds.insert(key).inserted else { continue }
            mentions.append(
                MentionSummary(
                    id: key,
                    claim: claim,
                    dateLabel: mentionDateLabel(for: claim, document: documents[documentId]),
                    pageLabel: pageLabel
                )
            )
        }

        return mentions
    }

    static func mentionDateLabel(
        for claim: Components.Schemas.KnowledgeClaim,
        document: Document?
    ) -> String? {
        let claimCandidates = [
            claim.timeStart.flatMap(formattedMentionDate),
            normalizedLabel(claim.temporalContext)
        ]
        for candidate in claimCandidates {
            if let candidate { return candidate }
        }

        guard let document else { return nil }
        let metadata = document.metadata
        let documentCandidates = [
            metadata["event_date"]?.value as? String,
            metadata["eventDate"]?.value as? String,
            metadata["date"]?.value as? String,
            metadata["display_date"]?.value as? String,
            metadata["displayDate"]?.value as? String
        ]

        for candidate in documentCandidates {
            if let formatted = formattedMentionDate(candidate) ?? normalizedLabel(candidate) {
                return formatted
            }
        }

        return nil
    }

    static func normalizedPageLabel(
        for claim: Components.Schemas.KnowledgeClaim,
        document: Document?
    ) -> String? {
        if let label = normalizedLabel(claim.sourcePageLabel) {
            return label.lowercased().hasPrefix("p.") ? label : "p. \(label)"
        }
        if let sequence = document?.sequence {
            return "p. \(sequence)"
        }
        return nil
    }

    static func formattedMentionDate(_ raw: String?) -> String? {
        guard let date = KGTemporal.parseFlexibleDate(raw) else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "EEEE, MMMM d, yyyy"
        return formatter.string(from: date)
    }

    static func normalizedLabel(_ raw: String?) -> String? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else { return nil }
        if trimmed.lowercased() == "unknown" {
            return nil
        }
        return trimmed
    }
}
