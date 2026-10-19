import Foundation

/// The places models may run (`source.onboard.places-cap-projects`, #5828): the engine's ids. The setting is the
/// engine's (`AppPlacesStore`); this is only the names and the default shown before it answers.
enum WhereTheWorkRuns: String, CaseIterable, Identifiable {
    case thisMac = "this-mac"
    case anotherMac = "another-mac"
    case cloud
    case acenet
    case huggingface

    var id: String { rawValue }
    static let `default`: WhereTheWorkRuns = .thisMac
}
