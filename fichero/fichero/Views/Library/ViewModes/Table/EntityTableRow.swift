import FicheroAPIClient
import Foundation

/// The display values for one entity row in the entities library view (Phase 2 of
/// the node-model build) — name · type · #claims · authority link.
///
/// A pure value mapping. `#claims` is NOT on the entity (it comes from the shared
/// `fetchClaimCounts` map, so it is passed in), and the authority link lives in
/// `metadata["authority_links"]` (the #3757 seam) — parsed here into a short,
/// read-only label. `nonisolated`-friendly and testable off-main.
struct EntityTableRow: Equatable, Sendable {
    var name: String
    /// Human type — "Person", "Location", … from the entity_type enum.
    var type: String
    /// How many claims reference this entity (from the shared claim-count map).
    var claimCount: Int
    /// A short label for the entity's external-authority link (e.g. "WIKIDATA ·
    /// Q42"), or empty when it isn't linked. Read-only here — linking stays in the
    /// entity editor's authority sheet.
    var authority: String
    /// Where the entity sits in the human review pass — the honesty layer the
    /// demo turns on ("the machine extracts everything; the scholar curates it").
    var curation: Curation

    /// The entity curation states (`EntityCurationState`: unreviewed / verified /
    /// rejected / merged). "Blessed" is the demo word for a human-verified entity.
    enum Curation: String, Equatable, Sendable {
        case unreviewed = "Unreviewed"
        case blessed = "Blessed"
        case rejected = "Rejected"
        case merged = "Merged"
    }

    init(_ entity: Components.Schemas.KnowledgeEntity, claimCount: Int) {
        self.name = (entity.canonicalName).trimmingCharacters(in: .whitespacesAndNewlines)
        self.type = entity.entityType.map { $0.rawValue.capitalized } ?? ""
        self.claimCount = claimCount
        let meta = entity.metadata?.additionalProperties.value
        self.authority = Self.authorityLabel(fromLinks: meta?["authority_links"] as? [Any])
        self.curation = Self.curation(entity.curationState)
    }

    static func curation(_ state: Components.Schemas.EntityCurationState?) -> Curation {
        switch state {
        case .some(.verified): return .blessed
        case .some(.rejected): return .rejected
        case .some(.merged): return .merged
        default: return .unreviewed  // unreviewed / nil
        }
    }

    /// Turn the entity's `authority_links` metadata list into a short label. Kept
    /// separate from `KnowledgeEntity` so the parse is testable without building a
    /// full metadata payload. Empty list / absent → "" (never "0 links").
    static func authorityLabel(fromLinks links: [Any]?) -> String {
        guard let links, !links.isEmpty else { return "" }
        if let first = links.first as? [String: Any] {
            let authority = (first["authority"] as? String ?? "").uppercased()
            let authorityId = (first["authority_id"] as? String)
                ?? (first["authorityId"] as? String)
                ?? ""
            let label = [authority, authorityId].filter { !$0.isEmpty }.joined(separator: " · ")
            if !label.isEmpty {
                return links.count > 1 ? "\(label) +\(links.count - 1)" : label
            }
        }
        // Linked, but not in the {authority, authority_id} shape we can label —
        // still say it IS linked rather than dropping the fact.
        return links.count == 1 ? "Linked" : "\(links.count) links"
    }
}
