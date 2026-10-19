@testable import Fichero
import Foundation
import Testing

/// `source.onboard.spend-cap` and `source.onboard.copies-may-stay-on-cluster` (#5769): saved under the engine's names,
/// and left out while unanswered so the saved value (or the engine's default) stands.
struct MoneyAndPlaceAnswersTests {
    @Test func theAnswersUseTheEnginesKeys() throws {
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
            RecipeSetupAnswers(hfSpendCapUsd: 5, copiesMayStayOnCluster: false))) as? [String: Any]
        #expect(json?["hf_spend_cap_usd"] as? Double == 5)
        #expect(json?["copies_may_stay_on_cluster"] as? Bool == false)
    }

    @Test func unansweredIsLeftOut() throws {
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(RecipeSetupAnswers())) as? [String: Any]
        #expect(json?["hf_spend_cap_usd"] == nil)
        #expect(json?["copies_may_stay_on_cluster"] == nil)
    }
}
