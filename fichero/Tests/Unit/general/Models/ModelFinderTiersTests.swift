@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `source.recipe.reader-tiers`: the finder groups the reading candidates by tier, in the engine's words, keeping the
/// engine's order inside a group.
struct ModelFinderTiersTests {
    private static func candidate(_ id: String, tier: String?, words: String?, chosen: Bool = false, cer: Double? = nil) -> String {
        var tierJSON = tier.map { #","tier":"\#($0)","tier_words":"\#(words ?? "")""# } ?? ""
        if chosen { tierJSON += #","chosen":true"# }
        if let cer { tierJSON += #","cer_measured_here":\#(cer)"# }
        return """
        {"id":"\(id)","name":"\(id)","source":"rules","offered_because":"","pin":null,"jobs":[],"open_licence":true,
         "size":"16 MB","measured":false,"in_recipe_rules":true,"runs_where":"this-mac","availability":"installed",
         "availability_words":"on this Mac"\(tierJSON)}
        """
    }

    private static func list(_ items: String...) throws -> [Components.Schemas.ModelCandidate] {
        try JSONDecoder().decode([Components.Schemas.ModelCandidate].self, from: Data("[\(items.joined(separator: ","))]".utf8))
    }

    @Test("specialist, then small vision model, then general; the engine's order kept inside a group")
    func groupsInTierOrder() throws {
        let candidates = try Self.list(
            Self.candidate("cloud", tier: "general", words: "General model"),
            Self.candidate("kraken-a", tier: "specialist", words: "Specialist line reader"),
            Self.candidate("qwen-3b", tier: "small-vlm", words: "Small vision model, on this Mac"),
            Self.candidate("kraken-b", tier: "specialist", words: "Specialist line reader")
        )
        let groups = ModelFinderTiers.groups(candidates)
        #expect(groups.map(\.title) == ["Specialist line reader", "Small vision model, on this Mac", "General model"])
        #expect(groups.map { $0.candidates.map(\.id) } == [["kraken-a", "kraken-b"], ["qwen-3b"], ["cloud"]])
    }

    @Test("a list with no tiers (another job's) is one list with no heading; an empty one has no groups")
    func noTiersNoHeadings() throws {
        let candidates = try Self.list(Self.candidate("a", tier: nil, words: nil), Self.candidate("b", tier: nil, words: nil))
        let groups = ModelFinderTiers.groups(candidates)
        #expect(groups.count == 1 && groups[0].title == nil && groups[0].candidates.map(\.id) == ["a", "b"])
        #expect(ModelFinderTiers.groups([]).isEmpty)
    }

    @Test("a chosen or measured reader heads the list, ungrouped, whatever its tier; the rest are grouped")
    func chosenAndMeasuredOverrideTheTier() throws {
        let candidates = try Self.list(
            Self.candidate("kraken-a", tier: "specialist", words: "Specialist line reader"),
            Self.candidate("cloud-measured", tier: "general", words: "General model", cer: 0.04),
            Self.candidate("qwen-chosen", tier: "small-vlm", words: "Small vision model, on this Mac", chosen: true),
            Self.candidate("kraken-b", tier: "specialist", words: "Specialist line reader")
        )
        let groups = ModelFinderTiers.groups(candidates)
        #expect(groups.first?.title == nil)
        #expect(groups.first?.candidates.map(\.id) == ["cloud-measured", "qwen-chosen"])
        #expect(groups.dropFirst().map(\.title) == ["Specialist line reader"])
        #expect(groups.dropFirst().first?.candidates.map(\.id) == ["kraken-a", "kraken-b"])
    }
}
