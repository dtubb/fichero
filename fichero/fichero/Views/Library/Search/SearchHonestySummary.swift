import Foundation

// MARK: - What the header is allowed to say (Daniel, 2026-09-02)
//
// "The user must SEE what ran and why a result matched."
//
// The engine grew an honesty surface tonight: which legs returned rows, the
// RAW best cosine, and a `weak_semantic_only` flag it raises when nothing
// matched literally and every vector neighbour is far away. A header that
// says "45 results" over that state is a lie of confidence — the search
// found no matches and is showing you the nearest pages instead.
//
// This is pure text, deliberately: the wording is the ruling, so the wording
// is what the tests pin, without mounting a view.
enum SearchHonestySummary {
    /// The ordinary headline: a count, the query, and where it looked.
    static func countHeadline(total: Int, query: String, scopeName: String) -> String {
        "\(total) result\(total == 1 ? "" : "s") for “\(query)” in \(scopeName)"
    }

    /// The headline for a `weak_semantic_only` response: no claim of a match,
    /// and the best similarity actually achieved so the number on the rows is
    /// not the only place the weakness shows.
    static func weakHeadline(total: Int, bestSimilarity: Double?) -> String {
        let subject = total == 1 ? "the closest page" : "the \(total) closest pages"
        guard let percent = percentLabel(bestSimilarity) else {
            return "No exact matches — showing \(subject)"
        }
        return "No exact matches — showing \(subject) (closest \(percent))"
    }

    /// The one quiet line under the headline: how many rows each leg
    /// contributed, and whether the graph leg ran at all.
    ///
    /// `nil` when the engine reported no legs (an older engine) — an empty
    /// line is better than an invented "0 semantic · 0 keyword".
    static func legsLine(legs: [String: Int]?, graphLegEnabled: Bool) -> String? {
        guard let legs, !legs.isEmpty else { return nil }
        let semantic = legs["semantic"] ?? 0
        let keyword = legs["fulltext"] ?? 0
        let graph = graphLegEnabled ? "\(legs["kg"] ?? 0) graph" : "graph off"
        return "\(semantic) semantic · \(keyword) keyword · \(graph)"
    }

    /// A similarity as the UI spells percentages: whole numbers, no
    /// false precision on a cosine.
    static func percentLabel(_ value: Double?) -> String? {
        guard let value else { return nil }
        return "\(Int((value * 100).rounded()))%"
    }
}
