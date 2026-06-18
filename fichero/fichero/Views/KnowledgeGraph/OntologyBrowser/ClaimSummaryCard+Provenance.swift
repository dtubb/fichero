import FicheroAPIClient
import SwiftUI

// MARK: - ClaimSummaryCard provenance badges (data)

extension ClaimSummaryCard {
    struct ProvenanceBadge: Equatable {
        let label: String
        let tint: Color
    }

    /// Plain-text provenance chips (no emoji — #1864) describing where a
    /// claim came from: who authored it, the quotation kind, the
    /// confidence source, and corroboration count.
    static func provenanceBadges(for claim: Components.Schemas.KnowledgeClaim) -> [ProvenanceBadge] {
        let metadata = Dictionary(
            uniqueKeysWithValues: (claim.metadata?.additionalProperties.value ?? [:]).map { key, value in
                (key, value as Any)
            }
        )
        return [
            createdByBadge(for: claim),
            quotationKindBadge(from: metadata),
            confidenceSourceBadge(for: claim, metadata: metadata),
            corroborationBadge(from: metadata)
        ].compactMap { $0 }
    }

    private static func createdByBadge(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> ProvenanceBadge? {
        guard let createdByRaw = claim.createdBy?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased(),
            !createdByRaw.isEmpty
        else { return nil }
        if ["human", "user", "manual", "researcher", "editor", "curator", "cli"]
            .contains(createdByRaw) {
            return ProvenanceBadge(label: "Human", tint: .orange)
        }
        if createdByRaw.contains("extract")
            || createdByRaw.contains("agent")
            || createdByRaw.contains("llm")
            || createdByRaw.contains("ai") {
            return ProvenanceBadge(label: "AI", tint: .purple)
        }
        return nil
    }

    private static func quotationKindBadge(
        from metadata: [String: Any]
    ) -> ProvenanceBadge? {
        guard let raw = (
            metadata["quotation_kind"] as? String
            ?? metadata["quotationKind"] as? String
        )?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            !raw.isEmpty
        else { return nil }
        let label: String
        switch raw {
        case "verbatim": label = "Verbatim"
        case "paraphrase": label = "Paraphrase"
        case "summary": label = "Summary"
        default: label = raw.replacingOccurrences(of: "_", with: " ").capitalized
        }
        return ProvenanceBadge(label: label, tint: .indigo)
    }

    private static func confidenceSourceBadge(
        for claim: Components.Schemas.KnowledgeClaim,
        metadata: [String: Any]
    ) -> ProvenanceBadge? {
        guard let raw = (
            claim.confidenceSource
            ?? metadata["confidence_source"] as? String
            ?? metadata["confidenceSource"] as? String
        )?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            !raw.isEmpty
        else { return nil }
        let label: String
        switch raw {
        case "llm_logprob": label = "LLM"
        case "heuristic": label = "Heuristic"
        case "human_review": label = "Human-reviewed"
        case "corroboration": label = "Corroborated"
        case "default": label = "Default"
        default: label = raw.replacingOccurrences(of: "_", with: " ").capitalized
        }
        return ProvenanceBadge(label: label, tint: .teal)
    }

    private static func corroborationBadge(
        from metadata: [String: Any]
    ) -> ProvenanceBadge? {
        let count = (
            metadata["corroboration_count"] as? Int
            ?? Int(metadata["corroboration_count"] as? String ?? "")
            ?? metadata["corroborationCount"] as? Int
            ?? Int(metadata["corroborationCount"] as? String ?? "")
        )
        guard let count, count > 0 else { return nil }
        return ProvenanceBadge(label: "\(count)x corroborated", tint: .green)
    }
}
