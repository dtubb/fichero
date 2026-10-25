import FicheroAPIClient
import Foundation

// Which hand (section 7d, #5668): the engine's curated hands, read by the store, never by the view.
extension RecipeSetupStore {
    /// The answer "Not sure" to Which hand (`HandList.not_sure`).
    static let notSureHand = "not-sure"

    /// The curated hands for the first script chosen and the period, as the engine keeps them; re-asked when either
    /// changes (`source.onboard.material.which-hand`).
    func loadHands() async {
        let script = scripts.first ?? "Latn"
        let when = period.trimmingCharacters(in: .whitespaces)
        do {
            if case .ok(let success) = try await client.api.listHandsApiRecipesHandsGet(
                query: .init(script: script, period: when.isEmpty ? nil : when, languages: Self.handLanguages(languages))
            ) {
                handOptions = try success.body.json.items
            }
        } catch {
            if error.isCancellationError { return }
            handOptions = []
        }
    }

    /// The project's languages as the hands query asks them (#6118): the engine leaves out a hand particular to others
    /// (Kurrent for a Spanish project). Sent from the page's own answers: the saved ones lag until Continue.
    nonisolated static func handLanguages(_ languages: [String]) -> String? {
        languages.isEmpty ? nil : languages.joined(separator: ",")
    }

    /// Tick or untick a hand. "Not sure" stands alone: it clears the others, and a hand ticked clears it.
    func toggle(hand id: String) {
        if hands.contains(id) {
            hands.removeAll { $0 == id }
        } else if id == Self.notSureHand {
            hands = [id]
        } else {
            hands.removeAll { $0 == Self.notSureHand }
            hands.append(id)
        }
    }
}
