import FicheroAPIClient
import Foundation

/// The engine's Models answer: the models, every place set up and this Mac (`GET /api/activity/models`).
struct ActivityModelsAnswer: Equatable, Sendable {
    var models: [ActivityModelEntry] = []
    var places: [ActivityModelEntry.SetUp] = []
    var thisMac: ActivityThisMac?

    /// Several projects' answers as one: the models merged, the places once each in the order first seen.
    static func merged(_ answers: [ActivityModelsAnswer]) -> ActivityModelsAnswer {
        let places = answers.flatMap(\.places).reduce(into: [ActivityModelEntry.SetUp]()) {
            if !$0.contains($1) { $0.append($1) }
        }
        return ActivityModelsAnswer(models: ActivityModelEntry.merged(answers.map(\.models)), places: places,
                                    thisMac: ActivityThisMac.merged(answers.compactMap(\.thisMac)))
    }
}
