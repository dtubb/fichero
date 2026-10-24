import FicheroAPIClient
import Foundation

// The engine sets a step's reader (Use Instead, Use for This Step, a free place): the changed steps replace theirs in
// place (moved out of the class body for its length; `choiceRevision` is internal to the module for it).
extension RecipeSetupStore {
    /// Use the installed model the plan offers instead of a download (#5583,
    /// `source.onboard.auto.installed-model-first`): the engine sets it on the steps that waited for
    /// the download and saves the recipe; the changed steps replace theirs in place, and Ready reads
    /// the plan again because the recipe changed.
    /// A step's reader changed by any road (Use for This Step, Use Instead, back to Set Up's pick, a step turned on): the
    /// one place the revision the finder and the stage page read candidates again on is moved (## 1097).
    func readerChanged() { choiceRevision += 1 }

    func useInstead(_ download: Components.Schemas.StartDownload,
                    _ installed: Components.Schemas.StartInstead) async {
        do {
            switch try await client.api.useInstalledInsteadApiRecipesProjectStartUseInsteadPost(
                body: .json(.init(model: download.model, card: installed.card))
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
                readerChanged()
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? "The engine would not use \(installed.name)."
            case .undocumented(let code, _):
                errorMessage = "Could not use \(installed.name) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not use \(installed.name): \(error.localizedDescription)"
        }
    }

    /// Use for This Step on any candidate the finder lists (#5612, `source.find.app-card-actions`): the
    /// engine sets it as the step's reader, kept as the project's override, and saves the recipe
    /// (audited, undoable); the changed step replaces its own in place, as with `useInstead`.
    func useCandidate(_ candidate: Components.Schemas.ModelCandidate, forStep step: String) async {
        await useCard(candidate.id, named: candidate.name, forStep: step)
    }

    /// Use for This Step by card: the finder's candidates and a stage comparison's columns (Use This) alike.
    func useCard(_ card: String, named name: String, forStep step: String) async {
        let candidate = (id: card, name: name)
        do {
            switch try await client.api.useCandidateForStepApiRecipesProjectStepsUseCandidatePost(
                body: .json(.init(step: step, card: candidate.id))
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
                readerChanged()
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? "The engine would not use \(candidate.name) for this step."
            case .undocumented(let code, _):
                errorMessage = "Could not use \(candidate.name) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not use \(candidate.name): \(error.localizedDescription)"
        }
    }

    /// Run the model this Mac cannot run at the free place the plan offers (#5592,
    /// `ai.where.fallback-free-and-asked`): only on this press, the engine sets the same model at that
    /// place on the steps and saves the recipe; the changed steps replace theirs in place, and Ready
    /// reads the plan again because the recipe changed.
    func useFreePlace(_ entry: Components.Schemas.StartElsewhere,
                      _ place: Components.Schemas.StartPlaceInstead) async {
        do {
            switch try await client.api.useInstalledInsteadApiRecipesProjectStartUseInsteadPost(
                body: .json(.init(model: entry.model, provider: place.provider))
            ) {
            case .ok(let success):
                if let recipe = try success.body.json.recipe {
                    adoptEngineRecipe(try JSONEncoder().encode(recipe))
                }
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail?.description
                    ?? "The engine would not run \(entry.name) at \(place.providerName)."
            case .undocumented(let code, _):
                errorMessage = "Could not run \(entry.name) at \(place.providerName) (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not run \(entry.name) at \(place.providerName): \(error.localizedDescription)"
        }
    }
}
