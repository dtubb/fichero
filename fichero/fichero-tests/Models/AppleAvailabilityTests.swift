@testable import Fichero
import XCTest

/// Unit tests for the pure Apple Intelligence availability mapping (#3121/#3118).
/// The available → row-state logic is separated from the probe I/O so it is
/// testable without stubbing the transport.
final class AppleAvailabilityTests: XCTestCase {

    func testAvailableHasNoReason() {
        let status = AppleAvailability.status(available: true, reason: nil)
        XCTAssertTrue(status.available)
        XCTAssertNil(status.reason)
        XCTAssertEqual(status.label, "Available")
    }

    func testAvailableIgnoresReason() {
        // A stray reason on an available probe must not leak into the UI.
        let status = AppleAvailability.status(available: true, reason: "irrelevant")
        XCTAssertTrue(status.available)
        XCTAssertNil(status.reason)
    }

    func testUnavailableSurfacesReasonVerbatim() {
        let status = AppleAvailability.status(available: false, reason: "Apple Intelligence is turned off")
        XCTAssertFalse(status.available)
        XCTAssertEqual(status.reason, "Apple Intelligence is turned off")
        XCTAssertEqual(status.label, "Apple Intelligence is turned off")
    }

    func testUnavailableWithNilReasonFallsBack() {
        let status = AppleAvailability.status(available: false, reason: nil)
        XCTAssertFalse(status.available)
        XCTAssertEqual(status.reason, "Not available on this Mac")
        XCTAssertEqual(status.label, "Not available on this Mac")
    }

    func testUnavailableWithEmptyReasonFallsBack() {
        let status = AppleAvailability.status(available: false, reason: "")
        XCTAssertFalse(status.available)
        XCTAssertEqual(status.reason, "Not available on this Mac")
    }
}
