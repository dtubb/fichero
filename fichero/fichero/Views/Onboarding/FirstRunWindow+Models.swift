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
    // Recipe setup (source.onboard.*): purpose first, then the material, ending
    // in the proposed recipe and, only when a cloud model would fit, the one
    // question whether pages may leave this Mac. Setup ends on what will run.
    case purpose
    case material

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .library: return "Project"
        case .purpose: return "Purpose"
        case .cloud: return "AI"
        case .material: return "Your Material"
        case .permissions: return "Permissions"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .library: return "folder"
        case .purpose: return "target"
        case .cloud: return "brain"
        case .material: return "doc.text.magnifyingglass"
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
        case .library, .purpose, .cloud, .material, .permissions: return true
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
    static let setUpSteps: [FirstRunStep] = [.purpose, .material]

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
