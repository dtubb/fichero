//
//  HarnessFailFastTests.swift
//  FicheroUITests
//
//  spec: ui-test-harness — `harness.fail-fast-loud` (#4781). Pure decisions, no app launch:
//  a present-but-broken harness fails loud, an absent one skips, and a broken app connection
//  costs one wait, not N x 120 s.
//

import XCTest

@MainActor
final class HarnessFailFastTests: XCTestCase {
    typealias Session = FicheroUISessionTests
    typealias HarnessError = UITestEngineHarness.HarnessError

    func testAbsentHarnessIsASkip() {
        for error in [HarnessError.repoRootNotFound, .venvNotFound] {
            guard case .skip = Session.provisioningOutcome(for: error) else {
                return XCTFail("\(error) is an absent harness and must stay a skip")
            }
        }
    }

    func testPresentButBrokenHarnessFailsLoud() {
        for error in [HarnessError.seedFailed("boom"), .engineDidNotBind("no ready line")] {
            guard case .fail(let message) = Session.provisioningOutcome(for: error) else {
                return XCTFail("\(error) is a broken harness and must fail, not skip")
            }
            XCTAssertTrue(message.contains("harness connection broken — fix this first"))
        }
    }

    func testAnUnknownProvisioningErrorFailsRatherThanSkips() {
        struct Other: Error {}
        guard case .fail = Session.provisioningOutcome(for: Other()) else {
            return XCTFail("an unclassified error must not read as a skip")
        }
    }

    func testSecondWaitAfterAFailureDoesNotReWaitTheFullTimeout() {
        XCTAssertEqual(Session.readyWait(full: 120, priorFailure: false), 120)
        XCTAssertEqual(Session.readyWait(full: 120, priorFailure: true), 0)
    }
}
