@testable import Fichero
import Testing

/// `source.recipe.into-what-is-a-multi-select` (#5789): the plan names one run per ticked reading level.
struct IntoWhatRunsTests {
    @Test func theAppKeepsNoRunTitlesOfItsOwn() throws {
        // The engine names the runs (`RecipeStep.run_titles`, #5795); a copy here would drift from Start's plan.
        #expect(!(try AppSource.code("Models/RecipeSetupAnswers.swift")).contains("runTitles"))
        #expect((try AppSource.code("Views/Onboarding/RecipeStepsView.swift")).contains("step.runTitles"))
    }

    @Test func aStepWithMoreThanOneRunSaysSoOnItsRow() {
        #expect(RecipeStepsView.runsLine(["As written"]) == nil, "one run needs no extra line")
        #expect(RecipeStepsView.runsLine(["As written", "Modernised"]) == "2 runs: As written · Modernised")
    }
}
