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

    /// `source.disagree.built-in-needs-second-reader` (#5812): a built-in step names its readers or says it needs a
    /// second one; it never says it has no model and never offers Choose a model.
    @MainActor @Test func aBuiltInComparisonNeverSaysItHasNoModel() throws {
        func step(_ extra: String) throws -> Components.Schemas.RecipeStep {
            let json = #"{"id":"d","job":"find-where-readers-disagree","built_in":true,\#(extra)}"#
            return try JSONDecoder().decode(Components.Schemas.RecipeStep.self, from: Data(json.utf8))
        }
        let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
        let two = RecipeStepsView.lines(for: try step(#""reasons":["Compares Kraken with Apple Vision"],"compares":["Kraken","Apple Vision"]"#),
                                        store: store, inSetup: true)
        #expect(two.contains(.place("Built in · Compares Kraken with Apple Vision", cloud: false)))
        let one = RecipeStepsView.lines(for: try step(#""needs":"needs a second reader: tick one in Read""#), store: store, inSetup: true)
        #expect(one.contains(.place("needs a second reader: tick one in Read", cloud: false)))
        for lines in [two, one] {
            #expect(!lines.contains { if case .problem = $0 { true } else if case .fix = $0 { true } else { false } })
        }
    }

    @Test func aStepWithMoreThanOneRunSaysSoOnItsRow() {
        #expect(RecipeStepsView.runsLine(["As written"]) == nil, "one run needs no extra line")
        #expect(RecipeStepsView.runsLine(["As written", "Modernised"]) == "2 runs: As written · Modernised")
    }
}
