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
                let list = try success.body.json
                let items = list.items
                moneyAndPlace = list.moneyAndPlace
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
    var chosenStageIds: [String] { stageIds(keeping: nil) }

    /// The chosen stages, plus `current` while the person is on its page: unticking a stage on its own page (Leave Out's
    /// toggle) must not drop the page from under them, or Continue and Back would lose their place.
    func stageIds(keeping current: String?) -> [String] { stageChoice?.inOrder(keeping: current) ?? [] }

    /// Each stage's title, for its page's name in the window's list.
    var stageTitles: [String: String] {
        Dictionary(stages.map { ($0.id, $0.title) }, uniquingKeysWith: { first, _ in first })
    }

    func stage(_ id: String) -> Components.Schemas.SetupStage? { stages.first { $0.id == id } }

    /// Tick or untick a stage; the answers follow, so the next recipe has the chosen stages' jobs and no others.
    func toggle(stage id: String) {
        stageChoice?.toggle(id)
        applyStageChoiceToJobs()
        // Leave Out's own question is the step's on/off (`source.recipe.leave-out-stage`): the tick and the toggle agree.
        if id == Self.leaveOutStage, let choice = stageChoice {
            jobAnswers[question: Self.leaveOutQuestion] = .yesNo(choice.chosen.contains(id))
        }
    }

    /// Leave Out turned on or off from anywhere but the chooser (its page's toggle, Ready's take out and put back): the
    /// answer is saved and the stage's tick follows, so the three never disagree. A tick that cannot change (another
    /// chosen stage needs the stage) leaves the answer as the tick has it.
    func setLeaveOut(_ on: Bool) {
        jobAnswers[question: Self.leaveOutQuestion] = .yesNo(on)
        guard let choice = stageChoice else { return }
        if choice.chosen.contains(Self.leaveOutStage) != on { stageChoice?.toggle(Self.leaveOutStage) }
        let ticked = stageChoice?.chosen.contains(Self.leaveOutStage) ?? on
        jobAnswers[question: Self.leaveOutQuestion] = .yesNo(ticked)
        // only this job's lines: the other steps taken out on Ready stay taken out
        removedJobs.removeAll { $0 == Self.leaveOutStage }
        addedJobs.removeAll { $0 == Self.leaveOutStage }
        if ticked { addedJobs.append(Self.leaveOutStage) } else { removedJobs.append(Self.leaveOutStage) }
    }

    /// Take a step out of the plan; the engine proposes the plan again without it, and Ready saves that, so
    /// Start runs the plan as shown and Set Up… reopens with it.
    func takeOut(job: String) async {
        guard !removedJobs.contains(job) else { return }
        removedJobs.append(job)
        if job == Self.leaveOutStage { setLeaveOut(false) }  // the saved answer follows the plan, never contradicts it
        await assemble()
    }

    /// Put a step taken out back into the plan.
    func putBack(job: String) async {
        removedJobs.removeAll { $0 == job }
        if job == Self.leaveOutStage { setLeaveOut(true) }
        await assemble()
    }

    /// The Leave Out stage and its one job (`recipes/stages.py`).
    static let leaveOutStage = "leave-out"

    /// The stage question that turns Leave Out on or off (`recipes/assemble.LEAVE_OUT_QUESTION`).
    static let leaveOutQuestion = "leave_out"

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
        runFirstPages = nil  // new material: the first N pages are no longer the question
        await loadStartPlan()
        if let counted = countedPages, counted > 0 { pages = counted }
    }

    static func choiceStage(_ stage: Components.Schemas.SetupStage) -> SetupStageChoice.Stage {
        SetupStageChoice.Stage(id: stage.id, jobs: stage.jobs, needs: stage.needs.map { ($0.stage, $0.why) })
    }

    /// Add one step to the project's plan from outside Set Up (the disagreement lens's Find Where the Readers
    /// Disagree, #5665): read what the project saved, tick the job, have the engine propose the plan again, and keep
    /// it as the draft, for Set Up's Start to run. Saves only once the engine's plan holds the step, so a project
    /// whose setup could not be read is never overwritten with defaults. False, with the engine's words in
    /// `errorMessage`, when it could not.
    func addStep(job: String) async -> Bool {
        await loadSaved()
        removedJobs.removeAll { $0 == job }
        if !tickedJobs.contains(job) { addedJobs.append(job) }
        await assemble()
        guard (recipe?.steps ?? []).contains(where: { $0.job == job }) else {
            if errorMessage == nil { errorMessage = "Set Up the project's languages and scripts first." }
            return false
        }
        return await save()
    }
}
