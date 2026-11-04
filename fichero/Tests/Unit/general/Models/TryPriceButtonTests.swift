@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `wide.try.paid-with-the-price-on-the-button` (#5806): the first Compare button says the price the engine read.
struct TryPriceButtonTests {
    private func price(_ json: String) throws -> Components.Schemas.TryPrice {
        try JSONDecoder().decode(Components.Schemas.TryPrice.self, from: Data(json.utf8))
    }

    @Test func aCloudTryNamesItsPriceAndALocalOneNamesNone() throws {
        let cost = (0.12).formatted(.currency(code: "USD"))
        #expect(SetupStageTryStore.compareTitle(price: try price(#"{"pages":5,"cloud":true,"cost_usd":0.12}"#))
                == "Compare on These Pages, about \(cost)")
        #expect(SetupStageTryStore.compareTitle(price: try price(#"{"pages":5,"cloud":false}"#)) == "Compare on These Pages")
        #expect(SetupStageTryStore.compareTitle(price: nil) == "Compare on These Pages")
    }

    @Test func aCloudTryTheEngineCannotPriceSaysSo() throws {
        #expect(SetupStageTryStore.compareTitle(price: try price(#"{"pages":5,"cloud":true}"#))
                == "Compare on These Pages, a cost that is not known")
    }
}
