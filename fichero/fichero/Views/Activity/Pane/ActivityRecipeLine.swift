import FicheroAPIClient
import Foundation

/// One line of the Recipes view (`activity.window.recipes`, decision 37, #6588): a recipe, one of its runs, or a run's step,
/// with the rates that compare them. Built from the engine's `GET /api/activity/recipes`, never worked out here.
struct ActivityRecipeLine: Identifiable, Equatable, Sendable {
    enum Level: Sendable { case recipe, run, step }

    let id: String
    let level: Level
    let name: String
    var runs: Int?
    var model: String?
    var pagesDone = 0
    var pagesFailed = 0
    var failedPct: Double?
    var secondsPerPage: Double?
    var costPerPage: Double?
    var when: Date?
    var children: [ActivityRecipeLine]?

    /// "15%", "0%", or blank when nothing was read.
    var failedWords: String { failedPct.map { String(format: "%.0f%%", $0) } ?? "" }
    /// "4 s", "1.2 min", or blank.
    var perPageWords: String {
        guard let secondsPerPage else { return "" }
        return secondsPerPage < 90 ? String(format: "%.0f s", secondsPerPage) : String(format: "%.1f min", secondsPerPage / 60)
    }
    /// "$0.004", "Free" for priced at zero, blank for local work (`activity.pane.cost-per-row-and-totals`).
    var costWords: String {
        guard let costPerPage else { return "" }
        return costPerPage == 0 ? "Free" : String(format: "$%.3f", costPerPage)
    }

    private static func date(_ text: String?) -> Date? {
        text.flatMap { ISO8601DateFormatter.withFractions.date(from: $0) ?? ISO8601DateFormatter().date(from: $0) }
    }

    /// The engine's recipes as lines: each recipe over its runs (newest first), each run over its steps.
    static func lines(_ recipes: [Components.Schemas.RecipeRow]) -> [ActivityRecipeLine] {
        recipes.map { recipe in
            ActivityRecipeLine(
                id: "recipe:\(recipe.id)", level: .recipe, name: recipe.name, runs: recipe.runCount ?? 0,
                pagesDone: recipe.pagesDone ?? 0, pagesFailed: recipe.pagesFailed ?? 0, failedPct: recipe.failedPct,
                secondsPerPage: recipe.secondsPerPage, costPerPage: recipe.costPerPage, when: date(recipe.lastRun),
                children: (recipe.runs ?? []).map { run in
                    let models = Set((run.steps ?? []).compactMap(\.model))
                    return ActivityRecipeLine(
                        id: "run:\(run.id)", level: .run, name: run.status.capitalized,
                        model: models.count == 1 ? models.first : (models.isEmpty ? nil : "\(models.count) models"),
                        pagesDone: run.pagesDone ?? 0, pagesFailed: run.pagesFailed ?? 0, failedPct: run.failedPct,
                        secondsPerPage: run.secondsPerPage, costPerPage: run.costPerPage, when: date(run.startedAt),
                        children: (run.steps ?? []).map { step in
                            ActivityRecipeLine(
                                id: "step:\(run.id):\(step.id)", level: .step, name: step.name, model: step.model,
                                pagesDone: step.pagesDone ?? 0, pagesFailed: step.pagesFailed ?? 0,
                                failedPct: (step.pagesDone ?? 0) + (step.pagesFailed ?? 0) > 0
                                    ? 100 * Double(step.pagesFailed ?? 0) / Double((step.pagesDone ?? 0) + (step.pagesFailed ?? 0))
                                    : nil,
                                secondsPerPage: step.secondsPerPage, costPerPage: step.costPerPage, children: nil)
                        })
                })
        }
    }
}
