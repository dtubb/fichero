import Foundation

/// `answers.how`: where the work runs, which kind of model, what matters most (`designer.how.*`, #6052). Ids are the engine's
/// (`GET /api/recipes/questions`); nothing here decides what they mean.
struct HowAnswers: Codable, Equatable {
    var places: [String]?
    var modelKind: String?
    var matters: String?

    enum CodingKeys: String, CodingKey { case places, modelKind = "model_kind", matters }

    /// Nothing answered yet: not saved, so a project that never saw the page keeps no `how`.
    var isEmpty: Bool { (places ?? []).isEmpty && modelKind == nil && matters == nil }
}
