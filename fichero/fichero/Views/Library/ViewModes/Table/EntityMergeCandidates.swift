import FicheroAPIClient

/// The entities a table Merge offers, the one carrying the most claims first: that is the
/// survivor the sheet proposes, and the person can keep another (#5129). Entities without an id
/// cannot be merged and are left out. File scope so Swift Testing can call it off-main.
func mergeCandidatesRichestFirst(
    _ entities: [Components.Schemas.KnowledgeEntity],
    claimCounts: [String: Int]
) -> [Components.Schemas.KnowledgeEntity] {
    entities.filter { $0.id != nil }.enumerated().sorted { lhs, rhs in
        let left = claimCounts[lhs.element.id ?? ""] ?? 0
        let right = claimCounts[rhs.element.id ?? ""] ?? 0
        return left != right ? left > right : lhs.offset < rhs.offset
    }.map(\.element)
}
