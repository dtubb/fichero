@testable import Fichero
import Foundation
import Testing

/// The condition-of-the-pages question (`designer.material.condition-asked`): none ticked by default, ticks toggle, and the answer is
/// saved as the engine keeps it: absent until asked, an empty list for none, the ids otherwise.
struct RecipeConditionTests {
    @Test("a tick toggles on and off, and ticking none leaves an empty list, never nil again")
    func toggling() {
        #expect(RecipeSetupStore.toggled(nil, "faded") == ["faded"])
        #expect(RecipeSetupStore.toggled(["faded"], "stains") == ["faded", "stains"])
        #expect(RecipeSetupStore.toggled(["faded"], "faded").isEmpty)
    }

    @Test("an unasked question is not saved; none ticked saves an empty list; ticks save their ids")
    func encoding() throws {
        func json(_ answers: RecipeSetupAnswers) throws -> [String: Any] {
            try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(answers)) as? [String: Any])
        }
        #expect(try json(RecipeSetupAnswers())["condition"] == nil)
        #expect((try json(RecipeSetupAnswers(condition: []))["condition"] as? [String]) == [])
        #expect((try json(RecipeSetupAnswers(condition: ["faded", "torn"]))["condition"] as? [String]) == ["faded", "torn"])
    }

    @Test("a saved project's condition reads back, and a project with none saved reads nil")
    func decoding() throws {
        let saved = try JSONDecoder().decode(RecipeSetupAnswers.self, from: Data(#"{"condition":["stains"]}"#.utf8))
        #expect(saved.condition == ["stains"])
        let none = try JSONDecoder().decode(RecipeSetupAnswers.self, from: Data("{}".utf8))
        #expect(none.condition == nil)
    }
}
