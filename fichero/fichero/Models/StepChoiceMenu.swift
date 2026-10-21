import Foundation

/// A step's model menu in Set Up (`source.onboard.step-choice-overrides-the-pick`, #4951): an OVERRIDE for a person who
/// wants a different model, not the main path. Set Up's pick stands and is shown first and marked; another candidate is
/// chosen with "Use", and "Use Set Up's pick" takes it back. A candidate that needs a key, the permission, a download or a
/// price says so in words in place; it is never hidden and never swapped for another by itself.
///
/// Plain values, read from the engine's `StepChoice` by `StepChoiceMenu.init(_:)` (the adapter lives beside the view, since
/// it reads the generated types), so what the menu says is checked without drawing it.
struct StepChoiceMenu: Equatable, Identifiable {
    enum ChosenBy: Equatable { case setup, person }

    struct Need: Equatable {
        enum Kind: Equatable { case permission, key, download, price, other }  // other: a kind this app does not know; its words still show
        let kind: Kind
        let words: String
    }

    struct Candidate: Equatable, Identifiable {
        let card: String
        let name: String
        let runsOn: String
        let isLocal: Bool
        /// In use for the step now.
        let isPicked: Bool
        /// Set Up's own pick.
        let isRecommended: Bool
        let isAvailable: Bool
        let needs: [Need]
        let costUsd: Double?
        /// The engine's own words for the figure (`cost_usd.from`: "free on this Mac", "the price list"), shown as sent.
        let costWords: String?
        var id: String { card }
    }

    let step: String
    let name: String
    let chosenBy: ChosenBy
    /// The recipe job the step is (`StepChoice.job`), for turning it on.
    let job: String
    /// False for a step the recipe does not have yet but lists so it can be found (Correct beside a Kraken reader).
    let inPlan: Bool
    /// The engine's sentence for a step that is not a plain model choice, shown as sent.
    let wording: String?
    /// Set Up's certainty bar for that step (0...1), or nil when none is chosen.
    let certaintyBar: Double?
    /// The engine's words for bringing the step in ("Have a second model check the reading, in Set Up"), nil in plan.
    let turnOnWords: String?
    /// Set Up's own answer that brings the step in, as the engine sent it (`turn_on.answer`, `turn_on.value`).
    let turnOnAnswer: String?
    let turnOnValue: StageAnswer?
    private let given: [Candidate]

    var id: String { step }

    init(step: String, name: String, chosenBy: ChosenBy, job: String? = nil, inPlan: Bool = true, wording: String? = nil,
         certaintyBar: Double? = nil, turnOnWords: String? = nil, turnOnAnswer: String? = nil, turnOnValue: StageAnswer? = nil,
         candidates: [Candidate]) {
        self.step = step
        self.name = name
        self.chosenBy = chosenBy
        self.job = job ?? step
        self.inPlan = inPlan
        self.wording = wording
        self.certaintyBar = certaintyBar
        self.turnOnWords = turnOnWords
        self.turnOnAnswer = turnOnAnswer
        self.turnOnValue = turnOnValue
        given = candidates
    }

    /// Set Up's pick first, the rest as the engine listed them.
    var candidates: [Candidate] {
        given.filter(\.isRecommended) + given.filter { !$0.isRecommended }
    }

    /// "Use Set Up's pick" is offered only while a person's choice overrides it.
    var offersTakeBack: Bool { chosenBy == .person }

    /// The marks on a row, in words: Set Up's pick, and the one in use when it is a person's choice.
    func marks(of candidate: Candidate) -> [String] {
        var marks: [String] = []
        if candidate.isRecommended { marks.append("Set Up's pick") }
        if candidate.isPicked, chosenBy == .person { marks.append("Your choice") }
        return marks
    }

    /// What the candidate needs, in the engine's words, or nil when nothing: shown in place, never hiding the row.
    func needsWords(of candidate: Candidate) -> String? {
        let words = candidate.needs.map(\.words).filter { !$0.isEmpty }
        return words.isEmpty ? nil : words.joined(separator: "; ")
    }

    /// Before Start, for these pages: the engine's words for the figure, as sent ("free on this Mac"), never rebuilt here
    /// from where it runs; with a price and no words, the price; else said not known.
    func costText(of candidate: Candidate) -> String {
        let words = candidate.costWords?.trimmingCharacters(in: .whitespaces) ?? ""
        if !words.isEmpty {
            if let cost = candidate.costUsd, cost > 0 { return words + ": " + Self.dollars(cost) }
            return words.prefix(1).uppercased() + words.dropFirst()
        }
        if let cost = candidate.costUsd { return Self.dollars(cost) }
        return "Cost not known yet"
    }

    private static func dollars(_ cost: Double) -> String {
        "About $" + cost.formatted(.number.precision(.fractionLength(2)).locale(Locale(identifier: "en_US_POSIX")))
    }

    /// A row already in use has no "Use"; every other row has one, also one that needs something (the choice is kept and
    /// the need is said, `source.onboard.step-choice-overrides-the-pick`).
    /// A step not in the plan has no "Use" (the engine would refuse it, 422): it offers the engine's turn-on words instead.
    func canUse(_ candidate: Candidate) -> Bool { inPlan && !candidate.isPicked }

    /// The turn-on button's words, only for a step that is not in the plan and has a way in.
    var turnOnTitle: String? { inPlan ? nil : turnOnWords }

    /// "Lines under 80% sure are corrected" for the bar; nil when none is chosen.
    var certaintyBarText: String? {
        certaintyBar.map { "Lines the reader is under \(Int(($0 * 100).rounded()))% sure of are corrected" }
    }
}
