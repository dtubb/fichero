import Foundation

/// One page of setting up (section 7d, ruled 2026-10-11, #5668): the app's own pages, then Set Up a Project's, with
/// one page per chosen stage. A stage page is named by the engine's stage id (`GET /api/recipes/stages`).
enum SetupStep: Hashable, Identifiable {
    // Setting up the app (`source.onboard.app.steps`).
    case welcome
    case whatFicheroRuns
    case handOff
    // Set Up a Project (`source.onboard.project.steps`).
    case project
    case addMaterial
    case aboutMaterial
    case stages
    case stage(String)
    case ready

    var id: String {
        switch self {
        case .stage(let stageId): "stage:\(stageId)"
        default: String(describing: self)
        }
    }

    /// The page's name in the window's list. A stage page takes the engine's title for its stage.
    func title(stageTitles: [String: String] = [:]) -> String {
        switch self {
        case .welcome: "Welcome"
        case .whatFicheroRuns: "AI and ML Models"
        case .handOff: "Your First Project"
        case .project: "Your Project"
        case .addMaterial: "Add Material"
        case .aboutMaterial: "About the Material"
        case .stages: "Choose the Stages"
        case .stage(let stageId): stageTitles[stageId] ?? stageId
        case .ready: "Ready"
        }
    }

    var icon: String {
        switch self {
        case .welcome: "sparkles"
        case .whatFicheroRuns: "cpu"
        case .handOff: "arrow.right.circle"
        case .project: "folder"
        case .addMaterial: "tray.and.arrow.down"
        case .aboutMaterial: "text.magnifyingglass"
        case .stages: "checklist"
        case .stage: "circle.dashed"
        case .ready: "play.circle"
        }
    }

    /// The app's pages, before any project (`source.onboard.app.steps`). No Permissions page: access to a folder is
    /// asked when a folder is added.
    static let appSteps: [SetupStep] = [.welcome, .whatFicheroRuns, .handOff]

    /// Set Up a Project's pages (`source.onboard.project.steps`): Your project for a new one (Project › Set Up… on an
    /// existing project starts at Add material), then one page per chosen stage, in the engine's order, then Ready
    /// (training is not a step: the plan offers it once there is enough corrected work, #5804). `chosenStages` is in the engine's order already.
    static func projectSteps(chosenStages: [String], isNewProject: Bool) -> [SetupStep] {
        (isNewProject ? [.project] : []) + [.addMaterial, .aboutMaterial, .stages]
            + chosenStages.map(SetupStep.stage) + [.ready]
    }

    /// The stage Train a Model… asks Set Up for (`LibraryManager.requestSetUp(for:stage:)`): it opens Ready, where the
    /// plan's training offers are.
    static let trainStage = "train"

    /// The page Set Up opens on when a stage is asked for: Train a Model… and any other stage open Ready, whose plan lists each step with its fix, until Set Up has a page per stage (#5668, §7c);
    /// none asked for opens the flow's first page (nil).
    static func opening(requestedStage: String?) -> SetupStep? {
        switch requestedStage {
        case nil: nil
        default: .ready
        }
    }

    /// Continue keeps the answers so far as a draft on the project (`source.onboard.screens-in-order`); saving is not
    /// Start, so nothing runs. Your project makes the project rather than saving into one; Ready saves with Start.
    var savesDraft: Bool {
        switch self {
        case .addMaterial, .aboutMaterial, .stages, .stage: true
        default: false
        }
    }

    /// The pages before a project exists: reachable with no project.
    var needsNoProject: Bool { Self.appSteps.contains(self) || self == .project }

    /// The successor within `steps`, clamped at the end (the caller finishes there).
    func next(in steps: [SetupStep]) -> SetupStep {
        guard let index = steps.firstIndex(of: self), index + 1 < steps.count else { return steps.last ?? self }
        return steps[index + 1]
    }

    /// The predecessor within `steps`, clamped at the start.
    func previous(in steps: [SetupStep]) -> SetupStep {
        guard let index = steps.firstIndex(of: self), index > 0 else { return steps.first ?? self }
        return steps[index - 1]
    }
}

/// Which pages a setup window shows: the app's, a project's, or the app's then a project's (a first launch whose
/// hand-off chose Set Up a Project). One view for every way in (`source.onboard.project.one-view`).
struct SetupFlow: Equatable {
    enum ProjectPages: Equatable {
        /// No project pages (yet).
        case none
        /// Your project makes one: a first launch's hand-off, the welcome, File › Set Up New Project….
        case new
        /// Project › Set Up… on a project that exists: from Add material.
        case existing
    }

    var includesApp: Bool
    var project: ProjectPages
    /// The chosen stages, in the engine's order.
    var chosenStages: [String] = []

    /// iPhone and iPad have no local engine to set up (#2807): their first run is the welcome alone.
    var isCompanionPlatform = false

    /// Whether THIS platform takes the companion path (#2807): macOS owns the local engine; every other platform
    /// pairs to a Mac (`EngineConfig.iosLaunchPhase`).
    static var runsOnCompanionPlatform: Bool {
        #if os(macOS)
        false
        #else
        true
        #endif
    }

    var steps: [SetupStep] {
        if isCompanionPlatform { return [.welcome] }
        let app = includesApp ? SetupStep.appSteps : []
        let projectSteps: [SetupStep] = switch project {
        case .none: []
        case .new: SetupStep.projectSteps(chosenStages: chosenStages, isNewProject: true)
        case .existing: SetupStep.projectSteps(chosenStages: chosenStages, isNewProject: false)
        }
        return app + projectSteps
    }
}

/// Choosing the stages (`source.onboard.stages.choose-first`, `.needs-are-ticked`, `.goals-are-shortcuts`): every
/// stage on or off; ticking one ticks the stages it needs; a stage another chosen stage needs cannot be unticked, and
/// says why; a goal ticks the stages that carry its jobs. Pure, over the engine's list.
struct SetupStageChoice: Equatable {
    struct Stage: Equatable {
        let id: String
        let jobs: [String]
        /// The stages it needs, each with the engine's words ("Dates & Times needs Names").
        let needs: [(stage: String, why: String)]

        static func == (lhs: Stage, rhs: Stage) -> Bool {
            lhs.id == rhs.id && lhs.jobs == rhs.jobs
                && lhs.needs.map(\.stage) == rhs.needs.map(\.stage) && lhs.needs.map(\.why) == rhs.needs.map(\.why)
        }
    }

    /// In the engine's (pipeline) order.
    let stages: [Stage]
    private(set) var chosen: Set<String>

    init(stages: [Stage], chosen: Set<String>) {
        self.stages = stages
        self.chosen = chosen
    }

    /// The chosen stages, in the engine's order.
    var chosenInOrder: [String] { stages.map(\.id).filter(chosen.contains) }

    /// Why a chosen stage cannot be unticked: the words of each chosen stage that needs it; empty when it can be.
    func neededBecause(_ stageId: String) -> [String] {
        stages.filter { chosen.contains($0.id) && $0.id != stageId }
            .flatMap { stage in stage.needs.filter { $0.stage == stageId }.map(\.why) }
    }

    /// Tick or untick one stage. Ticking ticks what it needs, and what those need; unticking a needed stage does
    /// nothing (its reason is shown instead).
    mutating func toggle(_ stageId: String) {
        if chosen.contains(stageId) {
            guard neededBecause(stageId).isEmpty else { return }
            chosen.remove(stageId)
        } else {
            choose(stageId)
        }
    }

    /// A goal's shortcut: tick every stage that carries one of the goal's jobs. A stage unticked by hand afterwards
    /// stays unticked; the goal does not hold it.
    mutating func applyGoal(jobs goalJobs: [String]) {
        let wanted = Set(goalJobs)
        for stage in stages where !wanted.isDisjoint(with: stage.jobs) {
            choose(stage.id)
        }
    }

    private mutating func choose(_ stageId: String) {
        guard chosen.insert(stageId).inserted, let stage = stages.first(where: { $0.id == stageId }) else { return }
        for need in stage.needs { choose(need.stage) }
    }

    /// What the answers carry so the engine's recipe follows the choice: every chosen stage's jobs added
    /// (`answers.jobs`), every other stage's jobs taken out (`answers.removed_jobs`).
    var jobsAddedAndRemoved: (added: [String], removed: [String]) {
        let added = stages.filter { chosen.contains($0.id) }.flatMap(\.jobs)
        let removed = stages.filter { !chosen.contains($0.id) }.flatMap(\.jobs).filter { !added.contains($0) }
        return (added, removed)
    }
}
