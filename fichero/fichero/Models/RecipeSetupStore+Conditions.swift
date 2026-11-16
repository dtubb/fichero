import FicheroAPIClient
import Foundation

/// One tick box of "What condition are the pages in?" (`designer.material.condition-asked`, #6052): the engine's id, name and the one
/// line of help saying what Fichero does about it. The app invents none.
struct ConditionOption: Identifiable, Equatable {
    let id: String
    let name: String
    let help: String
}

extension RecipeSetupStore {
    /// A tick turned on or off. Ticking none leaves an empty list (answered, none), never nil again.
    nonisolated static func toggled(_ ticked: [String]?, _ id: String) -> [String] {
        var list = ticked ?? []
        if let index = list.firstIndex(of: id) { list.remove(at: index) } else { list.append(id) }
        return list
    }

    func toggle(condition id: String) { conditions = Self.toggled(conditions, id) }

    func isTicked(condition id: String) -> Bool { conditions?.contains(id) ?? false }

    /// The tick boxes, asked of the engine once per window.
    func loadConditionOptions() async {
        guard conditionOptions.isEmpty else { return }
        do {
            switch try await client.api.questionsApiRecipesQuestionsGet() {
            case .ok(let success):
                conditionOptions = try success.body.json.conditions.map { ConditionOption(id: $0.id, name: $0.name, help: $0.help) }
            default:
                break
            }
        } catch {
            if error.isCancellationError { return }
            // No boxes: the question is simply not shown; the answers it would save are unchanged.
        }
    }
}
