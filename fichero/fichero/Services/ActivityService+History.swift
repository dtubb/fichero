import FicheroAPIClient
import Foundation

extension ActivityService {
    /// The Activity Monitor's graphs (`GET /api/activity/history`, `activity.window.bottom-panel`, #6588): per minute over the
    /// last `minutes`, pages done and failed, dollars and tokens; pages by where they ran; today's spend by provider.
    func history(minutes: Int = 60) async throws -> ActivityHistory {
        let response = try await client.api.getActivityHistoryApiActivityHistoryGet(query: .init(minutes: minutes))
        switch response {
        case .ok(let okResponse):
            return ActivityHistory(try okResponse.body.json)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }
}

/// One project's history, as the panel reads it: the engine's answer without its generated types.
struct ActivityHistory: Equatable {
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
    /// The Models tree (`GET /api/activity/models`, `activity.window.models-tree`, #6588): every model used today or held now.
    func models() async throws -> [ActivityModelEntry] {
        switch try await client.api.activityModelsApiActivityModelsGet() {
        case .ok(let okResponse):
            return try okResponse.body.json.models?.map(ActivityModelEntry.init) ?? []
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }
}

/// One model of the tree, as the sidebar reads it: the engine's answer without its generated types.
struct ActivityModelEntry: Equatable, Identifiable, Sendable {
    enum Place: String, CaseIterable, Sendable {
        case thisMac = "this-mac", remote, cloud

        var title: String {
            switch self {
            case .thisMac: "This Mac"
            case .remote: "Remote"
            case .cloud: "Cloud"
            }
        }

        var icon: String {
            switch self {
            case .thisMac: "desktopcomputer"
            case .remote: "server.rack"
            case .cloud: "cloud"
            }
        }
    }

    let id: String
    let name: String
    let place: Place
    let provider: String
    var loaded = false
    var active = false
    var memoryBytes: Int?
    var memoryEstimated = false
    var running = 0
    var pagesToday = 0
    var callsToday = 0

    init(id: String, name: String, place: Place, provider: String, loaded: Bool = false, active: Bool = false,
         memoryBytes: Int? = nil, memoryEstimated: Bool = false, running: Int = 0, pagesToday: Int = 0, callsToday: Int = 0) {
        self.id = id; self.name = name; self.place = place; self.provider = provider; self.loaded = loaded
        self.active = active; self.memoryBytes = memoryBytes; self.memoryEstimated = memoryEstimated
        self.running = running; self.pagesToday = pagesToday; self.callsToday = callsToday
    }

    init(_ model: Components.Schemas.ActivityModel) {
        self.init(id: model.id, name: model.name, place: Place(rawValue: model.place.rawValue) ?? .thisMac,
                  provider: model.provider, loaded: model.loaded, active: model.active, memoryBytes: model.memoryBytes,
                  memoryEstimated: model.memoryEstimated ?? false, running: model.running ?? 0,
                  pagesToday: model.pagesToday ?? 0, callsToday: model.callsToday ?? 0)
    }

    /// "312 MB", "~2.5 GB" when estimated, "—" when nothing measures it (`activity.resources.everything-measured`).
    var memoryWords: String {
        guard let memoryBytes else { return "—" }
        let words = ByteCountFormatter.string(fromByteCount: Int64(memoryBytes), countStyle: .memory)
        return memoryEstimated ? "~\(words)" : words
    }

    /// The icon's symbol: filled while it is loaded, hollow when not (decision 33).
    var symbol: String { loaded ? "cpu.fill" : "cpu" }

    /// Several projects' lists as one: a model in two is one row, loaded or active if either says so, its counts added.
    static func merged(_ lists: [[ActivityModelEntry]]) -> [ActivityModelEntry] {
        var byId: [String: ActivityModelEntry] = [:]
        var order: [String] = []
        for model in lists.joined() {
            guard var seen = byId[model.id] else { byId[model.id] = model; order.append(model.id); continue }
            seen.loaded = seen.loaded || model.loaded
            seen.active = seen.active || model.active
            seen.memoryBytes = seen.memoryBytes ?? model.memoryBytes
            seen.running += model.running
            seen.pagesToday += model.pagesToday
            seen.callsToday += model.callsToday
            byId[model.id] = seen
        }
        return order.compactMap { byId[$0] }
    }

    /// The tree: place › provider › its models, places in their order, empty places left out.
    static func tree(_ models: [ActivityModelEntry]) -> [(place: Place, providers: [(name: String, models: [ActivityModelEntry])])] {
        Place.allCases.compactMap { place in
            let here = models.filter { $0.place == place }
            guard !here.isEmpty else { return nil }
            let names = here.map(\.provider).reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
            return (place, names.map { name in (name, here.filter { $0.provider == name }) })
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
