@testable import Fichero
import XCTest

/// Unit tests for the pure local-inference presentation mapping (#3120).
/// Exercises the state machine directly — no transport stub needed because the
/// display logic is separated from `LocalInferenceStore`'s I/O.
final class LocalInferenceDisplayTests: XCTestCase {

    // MARK: Service state → badge

    func testHealthyBadge() {
        let badge = LocalInferenceDisplay.badge(state: "healthy", lastError: nil)
        XCTAssertEqual(badge.text, "Healthy")
        XCTAssertEqual(badge.tint, .success)
    }

    func testStartingBadge() {
        XCTAssertEqual(LocalInferenceDisplay.badge(state: "starting", lastError: nil).tint, .active)
    }

    func testDegradedBadge() {
        XCTAssertEqual(LocalInferenceDisplay.badge(state: "degraded", lastError: nil).tint, .warning)
    }

    func testStoppedBadge() {
        let badge = LocalInferenceDisplay.badge(state: "stopped", lastError: nil)
        XCTAssertEqual(badge.text, "Stopped")
        XCTAssertEqual(badge.tint, .neutral)
    }

    func testFailedBadgeSurfacesErrorVerbatim() {
        let badge = LocalInferenceDisplay.badge(state: "failed", lastError: "port 8123 in use")
        XCTAssertEqual(badge.text, "Failed — port 8123 in use")
        XCTAssertEqual(badge.tint, .error)
    }

    func testFailedBadgeWithoutErrorStillReadsFailed() {
        let badge = LocalInferenceDisplay.badge(state: "failed", lastError: nil)
        XCTAssertEqual(badge.text, "Failed")
        XCTAssertEqual(badge.tint, .error)
    }

    func testFailedBadgeIgnoresEmptyError() {
        XCTAssertEqual(LocalInferenceDisplay.badge(state: "failed", lastError: "").text, "Failed")
    }

    func testUnknownStateFallsBackNeutral() {
        let badge = LocalInferenceDisplay.badge(state: "provisioning", lastError: nil)
        XCTAssertEqual(badge.text, "Provisioning")
        XCTAssertEqual(badge.tint, .neutral)
    }

    // MARK: Job terminal detection (drives the poll loop)

    func testTerminalOnError() {
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "running", error: "boom", percent: 20))
    }

    func testTerminalOnFullPercent() {
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "running", error: nil, percent: 100))
    }

    func testTerminalOnDoneState() {
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "completed", error: nil, percent: nil))
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "cancelled", error: nil, percent: nil))
    }

    func testNotTerminalMidDownload() {
        XCTAssertFalse(LocalInferenceDisplay.isTerminal(state: "downloading", error: nil, percent: 42))
    }

    func testNotTerminalWithNoSignal() {
        XCTAssertFalse(LocalInferenceDisplay.isTerminal(state: nil, error: nil, percent: nil))
    }

    // MARK: Catalog row — unsupported entries stay visible but greyed (#3119)

    func testSupportedInstalledRow() {
        let row = LocalInferenceDisplay.row(supported: true, unsupportedReason: nil, installed: true)
        XCTAssertTrue(row.installed)
        XCTAssertFalse(row.disabled)
        XCTAssertNil(row.unsupportedReason)
    }

    func testUnsupportedRowKeepsReason() {
        let row = LocalInferenceDisplay.row(
            supported: false,
            unsupportedReason: "requires 16 GB unified memory",
            installed: false
        )
        XCTAssertTrue(row.disabled)
        XCTAssertEqual(row.unsupportedReason, "requires 16 GB unified memory")
    }

    func testNilSupportedDefaultsSupported() {
        let row = LocalInferenceDisplay.row(supported: nil, unsupportedReason: "ignored", installed: nil)
        XCTAssertFalse(row.disabled)
        XCTAssertFalse(row.installed)
        XCTAssertNil(row.unsupportedReason)
    }

    // MARK: Download progress fraction

    func testPercentTakesPrecedence() {
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: 1, total: 4, percent: 50), 0.5)
    }

    func testFallsBackToCurrentOverTotal() {
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: 3, total: 4, percent: nil), 0.75)
    }

    func testIndeterminateWhenTotalUnknown() {
        XCTAssertNil(LocalInferenceDisplay.progressFraction(current: 3, total: nil, percent: nil))
        XCTAssertNil(LocalInferenceDisplay.progressFraction(current: 3, total: 0, percent: nil))
    }

    func testFractionClampedToUnitRange() {
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: nil, total: nil, percent: 150), 1)
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: nil, total: nil, percent: -10), 0)
    }
}
