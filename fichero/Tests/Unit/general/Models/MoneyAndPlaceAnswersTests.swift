@testable import Fichero
import FicheroAPIClient
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

    // ai.where.cloud-spend-cap (#5943): Set Up sets the cloud cap beside the estimate, under the engine's key.
    @Test func theCloudCapIsSavedUnderTheEnginesKeyAndLeftOutUnanswered() throws {
        let set = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
            RecipeSetupAnswers(cloudSpendCapUsd: 25))) as? [String: Any]
        #expect(set?["cloud_spend_cap_usd"] as? Double == 25)
        let unset = try JSONSerialization.jsonObject(with: JSONEncoder().encode(RecipeSetupAnswers())) as? [String: Any]
        #expect(unset?["cloud_spend_cap_usd"] == nil, "unanswered keeps the saved cap or the engine's US$10")
    }

    @Test func theCapLineSaysWhatIsLeftAndWhetherStartAsks() {
        func line(estimate: Double?, over: Bool) -> Components.Schemas.CloudCapLine {
            .init(capUsd: 10, spentUsd: 4, remainingUsd: 6, estimateUsd: estimate, over: over, unpriced: estimate == nil)
        }
        func usd(_ value: Double) -> String { value.formatted(.currency(code: "USD")) }  // the Mac's locale, as the row
        let month = "\(usd(4)) spent this month, \(usd(6)) left."
        #expect(RecipeCloudCapRow.words(line(estimate: 2, over: false)) == "\(month) This run may cost \(usd(2)).")
        #expect(RecipeCloudCapRow.words(line(estimate: 9, over: true))
            == "\(month) This run may cost \(usd(9)), more than that: Start asks first.")
        #expect(RecipeCloudCapRow.words(line(estimate: nil, over: false)) == "\(month) This run's cloud cost is not known yet.")
    }
}

/// `ai.cloud.set-up-shows-the-defaults` (#6346, #6347): Set Up's daily field and the app's figures, said until the project answers.
struct CloudDailyCapSetUpTests {
    private func line(daily: Double?) -> Components.Schemas.CloudCapLine {
        .init(capUsd: 10, spentUsd: 0, remainingUsd: 10, over: false, dailyCapUsd: daily, unpriced: false)
    }

    @Test func theDailyCapIsSavedUnderTheEnginesKeyAndLeftOutUnanswered() throws {
        let set = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
            RecipeSetupAnswers(cloudDailyCapUsd: 3))) as? [String: Any]
        #expect(set?["cloud_daily_cap_usd"] as? Double == 3)
        let unset = try JSONSerialization.jsonObject(with: JSONEncoder().encode(RecipeSetupAnswers())) as? [String: Any]
        #expect(unset?["cloud_daily_cap_usd"] == nil)
    }

    @Test func aMovedDailyFieldIsSentAndAnEmptiedOneClearsTheProjectsOwn() {
        let held = line(daily: 3)
        #expect(CloudCapFields.change(monthly: 10, project: nil, line: held, daily: 3, heldDaily: 3).daily == nil)
        #expect(CloudCapFields.change(monthly: 10, project: nil, line: held, daily: 5, heldDaily: 3).daily == 5)
        let cleared = CloudCapFields.change(monthly: 10, project: nil, line: held, daily: nil, heldDaily: 3)
        #expect(cleared.clearDaily && cleared.daily == nil)
        #expect(CloudCapFields.change(monthly: 10, project: nil, line: held, daily: nil, heldDaily: nil).clearDaily == false)
    }

    @Test func theAppsFiguresAreSaidUntilTheProjectAnswers() {
        let words = CloudCapFields.defaultWords(ownMonthly: nil, ownDaily: nil, line: line(daily: nil))
        #expect(words?.contains("a day, as Settings: no limit") == true && words?.contains("a month, as Settings:") == true)
        #expect(CloudCapFields.defaultWords(ownMonthly: 20, ownDaily: 2, line: line(daily: 2)) == nil)
        #expect(CloudCapFields.dailyPrompt(line(daily: nil)) == "No limit")
    }
}
