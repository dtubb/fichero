import FicheroAPIClient
import Foundation
import OpenAPIRuntime

/// Ready's "Offered later: Train a model of your own for this step" (#5660 item 9,
/// `source.recipe.train-offered-per-step`): the engine's `train_offers` on the Start plan, one per trainable step, each
/// with its ways, where each runs, and how many more corrected lines or pages it needs, in words. Never run at Start
/// (`source.recipe.train-never-automatic`): a way starts only on its own button, by posting the place's action with
/// the engine's params as-is. Kept beside `RecipeSetupStore` so the store's own file stays setup's.
extension RecipeSetupStore {
    typealias TrainOffer = Components.Schemas.TrainOffer
    typealias TrainWay = Components.Schemas.TrainWay
    typealias TrainTarget = Components.Schemas.TrainTarget

    /// The offers on the plan shown, in the recipe's order.
    var trainOffers: [TrainOffer] { startPlan?.trainOffers ?? [] }

    /// The sentences, early, on how many corrected lines training a model of your own will need
    /// (`source.onboard.train-path`): for the steps of `jobs` that are not ready. Never an offer or a greyed row (#5804).
    func trainAhead(forJobs jobs: [String]) -> [String] {
        (startPlan?.trainAhead ?? []).filter { jobs.contains($0.job) }.map(\.sentence)
    }

    /// The offer's need sentence ("Needs 2,000 corrected lines on at least 2 pages; …"), or nil once it is ready.
    nonisolated static func needSentence(_ offer: TrainOffer) -> String? {
        let readiness = offer.readiness.additionalProperties.value
        if readiness["ready"] as? Bool == true { return nil }
        return readiness["sentence"] as? String ?? "Needs more corrected pages."
    }

    /// Whether the app can post this place's action: the engine named the action (`starts` is null for a cluster, which
    /// has no start action yet) and filled its params. Null params: it cannot yet
    /// (no reader has read this project's lines, so a distillation has no teacher).
    nonisolated static func canPost(_ target: TrainTarget) -> Bool {
        target.params != nil && target.starts != nil
    }

    /// Whether this place sends the pages away (Hugging Face Jobs): the person's yes is asked before posting, and
    /// only then is `pages_may_leave` sent.
    nonisolated static func sendsPagesAway(_ target: TrainTarget) -> Bool {
        target.place == "huggingface-jobs"
    }

    /// Why this way cannot start now, in words; nil: its buttons start it.
    nonisolated static func trainDisabledReason(_ offer: TrainOffer, _ way: TrainWay) -> String? {
        if !way.available { return way.why ?? "Not available yet." }
        if let need = needSentence(offer) { return need }
        if !way.targets.contains(where: canPost) { return "No reader has read this project's lines yet." }
        return nil
    }

    /// Start one way of training at one place: its action (`starts`) posted through the audited choke point with
    /// the engine's params as-is, plus `pages_may_leave` only after the person's yes (`pagesMayLeave`) for a place
    /// that sends the pages away. The job id, or nil with the engine's words in `errorMessage`.
    func startTraining(_ offer: TrainOffer, way: TrainWay, at target: TrainTarget,
                       pagesMayLeave: Bool = false) async -> String? {
        guard Self.trainDisabledReason(offer, way) == nil, let params = target.params, let starts = target.starts,
              !Self.sendsPagesAway(target) || pagesMayLeave else { return nil }
        do {
            var value = params.additionalProperties.value
            if Self.sendsPagesAway(target) { value["pages_may_leave"] = true }
            let request = Components.Schemas.InvokeActionRequest(
                name: starts, params: .init(additionalProperties: try OpenAPIObjectContainer(unvalidatedValue: value)))
            switch try await client.api.invokeActionApiActionsInvokePost(body: .json(request)) {
            case .ok(let done):
                let result = try done.body.json.result.value as? [String: (any Sendable)?]
                return (result?["job_id"] as? String) ?? ""
            case .unprocessableContent(let error):
                errorMessage = "Could not train: \((try? error.body.json)?.detail?.description ?? "the engine refused it")."
            case .undocumented(let code, let payload):
                errorMessage = "Could not train: \(await EngineErrorDetail.message(from: payload) ?? "HTTP \(code)")"
            }
        } catch {
            if error.isCancellationError { return nil }
            errorMessage = "Could not train: \(error.localizedDescription)"
        }
        return nil
    }
}

extension Components.Schemas.TrainWay {
    /// One way of an offer, by what it is: a method has more than one (Kraken fine-tunes and distils), so the method
    /// alone made two rows one (the first drawn twice, #5804).
    var wayKey: String { "\(method)/\(how)" }
}
