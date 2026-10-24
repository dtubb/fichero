import FicheroAPIClient

/// The reading candidates grouped by tier (`source.recipe.reader-tiers`): specialist line readers, then small vision
/// models on this Mac, then general models. The engine's order is kept inside a group, and the person's choice and a
/// measured result stay first inside theirs. A list with no tiers (another job's) is one group with no heading.
enum ModelFinderTiers {
    struct Group: Equatable, Identifiable {
        /// Stable and distinct per group ("heads", the tier, "untiered", "all"): the title is nil for several groups.
        let id: String
        /// The tier in the engine's words, or nil for the one ungrouped list.
        let title: String?
        let candidates: [Components.Schemas.ModelCandidate]

        static func == (lhs: Group, rhs: Group) -> Bool {
            lhs.id == rhs.id && lhs.title == rhs.title && lhs.candidates.map(\.id) == rhs.candidates.map(\.id)
        }
    }

    /// The order the tiers are shown in: your cloud models first, from any provider, likely the best.
    static let order = ["cloud", "specialist", "small-vlm", "general"]

    /// A result measured on the person's pages overrides the tier (`source.recipe.reader-tiers`): those rows head the
    /// list ungrouped, in the engine's order. The chosen row does NOT move: it stays in its tier and shows its choice by
    /// a filled radio glyph and a tinted row (`source.find.chosen-row-stays-in-place`, Set Up review item 6).
    static func headsTheList(_ candidate: Components.Schemas.ModelCandidate) -> Bool {
        candidate.cerMeasuredHere != nil
    }

    static func groups(_ candidates: [Components.Schemas.ModelCandidate]) -> [Group] {
        guard candidates.contains(where: { $0.tier != nil }) else {
            return candidates.isEmpty ? [] : [Group(id: "all", title: nil, candidates: candidates)]
        }
        var out: [Group] = []
        let heads = candidates.filter(headsTheList)
        if !heads.isEmpty { out.append(Group(id: "heads", title: nil, candidates: heads)) }
        let candidates = candidates.filter { !headsTheList($0) }
        for tier in order {
            let inTier = candidates.filter { $0.tier == tier }
            if let first = inTier.first {
                out.append(Group(id: tier, title: first.tierWords, candidates: inTier))
            }
        }
        let untiered = candidates.filter { $0.tier == nil || !order.contains($0.tier ?? "") }
        if !untiered.isEmpty { out.append(Group(id: "untiered", title: nil, candidates: untiered)) }
        return out
    }
}
