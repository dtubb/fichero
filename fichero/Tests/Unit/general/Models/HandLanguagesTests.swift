@testable import Fichero
import Foundation
import Testing

/// #6118 (`source.onboard.material.which-hand`): Which hand is asked for the project's languages, from the page's own
/// answers, so a Spanish project is not offered Kurrent while the saved answers lag until Continue.
struct HandLanguagesTests {
    @Test("the languages go to the hands query as one comma-separated list, none when none are chosen")
    func languagesQuery() {
        #expect(RecipeSetupStore.handLanguages(["es"]) == "es")
        #expect(RecipeSetupStore.handLanguages(["es", "und-x-quechua"]) == "es,und-x-quechua")
        #expect(RecipeSetupStore.handLanguages([]) == nil)
    }

    @Test("loadHands sends them, and the page asks again when a language changes")
    func sentAndReasked() throws {
        let load = try AppSource.code("Models/RecipeSetupStore+Hands.swift")
        #expect(load.contains("languages: Self.handLanguages(languages)"))
        let page = try AppSource.code("Views/Onboarding/RecipeWhenWhereHandFields.swift")
        #expect(page.contains("store.languages.joined"), "a changed language re-asks the hands")
    }
}
