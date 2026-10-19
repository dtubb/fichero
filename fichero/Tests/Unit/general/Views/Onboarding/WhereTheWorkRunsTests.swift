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

    func testACardShowsWhatIsSetUpAndNothingTicks() {
        let none = WhatFicheroRuns.SetUp()
        XCTAssertNil(none.line(for: .cloud))
        let set = WhatFicheroRuns.SetUp(keys: ["Claude", "Gemini"], hasToken: true, clusters: ["ACENET Siku"])
        XCTAssertEqual(set.line(for: .cloud), "Keys saved: Claude, Gemini")
        XCTAssertEqual(set.line(for: .huggingface), "Token saved")
        XCTAssertEqual(set.line(for: .acenet), "ACENET Siku")
        XCTAssertNil(set.line(for: .thisMac))
        XCTAssertNil(set.line(for: .anotherMac))
    }

    func testASavedTokenReplacesAddATokenButAKeyOrClusterLeavesItsButton() {
        let set = WhatFicheroRuns.SetUp(keys: ["Claude"], hasToken: true, clusters: ["ACENET Siku"])
        XCTAssertTrue(set.hidesButton(for: .huggingface))
        XCTAssertFalse(set.hidesButton(for: .cloud))
        XCTAssertFalse(set.hidesButton(for: .acenet))
        XCTAssertFalse(WhatFicheroRuns.SetUp().hidesButton(for: .huggingface))
    }
}
