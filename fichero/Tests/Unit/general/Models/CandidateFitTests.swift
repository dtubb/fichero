import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// #5641: each MLX candidate says whether it fits this Mac ("fits", "tight", "won't fit") with the engine's reason,
/// and names a smaller build of the same model when it won't. What breaks without these: a model that won't fit is
/// offered (or hidden), the reason is lost, or Use <name> instead points at a card the list does not hold.
@MainActor
@Suite("A candidate's fit on this Mac (#5641)")
struct CandidateFitTests {
    private static func candidate(_ id: String, _ name: String, fit: String? = nil, chosen: Bool = false) -> String {
        """
        {"id":"\(id)","name":"\(name)","source":"hugging-face","offered_because":"","pin":{},"jobs":["read-a-line"],
         "open_licence":true,"size":"4 GB","measured":"","in_recipe_rules":true,"runs_where":"this_mac",
         "availability":"download","availability_words":"Download (4 GB)","chosen":\(chosen)\(fit.map { ",\"fit\":\($0)" } ?? "")}
        """
    }

    private static func list(_ items: String...) throws -> [Components.Schemas.ModelCandidate] {
        try JSONDecoder().decode([Components.Schemas.ModelCandidate].self, from: Data("[\(items.joined(separator: ","))]".utf8))
    }

    private static let big = candidate(
        "mlx:hf/mlx-community/Qwen2.5-VL-7B-Instruct-8bit@main", "Qwen2.5-VL 7B (8-bit)",
        fit: #"{"word":"won't fit","reason":"needs 11.2 GB with an 8,192-token context; this Mac has 8 GB","smaller":"Qwen2.5-VL 3B (4-bit)"}"#
    )
    private static let small = candidate(
        "mlx:hf/mlx-community/Qwen2.5-VL-3B-Instruct-4bit@main", "Qwen2.5-VL 3B (4-bit)",
        fit: #"{"word":"fits","reason":"needs 3.1 GB of this Mac's 8 GB"}"#
    )
    private static let tight = candidate(
        "mlx:hf/example/tight@main", "Tight reader",
        fit: #"{"word":"tight","reason":"needs 5.9 GB; other models are unloaded first"}"#, chosen: true
    )
    private static let kraken = candidate("kraken:catmus@1", "CATMuS Medieval")

    @Test("the engine's three words map to what a person reads, with the reason kept whole")
    func words() throws {
        let candidates = try Self.list(Self.big, Self.small, Self.tight, Self.kraken)
        let fits = try #require(CandidateFit.of(candidates[1], in: candidates))
        #expect(fits.word == .fits && fits.title == "Fits this Mac" && !fits.isGreyed)
        #expect(fits.line == "Fits this Mac: needs 3.1 GB of this Mac's 8 GB")
        let tight = try #require(CandidateFit.of(candidates[2], in: candidates))
        #expect(tight.word == .tight && tight.title == "Tight on this Mac" && !tight.isGreyed)
        let wont = try #require(CandidateFit.of(candidates[0], in: candidates))
        #expect(wont.word == .wontFit && wont.title == "Won't fit this Mac" && wont.isGreyed)
        #expect(wont.reason == "needs 11.2 GB with an 8,192-token context; this Mac has 8 GB")
        // A model that is not MLX has no fit, and says nothing about it.
        #expect(CandidateFit.of(candidates[3], in: candidates) == nil)
    }

    @Test("the smaller build is the card in the same list, by its name or its Hub repo")
    func smallerBuild() throws {
        let candidates = try Self.list(Self.big, Self.small)
        let wont = try #require(CandidateFit.of(candidates[0], in: candidates))
        #expect(wont.smaller == CandidateFit.Smaller(card: candidates[1].id, name: "Qwen2.5-VL 3B (4-bit)"))
        let byRepo = CandidateFit.make(word: "won't fit", reason: "too big", smaller: "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
                                       of: candidates[0], in: candidates)
        #expect(byRepo?.smaller?.card == candidates[1].id)
        // Named, but not in this list: nothing to press (the reason still says it).
        let alone = try Self.list(Self.big)
        #expect(CandidateFit.of(alone[0], in: alone)?.smaller == nil)
    }

    @Test("the step's card shows the fit of the model it uses now")
    func stepFit() throws {
        let candidates = try Self.list(Self.big, Self.small, Self.tight)
        #expect(CandidateFit.ofStep(card: nil, in: candidates)?.word == .tight, "the chosen candidate")
        let unchosen = try Self.list(Self.big, Self.small)
        #expect(CandidateFit.ofStep(card: unchosen[1].id, in: unchosen)?.word == .fits, "else the step's card")
        #expect(CandidateFit.ofStep(card: "kraken:catmus@1", in: unchosen) == nil)
    }

    @Test("a model that won't fit is greyed, not hidden: it cannot be ticked or used, and stays in the list")
    func greyedRow() throws {
        let candidates = try Self.list(Self.big, Self.small)
        #expect(!StageCandidateChooser.canTick(candidates[0], chosen: [], in: candidates))
        #expect(StageCandidateChooser.canTick(candidates[1], chosen: [], in: candidates))
        // Ticked before the fit was known: it can still be unticked.
        #expect(StageCandidateChooser.canTick(candidates[0], chosen: [candidates[0].id], in: candidates))
        #expect(ModelFinderCard.wontFit(candidates[0], in: candidates))
        #expect(!ModelFinderCard.wontFit(candidates[1], in: candidates))
        #expect(CandidateFitLabel.tint(.wontFit) == .secondary)
        #expect(CandidateFitLabel.tint(.tight) == .orange)
    }

    @Test("Set Up's stage page, the model finder and the step's card draw the fit with the one label")
    func oneLabelEverywhere() throws {
        let chooser = try Self.appSource("Views/Onboarding/Stages/StageCandidateChooser.swift")
        #expect(chooser.contains("CandidateFitLabel(fit: fit, useSmaller: useSmaller)"))
        let finder = try Self.appSource("Views/Models/ModelFinderView.swift")
        #expect(finder.contains("CandidateFitLabel(fit: fit, useSmaller: useSmaller)"))
        #expect(finder.contains("step.setup.useCard(smaller.card, named: smaller.name, forStep: step.id)"))
        let steps = try Self.appSource("Views/Onboarding/RecipeStepsView.swift")
        #expect(steps.contains("CandidateFitLabel(fit: fit, useSmaller: useSmaller)"))
        #expect(steps.contains("setup.useCard(smaller.card, named: smaller.name, forStep: step.id)"))
        let page = try Self.appSource("Views/Onboarding/Stages/SetupStagePage.swift")
        #expect(page.contains("candidatesOf: stepCandidates"))
        #expect(page.contains("useSmaller: useSmaller"))
        let label = try Self.appSource("Views/Models/CandidateFitLabel.swift")
        #expect(label.contains("Button(\"Use \\(smaller.name) instead\")"))
        #expect(!label.contains(".system(size:"), "semantic fonts only")
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }
}
