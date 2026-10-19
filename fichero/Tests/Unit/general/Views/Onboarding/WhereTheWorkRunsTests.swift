@testable import Fichero
import XCTest

/// `source.onboard.places-cap-projects` (#5828): the screen shows the engine's ids; this Mac is the default.
final class WhereTheWorkRunsTests: XCTestCase {
    func testTheDefaultIsThisMacOnly() {
        XCTAssertEqual(WhereTheWorkRuns.default, .thisMac)
    }

    func testTheFivePlacesAreTheEnginesIds() {
        XCTAssertEqual(WhereTheWorkRuns.allCases.map(\.rawValue),
                       ["this-mac", "another-mac", "cloud", "acenet", "huggingface"])
    }
}
