@testable import Fichero
import FicheroAPIClient
import Testing

/// `source.onboard.material.nothing-preselected`: nothing is chosen for the person, and the examples are not defaults.
struct MaterialPromptsTests {
    @Test func theExamplesShareNoWordAndNameNoDefault() {
        let languages = Set(MaterialPrompts.languages.dropFirst(5).split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) })
        let scripts = Set(MaterialPrompts.writingSystem.dropFirst(5).split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) })
        #expect(languages.isDisjoint(with: scripts))
        #expect(!MaterialPrompts.languages.contains("Latin") && !MaterialPrompts.writingSystem.contains("Latin"))
    }

    @MainActor @Test func aFreshSetupHasNoLanguageAndNoScriptChosen() {
        let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
        #expect(store.languages.isEmpty && store.scripts.isEmpty)
    }
}
