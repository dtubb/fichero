import FicheroAPIClient
import Foundation

/// Setup's model questions answered by the model finder (#5619, `source.find.choose-a-model-opens-the-finder`): a
/// step's Choose a model…, Download a model… and Use a cloud model… open the finder for THAT step's job, with the
/// project's scripts, languages and first material, in Set Up… › Ready (the step's row, and the same step under
/// Will not run). Kept beside `RecipeSetupStore` so the store's own file stays setup's.
extension RecipeSetupStore {
    /// The fixes the model finder answers: choosing a model, downloading one, or choosing a cloud one (the finder
    /// lists every place a model runs, with where in words). Letting pages leave and accepting a licence are
    /// answered elsewhere (the cloud question; the card's licence).
    nonisolated static let finderFixes: Set<String> = ["choose-model", "download", "choose-cloud"]

    nonisolated static func fixOpensFinder(_ fix: String) -> Bool {
        finderFixes.contains(fix)
    }

    /// The job of a step in the recipe on screen, by its id; nil for a step the recipe does not have.
    func job(ofStepId step: String) -> String? {
        recipe?.steps.first { $0.id == step }?.job
    }

    /// What the finder asks for a step's job: the project's scripts and languages and its first material.
    func finderQuery(job: String) -> ModelFinderStore.Query {
        .init(job: job, scripts: scripts, languages: languages, material: materials.first ?? "handwriting")
    }
}
