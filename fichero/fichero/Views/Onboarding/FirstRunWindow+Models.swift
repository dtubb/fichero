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

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .library: return "Library"
        case .permissions: return "Permissions"
        case .cloud: return "AI"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .library: return "folder"
        case .permissions: return "lock.shield"
        case .cloud: return "brain"
        }
    }

    /// Mac-only steps (#2807): library location, folder permissions, and AI
    /// provider setup all configure a LOCAL engine. iPhone/iPad have none
    /// (`EngineConfig.iosLaunchPhase` — the device is a companion to a paired
    /// Mac), so these steps are meaningless there and must be skipped.
    var isMacOnly: Bool {
        switch self {
        case .welcome: return false
        case .library, .permissions, .cloud: return true
        }
    }

    /// Platform-gated step list (#2807): companion platforms (iOS/iPadOS —
    /// no local engine) run only the steps that apply there; the Mac keeps
    /// the full flow. Pure so the selection truth table is unit-testable.
    static func steps(isCompanionPlatform: Bool) -> [FirstRunStep] {
        isCompanionPlatform ? allCases.filter { !$0.isMacOnly } : allCases
    }

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
