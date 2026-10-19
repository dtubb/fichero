@testable import Fichero
import XCTest

/// `source.onboard.first-launch-three-screens` (#5828): Where the Work Runs defaults to this Mac only. The answer is
/// view state; it is the engine's setting with #5810 (GAP).
final class WhereTheWorkRunsTests: XCTestCase {
    func testTheDefaultIsThisMacOnly() {
        XCTAssertEqual(WhereTheWorkRuns.default, .thisMac)
        XCTAssertEqual(WhereTheWorkRuns.thisMac.title, "This Mac only")
    }

    func testTheFourPlacesAreOffered() {
        XCTAssertEqual(WhereTheWorkRuns.allCases, [.thisMac, .anotherMac, .cloud, .cluster])
    }

    func testNoPlacePromisesWhatTheEngineDoesNotHold() {
        for place in WhereTheWorkRuns.allCases { XCTAssertFalse(place.detail.contains("never leave"), place.detail) }
    }
}
