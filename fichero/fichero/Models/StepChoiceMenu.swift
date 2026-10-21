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
        enum Kind: Equatable { case permission, key, download, price }
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
        var id: String { card }
    }

    let step: String
    let name: String
    let chosenBy: ChosenBy
    private let given: [Candidate]

    var id: String { step }

    init(step: String, name: String, chosenBy: ChosenBy, candidates: [Candidate]) {
        self.step = step
        self.name = name
        self.chosenBy = chosenBy
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

    /// Before Start, for these pages: free on this Mac, a price when the engine has one, else said not known.
    func costText(of candidate: Candidate) -> String {
        if let cost = candidate.costUsd {
            return "About $" + cost.formatted(.number.precision(.fractionLength(2)).locale(Locale(identifier: "en_US_POSIX")))
        }
        return candidate.isLocal ? "Free, on this Mac" : "Cost not known yet"
    }

    /// A row already in use has no "Use"; every other row has one, also one that needs something (the choice is kept and
    /// the need is said, `source.onboard.step-choice-overrides-the-pick`).
    func canUse(_ candidate: Candidate) -> Bool { !candidate.isPicked }
}
