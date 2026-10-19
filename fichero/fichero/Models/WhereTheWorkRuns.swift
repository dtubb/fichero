import Foundation

/// Where Fichero's models may run (`source.onboard.first-launch-three-screens`, #5828, ruled 2026-10-19): the first
/// launch's second screen. This Mac only is the default. VIEW STATE ONLY: nothing is stored and nothing reads it yet;
/// #5810 makes it the engine's app setting, set by an audited action (the default for each project's `cloud_allowed`).
/// The words are placeholders until the owner hands the text back.
enum WhereTheWorkRuns: String, CaseIterable, Identifiable {
    case thisMac
    case anotherMac
    case cloud
    case cluster

    var id: String { rawValue }

    static let `default`: WhereTheWorkRuns = .thisMac

    var title: String {
        switch self {
        case .thisMac: "This Mac only"
        case .anotherMac: "Another Mac of mine"
        case .cloud: "Cloud AI and ML models"
        case .cluster: "A cluster"
        }
    }

    /// Placeholder copy; it promises nothing the engine does not yet hold.
    var detail: String {
        switch self {
        case .thisMac: "Models run on this Mac."
        case .anotherMac: "Models also run on a Mac of yours."
        case .cloud: "Models also run in the cloud."
        case .cluster: "Large jobs also go to a computing cluster you have access to."
        }
    }
}
