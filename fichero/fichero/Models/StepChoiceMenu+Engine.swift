import FicheroAPIClient
import Foundation

/// The engine's `StepChoice` (`StartPlan.step_choices`, `source.onboard.step-candidates-on-the-plan`) as the menu's values.
extension StepChoiceMenu {
    init(_ choice: Components.Schemas.StepChoice) {
        self.init(
            step: choice.step, name: choice.name, chosenBy: choice.chosenBy.rawValue == "person" ? .person : .setup,
            candidates: choice.candidates.map { candidate in
                Candidate(
                    card: candidate.card, name: candidate.name, runsOn: candidate.runsOn, isLocal: candidate.local,
                    isPicked: candidate.picked, isRecommended: candidate.recommended, isAvailable: candidate.available,
                    needs: (candidate.needs ?? []).map { Need(kind: Need.Kind(rawValue: $0.kind.rawValue) ?? .other, words: $0.words) },
                    costUsd: candidate.costUsd?.value, costWords: candidate.costUsd?.from)
            })
    }
}

extension StepChoiceMenu.Need.Kind {
    /// nil for a kind this app does not know.
    init?(rawValue: String) {
        switch rawValue {
        case "permission": self = .permission
        case "key": self = .key
        case "download": self = .download
        case "price": self = .price
        default: return nil
        }
    }
}
