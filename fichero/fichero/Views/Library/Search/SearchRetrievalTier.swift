import Foundation

// MARK: - The retrieval ladder (Daniel, 2026-09-02)
//
// "The tiers are a ladder — Full text / Semantic / Semantic+Graph — and the
// user must SEE what ran and why a result matched."
//
// Three rungs, in cost order, each strictly adding a leg to the one below:
//
//   Full Text      literal words only (engine `"fulltext"`)
//   Semantic       meaning + literal words, fused (engine `"hybrid"`) — DEFAULT
//   Semantic+Graph  the above plus the knowledge graph (engine `"hybrid_graph"`)
//
// The default is the middle rung, not the top: the graph leg is opt-in
// because a library with no reviewed entities has nothing to contribute and
// a library with garbage entities actively hurts (Daniel: "with no graph or
// garbage entities the graph must be OFF").
//
// The engine still accepts a pure-vector `"semantic"` that is NOT a rung —
// it drops the keyword leg, which is a strictly worse Semantic. Saved
// searches from before the ladder can carry it, so `init(requestValue:)`
// shows those on the Semantic rung rather than leaving the menu with nothing
// checked; picking that rung writes the fused `"hybrid"` back.
enum SearchRetrievalTier: String, CaseIterable, Identifiable, Sendable {
    case fulltext
    case semantic = "hybrid"
    case semanticGraph = "hybrid_graph"

    /// The rung a fresh search starts on (Daniel: "logical defaults —
    /// hybrid"). Mirrored by `ContentView.transientSearchType`.
    static let defaultTier: SearchRetrievalTier = .semantic

    /// The ladder, bottom rung first — the order the menu must render.
    static let ladder: [SearchRetrievalTier] = [.fulltext, .semantic, .semanticGraph]

    var id: String { rawValue }

    /// The value the request carries.
    var requestValue: String { rawValue }

    /// Read a request value back onto a rung, tolerating the legacy
    /// pure-vector `"semantic"` and any unknown string (which lands on the
    /// default rather than showing an unchecked menu).
    init(requestValue: String) {
        switch requestValue {
        case "fulltext": self = .fulltext
        case "hybrid_graph": self = .semanticGraph
        // Legacy pure-vector searches read as the Semantic rung; see above.
        case "hybrid", "semantic": self = .semantic
        default: self = Self.defaultTier
        }
    }

    var title: String {
        switch self {
        case .fulltext: return "Full Text"
        case .semantic: return "Semantic"
        case .semanticGraph: return "Semantic + Graph"
        }
    }

    /// What this rung actually runs — the sentence that makes the ladder
    /// legible instead of three opaque words.
    var help: String {
        switch self {
        case .fulltext:
            return "Only the words you typed, exactly as written."
        case .semantic:
            return "Meaning and the words you typed, fused into one ranking."
        case .semanticGraph:
            return "Meaning, words, and the people, places and events in your knowledge graph."
        }
    }

    /// Why the top rung is unavailable, when it is — never a dead row with
    /// no explanation.
    static let noGraphHelp =
        "This library has no reviewed knowledge-graph entities yet, so the graph leg has nothing to search."

    /// Whether the graph rung can be offered.
    ///
    /// `reviewedEntities` is the engine's `kg_entities.reviewed`. `nil` means
    /// the engine did not say — an older engine, or no search has run yet —
    /// and an unknown count keeps the rung ENABLED: refusing a tier because
    /// we failed to ask is a dishonesty of its own.
    static func graphTierAvailable(reviewedEntities: Int?) -> Bool {
        guard let reviewedEntities else { return true }
        return reviewedEntities > 0
    }
}
