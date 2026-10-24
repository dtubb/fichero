import Foundation
import FicheroAPIClient

/// The step menu's data and its two actions (`source.onboard.step-choice-overrides-the-pick`, #4951).
extension RecipeSetupStore {
    /// Each step of the shown plan that has a choice of model, from the engine's `StartPlan.step_choices`.
    var stepMenus: [StepChoiceMenu] {
        (startPlan?.stepChoices ?? []).map(StepChoiceMenu.init)
    }

    /// Use for This Step on a candidate of the menu; the plan is read again, since the choice changes what Start would run.
    func choose(_ candidate: StepChoiceMenu.Candidate, forStep step: String) async {
        await useCard(candidate.card, named: candidate.name, forStep: step)
        await loadStartPlan(folderId: startPlanFolderId)
    }

    /// Bring a step that is not in the plan in, by Set Up's own answer as the engine names it (`turn_on.answer` / `value`):
    /// set it, propose the recipe again with it, SAVE (PUT; the plan is read from the saved project, so a draft alone
    /// would leave the step "not in the plan"), then read the plan again.
    func turnOn(_ menu: StepChoiceMenu) async {
        guard let question = menu.turnOnAnswer, let value = menu.turnOnValue else {
            errorMessage = "The engine's way to turn this step on could not be read. Turn it on in Set Up."
            return
        }
        removedJobs.removeAll { $0 == menu.job }
        jobAnswers[question: question] = value
        // Saving a recipe the engine did not propose would PUT recipe: null over the saved one and the person's step choices
        // (## 923): a failed assemble stops here with the engine's words.
        guard await assemble(), recipe != nil, errorMessage == nil else { return }
        guard await save() else { return }
        readerChanged()
        await loadStartPlan(folderId: startPlanFolderId)
    }

    /// Take the step back to Set Up's pick (POST .../steps/use-setup-pick): the engine drops the person's override and
    /// saves the recipe; the plan is read again.
    func useSetupPick(step: String) async {
        do {
            switch try await client.api.useSetupPickForStepApiRecipesProjectStepsUseSetupPickPost(
                body: .json(.init(step: step))
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
                readerChanged()
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description ?? "The engine would not take this step back to Set Up's pick."
            case .undocumented(let code, _):
                errorMessage = "Could not take this step back to Set Up's pick (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not take this step back to Set Up's pick: \(error.localizedDescription)"
        }
        await loadStartPlan(folderId: startPlanFolderId)
    }
}
