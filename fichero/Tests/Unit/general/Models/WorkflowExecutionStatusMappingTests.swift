@testable import Fichero
import XCTest

/// Completes coverage of WorkflowExecutionService.mapStatus. WorkflowStreamConnectionTests
/// checks the canonical raws (completed/error/failed/cancelled/stopped/deleted);
/// this pins the untested branches: `paused`, the synonym groups, the nil/unknown
/// → .running default, and case-insensitivity. Pure static mapping, no engine.
@MainActor  // mapStatus is main-actor-isolated (Swift 6); sync helpers need the case isolated.
final class WorkflowExecutionStatusMappingTests: XCTestCase {

    private func map(_ raw: String?) -> ExecutionStatus {
        WorkflowExecutionService.mapStatus(raw)
    }

    func testPausedMapsToPaused() {
        XCTAssertEqual(map("paused"), .paused)
    }

    func testCompletedSynonyms() {
        for raw in ["complete", "success", "succeeded"] {
            XCTAssertEqual(map(raw), .completed, "raw=\(raw)")
        }
    }

    func testCancelledSpellingVariant() {
        // British "cancelled" is covered elsewhere; American "canceled" here.
        XCTAssertEqual(map("canceled"), .cancelled)
    }

    func testStoppedSynonym() {
        XCTAssertEqual(map("stop_requested"), .stopped)
    }

    /// nil and any unrecognized value (e.g. the 202 "accepted" handshake state)
    /// collapse to .running — a valid case rather than a decode failure.
    func testNilAndUnknownDefaultToRunning() {
        XCTAssertEqual(map(nil), .running)
        XCTAssertEqual(map("accepted"), .running)
        XCTAssertEqual(map("something_new"), .running)
        XCTAssertEqual(map(""), .running)
    }

    /// The switch lowercases first, so mixed-case backend values still map.
    func testCaseInsensitiveMapping() {
        XCTAssertEqual(map("COMPLETED"), .completed)
        XCTAssertEqual(map("Paused"), .paused)
        XCTAssertEqual(map("Stop_Requested"), .stopped)
    }
}
