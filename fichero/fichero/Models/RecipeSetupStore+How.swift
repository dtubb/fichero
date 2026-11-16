import FicheroAPIClient
import Foundation

/// How do you want to run this (`designer.how.*`, #6052): the answers ride on `RecipeSetupStore.how`; the options, their consequences,
/// what is greyed and why, the card the answers propose and the pre-filled "what matters" are the engine's
/// (`GET /api/recipes/questions`), asked again when an answer changes.
/// What this Mac has is shown from the derived facts and stored nowhere.
extension RecipeSetupStore {
    func toggle(place id: String) {
        how.places = Self.toggled(how.places, id)
        Task { await loadHowQuestions() }
    }

    func isTicked(place id: String) -> Bool { how.places?.contains(id) ?? false }

    func setModelKind(_ id: String) { how.modelKind = id }

    /// The person's own choice of what matters most: the engine's pre-fill stops following the places.
    func setMatters(_ id: String) {
        how.matters = id
        howMattersByHand = true
        Task { await loadHowQuestions() }
    }

    /// Ask the engine for the options and the card these answers propose; adopt its pre-filled "what matters" until the person picks.
    func loadHowQuestions() async {
        do {
            let query = Operations.QuestionsApiRecipesQuestionsGet.Input.Query(
                places: (how.places ?? []).joined(separator: ","), matters: how.matters, pages: pages)
            switch try await client.api.questionsApiRecipesQuestionsGet(query: query) {
            case .ok(let success):
                let asked = try success.body.json.how
                howQuestions = asked
                if !howMattersByHand, let prefilled = asked.defaultMatters { how.matters = prefilled }
            default:
                break
            }
        } catch {
            if error.isCancellationError { return }
            // No options: the page is simply empty; the answers it would save are unchanged.
        }
    }

    /// What this Mac and the person's accounts have, in one sentence (`designer.how.access-derived-and-confirmed`). Shown, never asked.
    func loadWhatYouHave() async {
        do {
            switch try await client.api.derivedFactsApiRecipesDerivedGet(query: .init()) {
            case .ok(let success):
                let facts = try success.body.json
                whatYouHave = Self.whatYouHave(chip: facts.mac.chip, memoryGb: facts.mac.memoryGb, keys: facts.keys,
                                               places: facts.targets.map(\.title))
            default:
                break
            }
        } catch {
            if error.isCancellationError { return }
        }
    }

    nonisolated static func whatYouHave(chip: String?, memoryGb: Int?, keys: [String], places: [String]) -> String {
        var parts: [String] = []
        if let chip {
            parts.append("This Mac: \(chip)" + (memoryGb.map { ", \($0) GB of memory" } ?? ""))
        }
        parts.append(keys.isEmpty ? "no provider keys saved" : "keys saved for \(keys.joined(separator: ", "))")
        if !places.isEmpty { parts.append("work can run on \(places.joined(separator: ", "))") }
        return parts.joined(separator: "; ") + "."
    }
}
