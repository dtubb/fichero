import FicheroAPIClient
import XCTest

@testable import Fichero

/// `ai.cloud.monthly-cap-in-settings` / `ai.cloud.daily-cap` (#6346, #6347): the Settings fields send only what moved.
final class CloudCapsSettingsTests: XCTestCase {
    func testNothingMovedSendsNothing() {
        XCTAssertEqual(CloudCapsSection.edits(monthly: 10, daily: nil, heldMonthly: 10, heldDaily: nil), [])
        XCTAssertEqual(CloudCapsSection.edits(monthly: 25, daily: 5, heldMonthly: 25, heldDaily: 5), [])
    }

    func testAMovedMonthlyCapIsSentAlone() {
        let edits = CloudCapsSection.edits(monthly: 40, daily: nil, heldMonthly: 10, heldDaily: nil)
        XCTAssertEqual(edits, [CloudCapsSection.Edit(which: .monthly, usd: 40)])
    }

    func testADailyCapIsSetAndCleared() {
        XCTAssertEqual(CloudCapsSection.edits(monthly: 10, daily: 5, heldMonthly: 10, heldDaily: nil),
                       [CloudCapsSection.Edit(which: .daily, usd: 5)])
        XCTAssertEqual(CloudCapsSection.edits(monthly: 10, daily: nil, heldMonthly: 10, heldDaily: 5),
                       [CloudCapsSection.Edit(which: .daily, usd: nil)])
    }

    func testAnEmptiedMonthlyFieldClearsItBackToTheDefault() {
        let edits = CloudCapsSection.edits(monthly: nil, daily: nil, heldMonthly: 40, heldDaily: nil)
        XCTAssertEqual(edits, [CloudCapsSection.Edit(which: .monthly, usd: nil)])
        XCTAssertEqual(CloudCapsSection.edits(monthly: nil, daily: nil, heldMonthly: 10, heldDaily: nil), [],
                       "empty is the default 10: already held, nothing to send")
    }

    func testZeroIsACapNotAnEmptyField() {
        XCTAssertEqual(CloudCapsSection.edits(monthly: 0, daily: 0, heldMonthly: 10, heldDaily: nil),
                       [CloudCapsSection.Edit(which: .monthly, usd: 0), CloudCapsSection.Edit(which: .daily, usd: 0)])
    }
}
