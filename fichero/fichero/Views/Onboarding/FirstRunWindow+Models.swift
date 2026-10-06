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
    // Setup in four steps (section 7b, ruled 2026-10-06, #5492; `source.onboard.screens-in-order`):
    // your project, your material, what you want to do (each ticked purpose's questions open in
    // place under it), and Ready (the plan, what runs by itself, the optional rows, then Start).
    case project
    case material
    case purpose
    // The first yes (`source.project.automatic-after-first-yes`): nothing runs before Start.
    case ready

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .permissions: return "Permissions"
        case .cloud: return "AI"
        case .project: return "Your Project"
        case .material: return "Your Material"
        case .purpose: return "What You Want to Do"
        case .ready: return "Ready"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .permissions: return "lock.shield"
        case .cloud: return "brain"
        case .project: return "folder"
        case .material: return "tray.and.arrow.down"
        case .purpose: return "target"
        case .ready: return "play.circle"
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
    /// it starts at step 2, Your material (section 7b). One code path with first run.
    static let setUpSteps: [FirstRunStep] = [.material, .purpose, .ready]

    /// File › Set Up New Project…: Your project, then the same steps as Set Up….
    static let newProjectSteps: [FirstRunStep] = [.project] + setUpSteps

    /// Continue on this step keeps the answers so far as a draft on the project
    /// (`source.onboard.screens-in-order`); saving is not Start, so nothing runs. Your project
    /// makes the project rather than saving into one; Ready saves as part of Start.
    var savesDraft: Bool { self == .material || self == .purpose }

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
