import FicheroAPIClient
import SwiftUI

extension RecipeSetupStore {
    /// The step id of the second Review the reading model (`recipes/assemble.py`, `correct-2`, #6257).
    static let secondReviewStepId = "correct-2"
    /// The stage question that says how the second model takes the first's work (`recipes/stages.py`).
    static let secondReviewModeQuestion = "second_review_mode"

    /// The engine's mode question from the stage list; nil until the stages have loaded.
    var secondReviewModeQuestion: Components.Schemas.StageQuestion? {
        stages.lazy.flatMap(\.questions).first { $0.key == Self.secondReviewModeQuestion }
    }
}

/// Beside the second Review model's picker: in turn (the default), compare, or both with a model settling the two
/// (`source.recipe.second-reviewer`, #6257). The choices and their words are the engine's question; the answer is saved
/// with the other stage answers and the plan is proposed again, so the step carries it.
struct SecondReviewModePicker: View {
    let store: RecipeSetupStore

    var body: some View {
        if let question = store.secondReviewModeQuestion {
            SetupStageQuestionField(
                question: question,
                answer: Binding(
                    get: { SetupStagePage.answer(to: question, in: store.jobAnswers) },
                    set: { store.jobAnswers[question: question.key] = $0 }
                )
            )
            .onChange(of: store.jobAnswers.other[question.key]) { Task { await store.assemble() } }
            .accessibilityIdentifier("setup.review.secondMode")
        }
    }
}

#Preview("Second review mode, in turn") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    let question = try? JSONDecoder().decode(Components.Schemas.StageQuestion.self, from: Data("""
    {"key": "second_review_mode", "ask": "How should the second model review?", "kind": "one",
     "options": [{"id": "in-turn", "title": "In turn: it reviews the first model's result"},
                 {"id": "compare", "title": "Compare: it reviews the same reading on its own"},
                 {"id": "both", "title": "Both: it reviews on its own, then settles the two"}],
     "default": "in-turn", "read_by_a_step": true}
    """.utf8))
    if let question {
        store.stages = [Components.Schemas.SetupStage(
            id: "read", title: "Read", sentence: "Reads the text.", example: "",
            exampleCredit: Components.Schemas.ExampleCredit(
                title: "Sample page", shortCredit: "Sample", licence: "CC BY 4.0",
                sourceUrl: "https://example.org", licenceUrl: "https://creativecommons.org/licenses/by/4.0/"
            ),
            jobs: ["correct"], on: true, jobsInRecipe: [], questions: [question], needs: [], sampleable: false, triedBy: .workflow
        )]
    }
    return SecondReviewModePicker(store: store)
        .padding()
        .frame(width: 420)
}
