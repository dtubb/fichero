import FicheroAPIClient
import Foundation
import Observation

/// Which search model a project uses, and the run that changes it (`search.embedding.change-is-a-re-embed-run`, #6122):
/// the plan comes first (pages, time, cost), then the person starts the run, which shows in Activity. Search keeps the
/// old vectors until the run finishes; the engine holds all of that, this only asks and says.
@MainActor
@Observable
final class EmbeddingChangeStore {
    private(set) var current: Components.Schemas.EmbeddingChoiceResponse?
    private(set) var plan: Components.Schemas.EmbeddingChangePlan?
    private(set) var started: Components.Schemas.EmbeddingChangeStarted?
    private(set) var errorMessage: String?
    private(set) var isBusy = false
    /// The models the engine offers with their one lines (`GET /api/search/embedding/models`); the built-in list until it answers.
    private(set) var choices = EmbeddingModelChoice.all

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// The model the project uses and how many vectors it holds (`GET /api/search/embedding`).
    func load() async {
        if let listed = await EmbeddingModelChoice.fetch(client: client) { choices = listed }
        do {
            switch try await client.api.getEmbeddingChoiceApiSearchEmbeddingGet(.init()) {
            case .ok(let success):
                current = try success.body.json
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body) ?? "Could not read the search model (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the search model: \(error.localizedDescription)"
        }
    }

    /// What changing to `model` would do, said before anything runs (`GET /api/search/embedding/change-plan`).
    func loadPlan(for model: String) async {
        plan = nil
        started = nil
        errorMessage = nil
        isBusy = true
        defer { isBusy = false }
        do {
            switch try await client.api.getEmbeddingChangePlanApiSearchEmbeddingChangePlanGet(query: .init(model: model)) {
            case .ok(let success):
                plan = try success.body.json
            case .unprocessableContent:
                errorMessage = "The engine does not know that search model."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body) ?? "Could not work out the plan (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not work out the plan: \(error.localizedDescription)"
        }
    }

    /// Start the run for the plan the person has seen (`POST /api/search/embedding/change`, confirmed). Only with a plan
    /// in hand, and only for the model it was made for.
    func start() async {
        guard let plan, !plan.same, !isBusy else { return }
        errorMessage = nil
        isBusy = true
        defer { isBusy = false }
        do {
            switch try await client.api.startEmbeddingChangeApiSearchEmbeddingChangePost(
                body: .json(.init(model: plan.toModel, confirm: true))
            ) {
            case .ok(let success):
                started = try success.body.json
            case .unprocessableContent:
                errorMessage = "The engine did not accept the request."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body) ?? "Could not start the run (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not start the run: \(error.localizedDescription)"
        }
    }

    // MARK: Words

    /// "About 4 minutes" / "under a minute": the engine's estimate, said as one.
    static func time(seconds: Int) -> String {
        if seconds < 60 { return "under a minute" }
        let minutes = Int((Double(seconds) / 60).rounded())
        if minutes < 90 { return "about \(minutes) minute\(minutes == 1 ? "" : "s")" }
        let hours = Double(minutes) / 60
        return "about \(String(format: "%.1f", hours)) hours"
    }

    /// The plan in one sentence, before anything runs.
    static func sentence(for plan: Components.Schemas.EmbeddingChangePlan,
                         choices: [EmbeddingModelChoice] = EmbeddingModelChoice.all) -> String {
        var parts = ["\(plan.pages) page\(plan.pages == 1 ? "" : "s")"]
        if plan.entities > 0 { parts.append("\(plan.entities) name\(plan.entities == 1 ? "" : "s")") }
        if plan.claims > 0 { parts.append("\(plan.claims) statement\(plan.claims == 1 ? "" : "s")") }
        let cost = plan.costUsd == 0 ? "free, it runs on this Mac" : String(format: "$%.2f", plan.costUsd)
        return "Embeds " + parts.joined(separator: ", ") + " again with \(EmbeddingModelChoice.name(of: plan.toModel, in: choices)): "
            + time(seconds: plan.secondsEstimate) + ", " + cost + "."
    }
}
