import FicheroAPIClient
import Foundation
import Observation

/// Each review pass's instructions as the engine builds them from the project's language, script and date, and
/// whether the project edited one (`source.job.review-instructions-are-editable`, #6128). The engine holds the
/// defaults and the profile sentence; this only asks and shows them.
@MainActor
@Observable
final class ReviewInstructionsStore {
    private(set) var passes: [Components.Schemas.ReviewInstruction] = []
    private(set) var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// The passes, from what the project has saved (`GET /api/recipes/project/review-instructions`).
    func load() async {
        do {
            switch try await client.api.getReviewInstructionsApiRecipesProjectReviewInstructionsGet(.init()) {
            case .ok(let success):
                passes = try success.body.json.passes
                errorMessage = nil
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body) ?? "Could not read the review's instructions (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the review's instructions: \(error.localizedDescription)"
        }
    }
}

extension RecipeSetupAnswers.JobAnswers {
    /// What the text box shows for `lens`: the person's edit, else the engine's default.
    func reviewText(for lens: String, default text: String) -> String {
        let edit = reviewInstructions[lens] ?? ""
        return edit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? text : edit
    }

    /// Keep what was typed as the edit; text equal to the default, or blank, is no edit (the engine reads blank as unedited).
    mutating func setReview(_ typed: String, for lens: String, default text: String) {
        if typed == text || typed.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            reviewInstructions[lens] = nil
        } else {
            reviewInstructions[lens] = typed
        }
    }
}
