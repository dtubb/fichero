import FicheroAPIClient
import Foundation

/// Why each default was chosen (`designer.defaults.says-why`, #6052): the engine's table row says it; the app reads it out, in the
/// order the defaults are listed, once per distinct sentence.
struct DefaultWhy: Identifiable, Equatable {
    /// The default it explains (`steps`, `prepare`, `model_kind`, `review`, `cap`).
    let id: String
    /// The answers that chose it: "faded, this mac".
    let because: String
    let why: String

    static let order = ["steps", "prepare", "model_kind", "review", "cap"]

    static func rows(_ why: [String: Components.Schemas.WhyOfDefault]) -> [DefaultWhy] {
        var seen = Set<String>()
        return order.compactMap { key in
            guard let row = why[key], seen.insert(row.why).inserted else { return nil }
            return DefaultWhy(id: key, because: row.because, why: row.why)
        }
    }
}

extension RecipeSetupStore {
    /// Ask the engine why the answers chose the defaults they did (`GET /api/recipes/defaults`); nothing is applied or written.
    func loadDefaultsWhy() async {
        do {
            let query = Operations.RecipeDefaultsApiRecipesDefaultsGet.Input.Query(
                materials: materials.joined(separator: ","), condition: (conditions ?? []).joined(separator: ","),
                places: (how.places ?? []).joined(separator: ","), matters: how.matters, pages: pages)
            switch try await client.api.recipeDefaultsApiRecipesDefaultsGet(query: query) {
            case .ok(let success):
                defaultsWhy = DefaultWhy.rows(try success.body.json.why.additionalProperties)
            default:
                break
            }
        } catch {
            if error.isCancellationError { return }
            // No reasons: Ready shows none; the plan itself is unchanged.
        }
    }

    /// Ask the engine what feeds each of the plan's steps and what it feeds (`GET /api/recipes/chain-risk`), by the step's job.
    func loadChainRisk() async {
        let jobs = (recipe?.steps ?? []).map(\.id)
        guard !jobs.isEmpty else { chainRisk = [:]; return }
        do {
            switch try await client.api.chainRiskApiRecipesChainRiskGet(query: .init(jobs: jobs.joined(separator: ","))) {
            case .ok(let success):
                chainRisk = Dictionary(try success.body.json.steps.map { ($0.job, $0) }, uniquingKeysWith: { first, _ in first })
            default:
                break
            }
        } catch {
            if error.isCancellationError { return }
        }
    }
}
