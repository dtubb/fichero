@testable import Fichero
import Foundation
import Testing

/// `source.onboard.step-choice-overrides-the-pick` (#4951): what a step's model menu says.
@MainActor
struct StepChoiceMenuTests {
    typealias Candidate = StepChoiceMenu.Candidate

    private func candidate(_ card: String, picked: Bool = false, recommended: Bool = false, local: Bool = true,
                           available: Bool = true, needs: [StepChoiceMenu.Need] = [], cost: Double? = nil,
                           runsOn: String? = nil, words: String? = nil) -> Candidate {
        Candidate(card: card, name: card.capitalized, runsOn: runsOn ?? (local ? "this Mac" : "the cloud"), isLocal: local,
                  isPicked: picked, isRecommended: recommended, isAvailable: available, needs: needs, costUsd: cost, costWords: words)
    }

    private func menu(by: StepChoiceMenu.ChosenBy = .setup, _ candidates: [Candidate]) -> StepChoiceMenu {
        StepChoiceMenu(step: "read-a-line", name: "Read the lines", chosenBy: by, candidates: candidates)
    }

    @Test("Set Up's pick is first and marked; the rest keep the engine's order")
    func pickFirst() {
        let model = menu([candidate("claude", local: false), candidate("kraken", picked: true, recommended: true),
                          candidate("gemini", local: false)])
        #expect(model.candidates.map(\.card) == ["kraken", "claude", "gemini"])
        #expect(model.marks(of: model.candidates[0]) == ["Set Up's pick"])
        #expect(model.marks(of: model.candidates[1]).isEmpty)
    }

    @Test("a person's choice is marked as theirs and offers taking it back; Set Up's own pick does not")
    func takeBack() {
        let mine = menu(by: .person, [candidate("kraken", recommended: true), candidate("claude", picked: true, local: false)])
        #expect(mine.offersTakeBack)
        #expect(mine.marks(of: mine.candidates[1]) == ["Your choice"])
        #expect(!menu([candidate("kraken", picked: true, recommended: true)]).offersTakeBack)
    }

    @Test("what a candidate needs is said in place, in the engine's words, and the row is kept")
    func needs() {
        let needs = [StepChoiceMenu.Need(kind: .key, words: "needs your Anthropic key"),
                     StepChoiceMenu.Need(kind: .permission, words: "needs cloud models allowed for this project")]
        let model = menu([candidate("claude", local: false, available: false, needs: needs)])
        #expect(model.needsWords(of: model.candidates[0]) == "needs your Anthropic key; needs cloud models allowed for this project")
        #expect(model.needsWords(of: candidate("kraken")) == nil)
        #expect(model.canUse(model.candidates[0]), "a choice that needs a key is kept, and the need is said")
    }

    @Test("the cost before Start is the engine's own words, never rebuilt from where it runs")
    func cost() {
        let model = menu([])
        // the engine sends runs_on "this-mac" and cost {0.0, "free on this Mac"}
        #expect(model.costText(of: candidate("kraken", cost: 0, runsOn: "this-mac", words: "free on this Mac")) == "Free on this Mac")
        #expect(model.costText(of: candidate("claude", local: false, cost: 0.4, words: "the price list")) == "the price list: About $0.40")
        #expect(model.costText(of: candidate("haiku", local: false, cost: 0.4)) == "About $0.40")
        #expect(model.costText(of: candidate("gemini", local: false)) == "Cost not known yet")
        // no words and no price: not called free
        #expect(model.costText(of: candidate("cluster", runsOn: "Maya's cluster")) == "Cost not known yet")
    }

    @Test("the one in use has no Use button")
    func inUse() {
        let model = menu([candidate("kraken", picked: true, recommended: true), candidate("claude", local: false)])
        #expect(!model.canUse(model.candidates[0]) && model.canUse(model.candidates[1]))
    }

    @Test("an unknown need kind shows its words and is not taken for a price")
    func unknownNeedKind() {
        #expect(StepChoiceMenu.Need.Kind(rawValue: "licence") == nil)
        let odd = Candidate(card: "x", name: "X", runsOn: "this-mac", isLocal: true, isPicked: false, isRecommended: false,
                            isAvailable: false, needs: [.init(kind: .other, words: "needs a licence")], costUsd: nil, costWords: nil)
        #expect(menu([]).needsWords(of: odd) == "needs a licence")
        #expect(odd.needs.first?.kind != .price)
    }
}
