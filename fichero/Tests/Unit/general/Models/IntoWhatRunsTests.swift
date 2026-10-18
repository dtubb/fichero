@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `source.recipe.into-what-is-a-multi-select` (#5789): the plan names one run per ticked reading level.
struct IntoWhatRunsTests {
    /// The engine names the Normalise step's runs (`RecipeStep.run_titles`, #5795); the row shows them as sent.
    @MainActor @Test func theRowShowsTheRunsTheEngineNamed() throws {
        func step(_ runTitles: String) throws -> Components.Schemas.RecipeStep {
            let json = #"{"id":"normalise","job":"translate-transliterate-normalise","run_titles":\#(runTitles)}"#
            return try JSONDecoder().decode(Components.Schemas.RecipeStep.self, from: Data(json.utf8))
        }
        let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
        let two = RecipeStepsView.lines(for: try step(#"["As written","Translation into Spanish"]"#), store: store, inSetup: true)
        #expect(two.contains(.runs("2 runs: As written · Translation into Spanish")))
        let one = RecipeStepsView.lines(for: try step(#"["Abbreviations expanded"]"#), store: store, inSetup: true)
        #expect(!one.contains { if case .runs = $0 { true } else { false } }, "one run needs no extra line")
    }

    @Test func aStepWithMoreThanOneRunSaysSoOnItsRow() {
        #expect(RecipeStepsView.runsLine(["As written"]) == nil, "one run needs no extra line")
        #expect(RecipeStepsView.runsLine(["As written", "Modernised"]) == "2 runs: As written · Modernised")
    }
}
