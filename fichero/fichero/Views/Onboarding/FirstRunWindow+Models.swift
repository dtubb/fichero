import Foundation

struct FirstRunCardConfig {
    let icon: String
    let title: String
    let body: String
    let primaryTitle: String
    let primaryIcon: String
    let primaryAction: () -> Void
}

enum FirstRunStep: Int, CaseIterable, Identifiable {
    case welcome
    case permissions
    case cloud
    // Setup, in the order of section 7b (ruled 2026-10-05, `source.onboard.screens-in-order`):
    // where it lives, what it is for, your material, what it is, a screen for each ticked job
    // (`jobs` stands for them, and is replaced by them), how it will be done, what runs by
    // itself, then Start.
    case location
    case purpose
    case material
    case about
    case jobs
    case recipe
    case automatic
    // The first yes (`source.project.automatic-after-first-yes`): what will run, on how many
    // pages, with an estimate; nothing runs by itself before Start.
    case start

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .location: return "Where It Lives"
        case .purpose: return "What It Is For"
        case .cloud: return "AI"
        case .material: return "Your Material"
        case .about: return "What It Is"
        case .jobs: return "Each Job"
        case .recipe: return "How It Will Be Done"
        case .automatic: return "What Runs by Itself"
        case .start: return "Start"
        case .permissions: return "Permissions"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .location: return "folder"
        case .purpose: return "target"
        case .cloud: return "brain"
        case .material: return "tray.and.arrow.down"
        case .about: return "character.book.closed"
        case .jobs: return "checklist"
        case .recipe: return "list.bullet.rectangle"
        case .automatic: return "gearshape.2"
        case .start: return "play.circle"
        case .permissions: return "lock.shield"
        }
    }

    /// Mac-only steps (#2807): project location, folder permissions, AI provider setup and the
    /// recipe all configure a LOCAL engine. iPhone/iPad have none
    /// (`EngineConfig.iosLaunchPhase` — the device is a companion to a paired
    /// Mac), so these steps are meaningless there and must be skipped.
    var isMacOnly: Bool { self != .welcome }

    /// Platform-gated step list (#2807): companion platforms (iOS/iPadOS —
    /// no local engine) run only the steps that apply there; the Mac keeps
    /// the full flow. Pure so the selection truth table is unit-testable.
    static func steps(isCompanionPlatform: Bool) -> [FirstRunStep] {
        isCompanionPlatform ? allCases.filter { !$0.isMacOnly } : allCases
    }

    /// The steps Set Up… runs for an existing project: the project already lives somewhere, so
    /// it starts at What it is for (section 7b). One code path with first run.
    static let setUpSteps: [FirstRunStep] = [.purpose, .material, .about, .jobs, .recipe, .automatic, .start]

    /// File › Set Up New Project…: Where it lives, then the same steps as Set Up….
    static let newProjectSteps: [FirstRunStep] = [.location] + setUpSteps

    /// Leaving this screen keeps the answers so far as a draft on the project
    /// (`source.onboard.screens-in-order`); saving is not Start, so nothing runs. Where it lives
    /// makes the project rather than saving into one.
    var savesDraft: Bool { Self.setUpSteps.contains(self) && self != .start }

    /// Whether THIS platform takes the companion first-run path (#2807).
    /// Compile-time: macOS owns the local engine; every other platform is a
    /// companion (pairs to a Mac, per `EngineConfig.iosLaunchPhase`).
    static var isCompanionPlatform: Bool {
        #if os(macOS)
        false
        #else
        true
        #endif
    }

    /// List-relative forward navigation (#2807): the successor within the
    /// PLATFORM's step list, clamped at the end (the caller finishes there).
    func next(in steps: [FirstRunStep]) -> FirstRunStep {
        guard let index = steps.firstIndex(of: self), index + 1 < steps.count else {
            return steps.last ?? self
        }
        return steps[index + 1]
    }

    /// List-relative backward navigation (#2807), clamped at the start.
    func previous(in steps: [FirstRunStep]) -> FirstRunStep {
        guard let index = steps.firstIndex(of: self), index > 0 else {
            return steps.first ?? self
        }
        return steps[index - 1]
    }
}

/// One page setup shows: a step, or the screen of one ticked job (`source.onboard.job-detail-screens`;
/// ruled 2026-10-05: every ticked job adds its own screen, an unticked one adds none).
enum SetupPage: Hashable, Identifiable {
    case step(FirstRunStep)
    case job(String)

    var id: String {
        switch self {
        case .step(let step): "step-\(step.rawValue)"
        case .job(let job): "job-\(job)"
        }
    }

    /// The pages in order: `steps`, with `.jobs` replaced by one page per ticked job (none
    /// when no job is ticked).
    static func pages(steps: [FirstRunStep], tickedJobs: [String]) -> [SetupPage] {
        steps.flatMap { step in step == .jobs ? tickedJobs.map(SetupPage.job) : [.step(step)] }
    }

    /// Leaving a job's screen saves its answers like any setup screen.
    var savesDraft: Bool {
        switch self {
        case .step(let step): step.savesDraft
        case .job: true
        }
    }
}
