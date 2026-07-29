@testable import Fichero
import Foundation
import XCTest

/// Decode rule for backend-work / library-opened signals folded onto the
/// activity stream (#2279). `BackendActivityEvent.init?(activityMetadata:)` is
/// pure, so these run without a backend — they pin the exact wire shape codex
/// emits (`change_type` + `change_metadata` JSON string).
final class BackendActivityEventTests: XCTestCase {

    /// The wire shape from `_change_event_to_activity_response`: flattened
    /// metadata with `change_metadata` as a JSON string of the inner payload.
    private func frame(changeType: String, runId: String? = nil, timestamp: String = "t0",
                       inner: [String: String]) -> [String: String] {
        let json = String(data: try! JSONSerialization.data(withJSONObject: inner), encoding: .utf8)!
        var metadata: [String: String] = ["change_type": changeType, "ts": timestamp, "change_metadata": json]
        if let runId { metadata["run_id"] = runId }
        return metadata
    }

    func testBackendWorkProgressDecodes() {
        let metadata = frame(
            changeType: "backend.work.progress",
            runId: "task-1",
            inner: ["task_type": "import", "task_name": "Importing photos",
                    "status": "running", "message": "42 of 100",
                    "current": "42", "total": "100", "percent": "42"]
        )
        guard case .work(let status)? = BackendActivityEvent(activityMetadata: metadata) else {
            return XCTFail("expected .work")
        }
        XCTAssertEqual(status.runId, "task-1")
        XCTAssertEqual(status.phase, .progress)
        XCTAssertEqual(status.taskName, "Importing photos")
        XCTAssertEqual(status.current, 42)
        XCTAssertEqual(status.total, 100)
        XCTAssertEqual(status.displayPercent, 42)
        XCTAssertFalse(status.isTerminal)
    }

    func testBackendWorkCompletedIsTerminal() {
        let metadata = frame(
            changeType: "backend.work.completed", runId: "task-1",
            inner: ["task_name": "Importing photos", "status": "completed",
                    "current": "100", "total": "100", "percent": "100"]
        )
        guard case .work(let status)? = BackendActivityEvent(activityMetadata: metadata) else {
            return XCTFail("expected .work")
        }
        XCTAssertEqual(status.phase, .completed)
        XCTAssertTrue(status.isTerminal)
    }

    /// A fractional percent (the engine stringifies a float) parses without
    /// collapsing to zero.
    func testFractionalPercentParses() {
        let metadata = frame(
            changeType: "backend.work.progress", runId: "task-2",
            inner: ["task_name": "Indexing", "percent": "42.7", "total": "100", "current": "43"]
        )
        guard case .work(let status)? = BackendActivityEvent(activityMetadata: metadata) else {
            return XCTFail("expected .work")
        }
        XCTAssertEqual(status.percent, 42.7, accuracy: 0.001)
        XCTAssertEqual(status.displayPercent, 43)
    }

    func testLibraryOpenedDecodes() {
        let metadata = frame(
            changeType: "library.opened",
            inner: ["library_name": "Marshall Diaries", "source": "db_manager"]
        )
        guard case .libraryOpened(let opened)? = BackendActivityEvent(activityMetadata: metadata) else {
            return XCTFail("expected .libraryOpened")
        }
        XCTAssertEqual(opened.libraryName, "Marshall Diaries")
        XCTAssertEqual(opened.source, "db_manager")
        XCTAssertEqual(opened.timestamp, "t0")
    }

    /// A domain-mutation frame (entity.updated) is NOT a backend/library signal —
    /// the initializer returns nil so the caller falls through to its existing
    /// change-fold handling.
    func testDomainMutationFrameReturnsNil() {
        let metadata = frame(
            changeType: "entity.updated", runId: "r1",
            inner: [:]
        )
        XCTAssertNil(BackendActivityEvent(activityMetadata: metadata))
    }

    /// An unknown backend.work phase is rejected (nil) rather than mis-decoded.
    func testUnknownWorkPhaseReturnsNil() {
        let metadata = frame(
            changeType: "backend.work.paused", runId: "r1",
            inner: ["task_name": "X"]
        )
        XCTAssertNil(BackendActivityEvent(activityMetadata: metadata))
    }

    /// A frame with no change_type is not a signal.
    func testMissingChangeTypeReturnsNil() {
        XCTAssertNil(BackendActivityEvent(activityMetadata: ["ts": "t0"]))
    }
}
