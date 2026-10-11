import FicheroAPIClient
import Foundation

// MARK: - The stages (section 7c/7d, #5668)

extension RecipeSetupStore {
    /// The stages, once, in the engine's order, with this project's choice as the engine has it (a stage is on when
    /// the project's recipe has any of its jobs). The app works none of it out
    /// (`source.onboard.stages.stages-list-from-the-engine`).
    func loadStages() async {
        guard stages.isEmpty else { return }
        do {
            if case .ok(let success) = try await client.api.listStagesApiRecipesStagesGet() {
                let items = try success.body.json.items
                stages = items
                stageChoice = SetupStageChoice(
                    stages: items.map(Self.choiceStage),
                    chosen: Set(items.filter(\.on).map(\.id))
                )
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the stages: \(error.localizedDescription)"
        }
    }

    /// The chosen stages, in the engine's order: one page each.
    var chosenStageIds: [String] { stageChoice?.chosenInOrder ?? [] }

    /// Each stage's title, for its page's name in the window's list.
    var stageTitles: [String: String] {
        Dictionary(stages.map { ($0.id, $0.title) }, uniquingKeysWith: { first, _ in first })
    }

    func stage(_ id: String) -> Components.Schemas.SetupStage? { stages.first { $0.id == id } }

    /// Tick or untick a stage; the answers follow, so the next recipe has the chosen stages' jobs and no others.
    func toggle(stage id: String) {
        stageChoice?.toggle(id)
        applyStageChoiceToJobs()
    }

    /// A goal (a purpose) as a shortcut: it ticks the stages that carry its jobs, and stays a goal of the project.
    func applyGoal(_ purposeId: String) {
        let jobs = purposeOptions.first { $0.id == purposeId }?.jobs?.map(\.id) ?? []
        if !purposes.contains(purposeId) { purposes.append(purposeId) }
        stageChoice?.applyGoal(jobs: jobs)
        applyStageChoiceToJobs()
    }

    private func applyStageChoiceToJobs() {
        guard let choice = stageChoice else { return }
        let (added, removed) = choice.jobsAddedAndRemoved
        addedJobs = added
        removedJobs = removed
    }

    /// The steps Start skips that belong to a chosen stage (`source.onboard.ready.will-not-run-when-chosen`): a step
    /// of a stage not chosen is not listed. Before the stages load, every skipped step.
    var skippedStepsOfChosenStages: [Components.Schemas.SkippedStep] {
        guard let choice = stageChoice else { return skippedSteps }
        let chosenJobs = Set(choice.jobsAddedAndRemoved.added)
        let jobOfStep = Dictionary((recipe?.steps ?? []).map { ($0.id, $0.job) }, uniquingKeysWith: { first, _ in first })
        return skippedSteps.filter { chosenJobs.contains(jobOfStep[$0.step] ?? $0.step) }
    }

    /// The pages already in the project, as the engine counts them for Start (every page, every file with no pages:
    /// `start.count_pages`); nil before the plan is read (`source.onboard.project.about-material`).
    var countedPages: Int? { startPlan.map { $0.estimate.pages } }

    /// Read the count again (after material was added) and keep it as the pages answer, so the estimate is the
    /// material's, not a guess typed earlier.
    func countPages() async {
        await loadStartPlan()
        if let counted = countedPages, counted > 0 { pages = counted }
    }

    static func choiceStage(_ stage: Components.Schemas.SetupStage) -> SetupStageChoice.Stage {
        SetupStageChoice.Stage(id: stage.id, jobs: stage.jobs, needs: stage.needs.map { ($0.stage, $0.why) })
    }
}
