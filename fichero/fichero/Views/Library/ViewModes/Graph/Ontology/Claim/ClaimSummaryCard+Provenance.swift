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
            corroborationBadge(from: metadata),
            multiSourceBadge(for: claim)
        ].compactMap { $0 }
    }

    /// "N places" when the multi-source layer holds more than the primary
    /// attestation (#4672) — visible collapsed, so a statement attested in
    /// two places says so before anyone opens the drawer. The drawer's
    /// attestation list is where each place becomes a door.
    private static func multiSourceBadge(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> ProvenanceBadge? {
        let count = attestations(for: claim).count
        guard count > 1 else { return nil }
        return ProvenanceBadge(label: "\(count) places", tint: .indigo)
    }

    /// #4868 (`hermeneutic.claim-provenance-badge-reads-the-right-field`,
    /// `kg.claim.provenance-kind-is-server-stated`): reads `provenanceKind`
    /// and NOTHING else. The old version guessed from `createdBy` by
    /// substring — a user literally named "daniel" read as AI (contains
    /// none of the trigger words, so it actually fell through to no badge;
    /// the real failure was the OTHER direction: every machine-extracted
    /// claim was stored with `created_by: "human"` until tonight's engine
    /// fix, so the substring check could never have told them apart even
    /// with a name that DID collide). `provenanceKind` is set by the SERVER
    /// at write time and derived for rows written before the field existed
    /// — the app never guesses, it only reads. `nil` is treated exactly
    /// like `.unknown`: never shown as Human or AI.
    private static func createdByBadge(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> ProvenanceBadge? {
        switch claim.provenanceKind {
        case .human:
            return ProvenanceBadge(label: "Human", tint: .orange)
        case .workflow:
            // Machine-made — `provider`/`model` say whether it was a
            // language model or spaCy, shown beside the badge when present
            // rather than folded into one ambiguous "AI" label.
            let detail = [claim.provider, claim.model]
                .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            let suffix = detail.isEmpty ? "" : " (\(detail.joined(separator: " · ")))"
            return ProvenanceBadge(label: "Workflow\(suffix)", tint: .purple)
        case .agent:
            return ProvenanceBadge(label: "Agent", tint: .purple)
        case .externalImport:
            // Names the source — `createdBy` carries it (e.g. "wikidata").
            let source = claim.createdBy?.trimmingCharacters(in: .whitespacesAndNewlines)
            let label = (source?.isEmpty == false) ? source! : "External import"
            return ProvenanceBadge(label: label, tint: .blue)
        case .unknown, nil:
            return ProvenanceBadge(label: "Unknown origin", tint: .gray)
        @unknown default:
            return ProvenanceBadge(label: "Unknown origin", tint: .gray)
        }
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
