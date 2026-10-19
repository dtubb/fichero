import Foundation

/// Ready's boxes, in order (`source.onboard.ready.grouped-sections`, #5840): each plan step is its own numbered box in run
/// order, then what runs by itself, then the two optional parts, then the last box with the total and why Start waits.
/// Pure, so the order can be checked without drawing it.
enum ReadySection: Equatable {
    case step(number: Int, stepId: String, title: String)
    case runsByItself
    case checkOnYourPages
    case keepAnExport
    /// Offered only once there is enough corrected work (#5804).
    case trainOffer
    case start

    /// The heading of the box; a step's is numbered.
    var title: String {
        switch self {
        case .step(let number, _, let title): "\(number). \(title)"
        case .runsByItself: "What runs by itself"
        case .checkOnYourPages: "Check on your pages"
        case .keepAnExport: "Keep an export"
        case .trainOffer: "Train a model of your own"
        case .start: "Start"
        }
    }

    /// Shown small and grey beside the heading: the parts that can be left and done later from the Inspector.
    var isOptional: Bool { self == .checkOnYourPages || self == .keepAnExport }

    static func order(steps: [(id: String, title: String)], offersTraining: Bool = false) -> [ReadySection] {
        steps.enumerated().map { .step(number: $0.offset + 1, stepId: $0.element.id, title: $0.element.title) }
            + [.runsByItself, .checkOnYourPages, .keepAnExport] + (offersTraining ? [.trainOffer] : []) + [.start]
    }
}
