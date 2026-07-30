import Foundation

/// How many hits a search returned, per kind (#4403).
///
/// The header counts ALL of these; the grid only ever renders the document
/// leg. That gap is the bug: a query matching six artifacts and no documents
/// produced "3 results for 'Asprilla'" over an empty grid, and the grid then
/// explained itself with the prompt for a completely different situation.
struct SearchHitCounts: Equatable {
    var documents: Int = 0
    var artifacts: Int = 0
    var entities: Int = 0
    var claims: Int = 0

    /// What the header reports.
    var total: Int { documents + artifacts + entities + claims }

    /// Hits the document grid structurally cannot show.
    var nonDocument: Int { artifacts + entities + claims }

    /// The kinds that matched, named, longest-first so the sentence reads
    /// naturally: "6 artifacts and 2 entities".
    var nonDocumentSummary: String {
        var parts: [String] = []
        if artifacts > 0 { parts.append("\(artifacts) artifact\(artifacts == 1 ? "" : "s")") }
        if entities > 0 { parts.append("\(entities) entit\(entities == 1 ? "y" : "ies")") }
        if claims > 0 { parts.append("\(claims) claim\(claims == 1 ? "" : "s")") }
        switch parts.count {
        case 0: return ""
        case 1: return parts[0]
        case 2: return "\(parts[0]) and \(parts[1])"
        default: return parts.dropLast().joined(separator: ", ") + ", and " + (parts.last ?? "")
        }
    }
}

/// Why the library body has no rows, and what it is allowed to say (#4403).
///
/// The defect this replaces: `emptyState` branched on the local FILTER text
/// and, finding it empty, fell through to "Select a collection to view
/// documents" — the prompt for having chosen no collection at all. During an
/// active search that sentence is simply false, and it appeared directly under
/// a header reading "3 results for 'Asprilla'". Two halves of one screen
/// deriving "is there anything here?" from different state, which is the same
/// disagreement #4380 removed from the connection surfaces.
///
/// Pure, so the load-bearing invariant is assertable: **whenever a search is
/// active, the body talks about the search.** It can never fall back to a
/// collection prompt, whatever the counts are.
enum LibraryEmptyReason: Equatable {
    /// No collection chosen — the ONLY case that may say so.
    case noCollectionSelected
    /// An entity collection with nothing in it.
    case noEntitiesInCollection
    /// The local filter bar hid everything.
    case filteredOut(query: String)
    /// A search ran and matched nothing anywhere.
    case searchFoundNothing(query: String)
    /// A search matched, but only kinds the document grid cannot render.
    /// The #4403 case: the header is right, the grid is empty, and the body
    /// has to explain the difference instead of contradicting it.
    case searchMatchedOtherKinds(query: String, counts: SearchHitCounts)

    var title: String {
        switch self {
        case .noCollectionSelected: return "No Documents"
        case .noEntitiesInCollection: return "No Entities"
        case .filteredOut: return "No Matches"
        case .searchFoundNothing: return "No Results"
        case .searchMatchedOtherKinds: return "No Matching Documents"
        }
    }

    var message: String {
        switch self {
        case .noCollectionSelected:
            return "Select a collection to view documents"
        case .noEntitiesInCollection:
            return "Select an entity to inspect it."
        case .filteredOut(let query):
            return "No results for \"\(query)\""
        case .searchFoundNothing(let query):
            return "No results for \"\(query)\""
        case .searchMatchedOtherKinds(let query, let counts):
            // Says what DID match, so the header's count is explained rather
            // than contradicted, and points at where those hits are shown.
            return "No documents match \"\(query)\", but \(counts.nonDocumentSummary) did — see the groups above."
        }
    }

    /// The filter escape hatch belongs only to a filter.
    var offersClearFilter: Bool {
        if case .filteredOut = self { return true }
        return false
    }

    var systemImage: String {
        switch self {
        case .noEntitiesInCollection: return "person.3.sequence"
        default: return "doc.text.magnifyingglass"
        }
    }

    /// Precedence: an active search outranks everything, because while one is
    /// running the body's job is to explain the search — never the collection.
    static func resolve(
        isShowingEntities: Bool,
        filterText: String,
        activeSearchQuery: String?,
        hitCounts: SearchHitCounts
    ) -> LibraryEmptyReason {
        if let query = activeSearchQuery, !query.isEmpty {
            if hitCounts.nonDocument > 0 {
                return .searchMatchedOtherKinds(query: query, counts: hitCounts)
            }
            // Includes the shouldn't-happen case of document hits with an empty
            // grid: still a search answer, never a collection prompt.
            return .searchFoundNothing(query: query)
        }
        if !filterText.isEmpty {
            return .filteredOut(query: filterText)
        }
        if isShowingEntities {
            return .noEntitiesInCollection
        }
        return .noCollectionSelected
    }
}
