@testable import Fichero
import Testing

/// `source.recipe.into-what-is-a-multi-select` (#5789): the plan names one run per ticked reading level.
struct IntoWhatRunsTests {
    @Test func theNormaliseStepNamesOneRunPerTickedLevelAndTranslation() {
        var answers = RecipeSetupAnswers.JobAnswers()
        #expect(answers.runTitles == ["Abbreviations expanded"], "the default is one run")
        answers.set(level: "as_written", true)
        answers.translation = "es"
        #expect(answers.runTitles == ["As written", "Abbreviations expanded", "Translation into Spanish"])
    }

    @Test func aStepWithMoreThanOneRunSaysSoOnItsRow() {
        #expect(RecipeStepsView.runsLine(["As written"]) == nil, "one run needs no extra line")
        #expect(RecipeStepsView.runsLine(["As written", "Modernised"]) == "2 runs: As written · Modernised")
    }
}
