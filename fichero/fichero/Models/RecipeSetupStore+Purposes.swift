import FicheroAPIClient
import Foundation

/// The purpose checkboxes (#5478) and the one choice on Ready, what runs by itself
/// (`source.onboard.what-runs-by-itself`). Moved out of `RecipeSetupStore.swift` unchanged, to keep its body under
/// SwiftLint's `type_body_length`.
extension RecipeSetupStore {
    // MARK: Purposes and jobs as checkboxes (#5478)

    /// Tick or untick a purpose. None ticked is "Not sure yet" (the engine reads an empty list so).
    func toggle(purpose id: String) {
        if let index = purposes.firstIndex(of: id) {
            purposes.remove(at: index)
        } else {
            purposes.append(id)
            // Ticking a purpose asks for its jobs: a step taken out on Ready that it brings comes back (#5627).
            let brings = Set(purposeOptions.first { $0.id == id }?.jobs?.map(\.id) ?? [])
            removedJobs.removeAll { brings.contains($0) }
        }
    }

    /// The ticked purpose that already includes this one, when it is listed under it (#5625): its parent, ticked,
    /// whose jobs hold every one of this purpose's (the knowledge graph holds Entities and Statements). Shown
    /// ticked and fixed while the parent is; nil otherwise.
    func includingPurpose(of id: String) -> Components.Schemas.PurposeInfo? {
        guard !purposes.contains(id), let option = purposeOptions.first(where: { $0.id == id }),
              let parentId = option.parent, purposes.contains(parentId),
              let parent = purposeOptions.first(where: { $0.id == parentId }) else { return nil }
        let held = Set((parent.jobs ?? []).map(\.id))
        return (option.jobs ?? []).allSatisfy { held.contains($0.id) } ? parent : nil
    }

    // MARK: What runs by itself (source.onboard.what-runs-by-itself)

    /// The one choice on Ready: Nothing runs automatically, or new material runs through the
    /// recipe's steps (the purposes' proposal where there is one, else every step but training,
    /// `source.recipe.train-never-automatic`).
    func setRunsByItself(_ runs: Bool) {
        var steps = automaticAnswer.steps
        if runs && steps.isEmpty {
            steps = (recipe?.steps ?? []).map(\.job).filter { $0 != "train-a-model" }
        }
        automatic = .init(runs: runs, steps: steps)
    }

    /// The proposal before the person says: steps of a purpose that runs by itself are ticked
    /// (training never is, `source.recipe.train-never-automatic`); with none, nothing runs.
    var proposedAutomatic: RecipeSetupAnswers.Automatic {
        let running = purposeOptions.filter { purposes.contains($0.id) && $0.runsByItself }
        let jobs = Set(running.flatMap { ($0.jobs ?? []).map(\.id) })
        let steps = (recipe?.steps ?? []).map(\.job).filter { jobs.contains($0) && $0 != "train-a-model" }
        return .init(runs: !steps.isEmpty, steps: steps)
    }

    /// What runs by itself: the person's answer, else the proposal.
    var automaticAnswer: RecipeSetupAnswers.Automatic { automatic ?? proposedAutomatic }
}
