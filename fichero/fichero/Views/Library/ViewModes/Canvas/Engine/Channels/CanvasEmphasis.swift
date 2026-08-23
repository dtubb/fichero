import Foundation

// MARK: - Emphasis: one channel for highlight and heat (§18.2 B, §25.4 step 2)

/// WHICH cards matter right now, and how much — the canvas's answer to "pick a
/// person or place, matching cards glow, the rest dim; nothing moves".
///
/// **One channel, many producers.** A search's score-weighted heat map and an
/// entity highlight are the same question asked twice, so they are the same
/// mechanism: a producer hands over `placeable id → weight in 0…1`, and the
/// renderers turn that into strength. Anything else — a colour-by, a facet, a
/// date band — plugs in the same way rather than inventing a second visual
/// language for "these ones".
///
/// **The producer contract, stated once so nobody invents a second
/// normalisation:**
/// - keys are PLACEABLE ids, not document ids. A document card's id is
///   `SpatialLibraryProjector.nodeId(forDocument:)` (`doc:<id>`); a producer
///   working from search hits maps through it.
/// - values are 0…1, where 1 is the strongest match in the current answer.
///   Use `scoreWeighted(scores:)` rather than hand-rolling a scale.
/// - **EMPTY means NEUTRAL** — no emphasis is active and every card renders at
///   full strength. It does not mean "nothing matched". A producer with an
///   answer that happens to be empty (a search with no hits) must decide
///   whether that should dim the board or leave it alone, and say so at the
///   call site; the channel itself reads empty as "no question is being asked".
///
/// **Nothing moves.** Emphasis touches no position, no size, and no layout row
/// (R10: "colour-by / highlight never move a card"), which is also why it is
/// free of the default-grid re-flow that pitch and columns carry.
struct CanvasEmphasis: Equatable {
    /// Placeable id → weight in 0…1. Empty is neutral, NOT "nothing matched".
    private(set) var weights: [String: Double]

    /// Strength of a card that is not in the answer. Dim, not invisible: the
    /// board's shape is itself information (§18.1 defect 3), so a distribution
    /// has to stay readable — you are looking at WHERE the hits fall as much as
    /// at the hits.
    static let dimmedStrength = 0.25
    /// Strength of the WEAKEST card in the answer. Every hit stays clearly
    /// brighter than the ground, so the heat map grades matches against each
    /// other rather than fading the tail back into the dimmed rest.
    static let weakestMatchStrength = 0.6

    /// No question is being asked: every card at full strength.
    static let neutral = CanvasEmphasis(weights: [:])

    init(weights: [String: Double] = [:]) {
        self.weights = weights.compactMapValues { value in
            guard value.isFinite else { return nil }
            return min(max(value, 0), 1)
        }
    }

    /// Whether anything is being emphasised at all. False → the renderers leave
    /// every card alone, which is what makes clearing a search free.
    var isActive: Bool { !weights.isEmpty }

    /// How strongly to render one card, in 0…1. Neutral emphasis is 1 for
    /// everything; otherwise a match grades from `weakestMatchStrength` to 1 by
    /// its weight, and everything else sits at `dimmedStrength`.
    func strength(for id: String) -> Double {
        guard isActive else { return 1 }
        guard let weight = weights[id] else { return Self.dimmedStrength }
        return Self.weakestMatchStrength + (1 - Self.weakestMatchStrength) * weight
    }

    /// Weights from raw relevance scores, normalised across the VISIBLE range
    /// rather than 0…1 absolute.
    ///
    /// Absolute normalisation reads wrong on exactly the queries that work:
    /// `SearchStore.defaultMinScore` is 0.55, so a tight query returns a narrow
    /// band of high scores and every result would dim together against a scale
    /// whose bottom nothing occupies. Normalising min…max makes the heat map
    /// about how these hits compare to EACH OTHER, which is the only comparison
    /// the user can act on.
    ///
    /// A flat distribution — one hit, or every score identical — is all-full
    /// strength rather than all-zero: identical scores carry no ranking, so
    /// inventing one would be a lie in the one direction that looks confident.
    static func scoreWeighted(scores: [String: Double]) -> CanvasEmphasis {
        let usable = scores.filter { $0.value.isFinite }
        guard !usable.isEmpty else { return .neutral }
        let values = usable.values
        guard let lowest = values.min(), let highest = values.max() else { return .neutral }
        let span = highest - lowest
        guard span > 0 else { return CanvasEmphasis(weights: usable.mapValues { _ in 1 }) }
        return CanvasEmphasis(weights: usable.mapValues { ($0 - lowest) / span })
    }
}
