import FicheroAPIClient
import Foundation

/// Steps a purpose brings that are off until turned on (#5677, `source.onboard.correct-off-unless-a-corrector-is-here`):
/// the engine leaves Correct out when no corrector is at hand and says, in one line per step, what turning it on
/// would cost (`AssembledRecipe.left_off`). Set Up's Read page and the Start section list them, each with Turn On.
extension RecipeSetupStore {
    /// The question a stage page asks for a step that is off by default (`recipes/stages.py`): turning the step on
    /// answers it yes, so the page's question and the plan agree.
    static let askingQuestion = ["correct": "correct_with_a_second_model"]

    /// The left-off steps among `jobs` (a stage's), or all of them with nil.
    static func leftOff(_ steps: [Components.Schemas.LeftOffStep], forJobs jobs: Set<String>?) -> [Components.Schemas.LeftOffStep] {
        steps.filter { jobs?.contains($0.job) ?? true }
    }

    /// The recipe's left-off steps, a stage's or all of them.
    func leftOff(forJobs jobs: Set<String>? = nil) -> [Components.Schemas.LeftOffStep] {
        Self.leftOff(recipe?.leftOff ?? [], forJobs: jobs)
    }

    /// Turn On: ask for the step (tick it, put it back if it was taken out, and answer its question yes); the
    /// engine proposes the plan again with it, and says what it needs (a download, a cloud) as for any step.
    func turnOn(job: String) async {
        removedJobs.removeAll { $0 == job }
        if !tickedJobs.contains(job) { addedJobs.append(job) }
        if let question = Self.askingQuestion[job] { jobAnswers[question: question] = .yesNo(true) }
        await assemble()
    }
}
