import Foundation

/// The project's cloud switch in words (`ai.cloud.switch-in-the-project`, #6022 place 1): the project's own yes
/// or no, or
/// the app's Settings answer it follows until it answers for itself. Pure, from what the engine served
/// (`cloud_inherited` and the saved `cloud_allowed`), never a rule kept here.
enum ProjectCloudSwitch: Equatable {
    case allowed
    case refused
    case asSettings(Bool)

    static func state(answered: Bool, allowed: Bool) -> ProjectCloudSwitch {
        answered ? (allowed ? .allowed : .refused) : .asSettings(allowed)
    }

    var words: String {
        switch self {
        case .allowed: "On for this project, whatever Settings says."
        case .refused: "Off for this project, whatever Settings says."
        case .asSettings(let allowed): "As Settings: \(allowed ? "on" : "off")."
        }
    }
}
