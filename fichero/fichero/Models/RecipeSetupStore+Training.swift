import FicheroAPIClient
import Foundation

/// Ready's "Offered later: Train a model on your corrected pages" (#5660 item 9, `source.recipe.train-offered-per-step`):
/// the engine's `train_offers` on the Start plan, one per trainable step, each with its ways, where each runs and how
/// many more corrected lines or pages it needs, in words. Never run at Start (`source.recipe.train-never-automatic`):
/// a way starts only on its own button. Kept beside `RecipeSetupStore` so the store's own file stays setup's.
extension RecipeSetupStore {
    typealias TrainOffer = Components.Schemas.TrainOffer
    typealias TrainWay = Components.Schemas.TrainWay
    typealias TrainTarget = Components.Schemas.TrainTarget

    /// The audited action that fine-tunes a layout model on this Mac: it needs only the project's pages.
    nonisolated static let regionsAction = "training.start_regions_here"

    /// The offers on the plan shown, in the recipe's order.
    var trainOffers: [TrainOffer] { startPlan?.trainOffers ?? [] }

    /// The offer's need sentence ("Needs 2,000 corrected lines on at least 2 pages; …"), or nil once it is ready.
    nonisolated static func needSentence(_ offer: TrainOffer) -> String? {
        let readiness = offer.readiness.additionalProperties.value
        if readiness["ready"] as? Bool == true { return nil }
        return readiness["sentence"] as? String ?? "Needs more corrected pages."
    }

    /// Whether the app can post this place's action. The Kraken and vision-model actions also need the reading that
    /// teaches them, which the offer does not carry yet (the engine will add it as `params`, posted as-is, like a
    /// download's): when it does, this is the one condition that enables them.
    nonisolated static func canPost(_ target: TrainTarget) -> Bool {
        target.starts == regionsAction
    }

    /// Why this way cannot start now, in words; nil: its buttons start it.
    nonisolated static func trainDisabledReason(_ offer: TrainOffer, _ way: TrainWay) -> String? {
        if !way.available { return way.why ?? "Not available yet." }
        if let need = needSentence(offer) { return need }
        if !way.targets.contains(where: canPost) {
            return "Not available yet: Fichero does not yet say which reading teaches this model."
        }
        return nil
    }

    /// Start one way of training at one place, through its audited action; the job id, or nil with the engine's
    /// words in `errorMessage`. The pages are the plan's folder, else the whole project (its top-level items).
    func startTraining(_ offer: TrainOffer, way: TrainWay, at target: TrainTarget) async -> String? {
        guard Self.trainDisabledReason(offer, way) == nil, Self.canPost(target) else { return nil }
        do {
            let scope: [String]
            if let folder = startPlanFolderId {
                scope = [folder]
            } else if case .ok(let roots) = try await client.api.listRootsApiDocumentsRootsGet(.init()) {
                scope = try roots.body.json.items.compactMap(\.id)
            } else {
                scope = []
            }
            guard !scope.isEmpty else {
                errorMessage = "Could not train: the project has no pages to train on."
                return nil
            }
            switch try await client.api.startRegionsTrainingHereApiTrainingRegionsHerePost(
                body: .json(.init(name: "regions", scopeIds: scope))
            ) {
            case .ok(let started):
                return try started.body.json.jobId
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
