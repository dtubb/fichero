@testable import Fichero
import XCTest

/// Pure-function coverage for `ActivityViewHelpers` — the level colours and
/// duration formatter that back the Activity views. No network / SwiftUI needed:
/// every function here is a deterministic `static`. Guards the boundary logic in
/// `formatDuration` against silent regressions (the status mappings went with
/// the five-section details view, #5561).
final class ActivityViewHelpersTests: XCTestCase {

    // MARK: - levelColor default branch

    func testLevelColorDefaultsForUnknownLevel() {
        // Known levels don't crash; unknown falls to the default (.primary).
        XCTAssertEqual(ActivityViewHelpers.levelColor("error"), .red)
        XCTAssertEqual(ActivityViewHelpers.levelColor("warning"), .orange)
        XCTAssertEqual(ActivityViewHelpers.levelColor("info"), .blue)
        XCTAssertEqual(ActivityViewHelpers.levelColor("trace"), .primary)
        XCTAssertEqual(ActivityViewHelpers.levelColor(""), .primary)
    }

    // MARK: - formatDuration boundaries

    func testFormatDurationMilliseconds() {
        XCTAssertEqual(ActivityViewHelpers.formatDuration(0), "0ms")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(1), "1ms")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(999), "999ms")
    }

    func testFormatDurationSecondsBoundary() {
        // Exactly 1000ms crosses into the seconds format.
        XCTAssertEqual(ActivityViewHelpers.formatDuration(1000), "1.0s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(1500), "1.5s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(59999), "60.0s")
    }

    func testFormatDurationMinutesBoundary() {
        // Exactly 60000ms crosses into the minutes+seconds format.
        XCTAssertEqual(ActivityViewHelpers.formatDuration(60000), "1m 0s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(90000), "1m 30s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(3_661_000), "61m 1s")
    }
}
