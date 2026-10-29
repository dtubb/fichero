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
