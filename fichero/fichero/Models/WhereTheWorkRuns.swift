import Foundation

/// Where Fichero's models may run (`source.onboard.first-launch-three-screens`, #5828, ruled 2026-10-19): the first
/// launch's second screen. This Mac only is the default; the others are choices a person makes. #5810 reads the cloud
/// answer; the words here are placeholders until the owner hands the text back.
enum WhereTheWorkRuns: String, CaseIterable, Identifiable {
    case thisMac
    case anotherMac
    case cloud
    case cluster

    var id: String { rawValue }

    static let defaultsKey = "setup.whereTheWorkRuns"
    static let `default`: WhereTheWorkRuns = .thisMac

    var title: String {
        switch self {
        case .thisMac: "This Mac only"
        case .anotherMac: "Another Mac of mine"
        case .cloud: "Cloud AI and ML models"
        case .cluster: "A cluster"
        }
    }

    /// Placeholder copy.
    var detail: String {
        switch self {
        case .thisMac: "Your pages never leave this Mac."
        case .anotherMac: "Use a Mac of yours as well; its pages stay on your Macs."
        case .cloud: "Pages go to the provider you choose; Fichero asks before any page leaves."
        case .cluster: "Send large jobs to a computing cluster you have access to."
        }
    }

    /// The kept answer; this Mac only when none was kept.
    static func current(_ defaults: UserDefaults = .standard) -> WhereTheWorkRuns {
        defaults.string(forKey: defaultsKey).flatMap(WhereTheWorkRuns.init(rawValue:)) ?? .default
    }

    static func keep(_ choice: WhereTheWorkRuns, _ defaults: UserDefaults = .standard) {
        defaults.set(choice.rawValue, forKey: defaultsKey)
    }
}
