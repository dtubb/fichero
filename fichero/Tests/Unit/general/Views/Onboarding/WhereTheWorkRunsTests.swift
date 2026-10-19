@testable import Fichero
import XCTest

/// `source.onboard.first-launch-three-screens` (#5828): Where the Work Runs defaults to this Mac only and keeps the answer.
final class WhereTheWorkRunsTests: XCTestCase {
    private func defaults() -> UserDefaults {
        let suite = "WhereTheWorkRunsTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { defaults.removePersistentDomain(forName: suite) }
        return defaults
    }

    func testTheDefaultIsThisMacOnly() {
        XCTAssertEqual(WhereTheWorkRuns.current(defaults()), .thisMac)
        XCTAssertEqual(WhereTheWorkRuns.thisMac.title, "This Mac only")
    }

    func testTheFourPlacesAreOffered() {
        XCTAssertEqual(WhereTheWorkRuns.allCases, [.thisMac, .anotherMac, .cloud, .cluster])
    }

    func testTheAnswerIsKept() {
        let store = defaults()
        WhereTheWorkRuns.keep(.cloud, store)
        XCTAssertEqual(WhereTheWorkRuns.current(store), .cloud)
    }
}
