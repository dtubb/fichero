import Foundation

/// The three global controls (`activity.window.run-controls`, decision 30, #6588).
enum ActivityRunControl: Sendable {
    case pauseAll, continueAll, stopAll
}
