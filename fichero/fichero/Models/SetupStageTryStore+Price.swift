import FicheroAPIClient
import Foundation

extension SetupStageTryStore {
    /// "Compare on These Pages", with its price when a candidate leaves this Mac (`wide.try.paid-with-the-price-on-the-button`, #5806):
    /// "Compare on These Pages, about $0.12", or "…, a cost that is not known" when the engine cannot price it. Pure, for the tests.
    nonisolated static func compareTitle(price: Components.Schemas.TryPrice?) -> String {
        let base = "Compare on These Pages"
        guard let price, price.cloud else { return base }
        guard let cost = price.costUsd else { return base + ", a cost that is not known" }
        return base + ", about " + cost.formatted(.currency(code: "USD"))
    }

    /// Ask the engine what a try of the stage would cost (`GET /api/recipes/stages/{stage}/try-price`), before the button is
    /// pressed; nothing is started or written. A failed read leaves the button without a price: the try still asks first.
    func loadPrice() async {
        do {
            if case .ok(let success) = try await client.api.stageTryPriceApiRecipesStagesStageTryPriceGet(path: .init(stage: stageId)) {
                price = try success.body.json
            }
        } catch {
            if error.isCancellationError { return }
        }
    }
}
