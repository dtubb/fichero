import FicheroAPIClient
import Foundation

extension ActivityService {
    /// The Activity Monitor's graphs (`GET /api/activity/history`, `activity.window.bottom-panel`, #6588): per minute over the
    /// last `minutes`, pages done and failed, dollars and tokens; pages by where they ran; today's spend by provider.
    func history(minutes: Int = 60) async throws -> ActivityHistoryFigures {
        let response = try await client.api.getActivityHistoryApiActivityHistoryGet(query: .init(minutes: minutes))
        switch response {
        case .ok(let okResponse):
            return ActivityHistoryFigures(try okResponse.body.json)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }
}

/// One project's history, as the panel reads it: the engine's answer without its generated types.
struct ActivityHistoryFigures: Equatable {
    struct Minute: Equatable, Identifiable {
        let start: Date
        var pagesDone = 0
        var pagesFailed = 0
        var spendUsd = 0.0
        var tokens = 0
        var id: Date { start }
    }

    var minutes: [Minute] = []
    /// Pages done in the window by where they ran: "this-mac", "other-mac", "cloud", "cluster".
    var byRuntime: [String: Int] = [:]
    var todaySpendUsd = 0.0
    var todaySpendByProvider: [String: Double] = [:]

    init(minutes: [Minute] = [], byRuntime: [String: Int] = [:], todaySpendUsd: Double = 0,
         todaySpendByProvider: [String: Double] = [:]) {
        self.minutes = minutes
        self.byRuntime = byRuntime
        self.todaySpendUsd = todaySpendUsd
        self.todaySpendByProvider = todaySpendByProvider
    }

    init(_ answer: Components.Schemas.ActivityHistory) {
        minutes = answer.buckets.map {
            Minute(start: $0.start, pagesDone: $0.pagesDone ?? 0, pagesFailed: $0.pagesFailed ?? 0,
                   spendUsd: $0.spendUsd ?? 0, tokens: $0.tokens ?? 0)
        }
        byRuntime = answer.byRuntime?.additionalProperties ?? [:]
        todaySpendUsd = answer.todaySpendUsd ?? 0
        todaySpendByProvider = answer.todaySpendByProvider?.additionalProperties ?? [:]
    }
}

extension ActivityService {
    /// The Models tree (`GET /api/activity/models`, `activity.window.models-tree`, #6588): every model used
    /// today, held now or installed on this Mac, and every place set up.
    func models() async throws -> ActivityModelsAnswer {
        switch try await client.api.activityModelsApiActivityModelsGet() {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return ActivityModelsAnswer(models: body.models?.map(ActivityModelEntry.init) ?? [],
                                        places: body.places?.map(ActivityModelEntry.SetUp.init) ?? [])
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }
}

extension ActivityService {
    /// The Recipes view (`GET /api/activity/recipes`, `activity.window.recipes`, #6588): each recipe with its runs and steps.
    func recipes(days: Int = 30) async throws -> [Components.Schemas.RecipeRow] {
        switch try await client.api.activityRecipesApiActivityRecipesGet(query: .init(days: days)) {
        case .ok(let okResponse):
            return try okResponse.body.json.recipes ?? []
        case .unprocessableContent(let error):
            throw ActivityServiceError.validationError((try? error.body.json)?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }
}
