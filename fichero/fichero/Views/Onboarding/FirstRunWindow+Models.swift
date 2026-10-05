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
    case library
    case permissions
    case cloud
    // Recipe setup (`source.onboard.screens-in-order`), the screens of the spec's
    // section 7 in its order: what you are doing, your material (where it is and
    // how it comes in), what it is, how it will be done, then Start. Screen 5
    // (check on your pages) waits for the evaluation job (#5441).
    case purpose
    case material
    case about
    case recipe
    // The first yes (`source.project.automatic-after-first-yes`): what will run, on how many
    // pages, with an estimate; nothing runs by itself before Start.
    case start

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .library: return "Project"
        case .purpose: return "Purpose"
        case .cloud: return "AI"
        case .material: return "Your Material"
        case .about: return "What It Is"
        case .recipe: return "How It Will Be Done"
        case .start: return "Start"
        case .permissions: return "Permissions"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .library: return "folder"
        case .purpose: return "target"
        case .cloud: return "brain"
        case .material: return "tray.and.arrow.down"
        case .about: return "character.book.closed"
        case .recipe: return "list.bullet.rectangle"
        case .start: return "play.circle"
        case .permissions: return "lock.shield"
        }
    }

    /// Mac-only steps (#2807): library location, folder permissions, and AI
    /// provider setup all configure a LOCAL engine. iPhone/iPad have none
    /// (`EngineConfig.iosLaunchPhase` — the device is a companion to a paired
    /// Mac), so these steps are meaningless there and must be skipped.
    var isMacOnly: Bool {
        switch self {
        case .welcome: return false
        case .library, .purpose, .cloud, .material, .about, .recipe, .start, .permissions: return true
        }
    }

    /// Platform-gated step list (#2807): companion platforms (iOS/iPadOS —
    /// no local engine) run only the steps that apply there; the Mac keeps
    /// the full flow. Pure so the selection truth table is unit-testable.
    static func steps(isCompanionPlatform: Bool) -> [FirstRunStep] {
        isCompanionPlatform ? allCases.filter { !$0.isMacOnly } : allCases
    }

    /// The steps Set Up… runs for an existing library from the Inspector: the
    /// same recipe steps as first run, one code path (`source.onboard.set-up-later`).
    static let setUpSteps: [FirstRunStep] = [.purpose, .material, .about, .recipe, .start]

    /// Leaving this screen keeps the answers so far as a draft on the project
    /// (`source.onboard.screens-in-order`); saving is not Start, so nothing runs.
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
